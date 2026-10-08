"""
fitbit_daily_sync.py — Sync diario e incremental de actividades de Fitbit → BigQuery.

Pensado para el plan 10K (28/11/2026):
- Incremental: la ventana se calcula desde el último DATE(startTs) en BigQuery
  (el "estado" son los propios datos). Si falla un día, se recupera solo; no hay
  dependencia de "ayer fijo" ni de zona horaria del servidor (UTC).
- Idempotente: MERGE por logId → reintentos y solapamientos NO duplican.
- Timezone-aware: America/Argentina/Buenos_Aires (ART = UTC-3).
- Backfill inicial configurable con FITBIT_START_DATE (default 2026-06-01).

Ejecución local:
    GCP_PROJECT_ID=... FITBIT_CLIENT_ID=... FITBIT_CLIENT_SECRET=... python fitbit_daily_sync.py

Cloud Function: desplegar con entrypoint `sync_fitbit_workouts` + trigger HTTP,
y Cloud Scheduler diario (ver instrucciones en el chat).
"""

import base64
import json
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

# Librerías de GCP son opcionales: solo hacen falta en modo BigQuery.
try:
    from google.api_core.exceptions import NotFound
    from google.cloud import bigquery, secretmanager
except ImportError:  # modo 100% Python local
    bigquery = None
    secretmanager = None
    NotFound = Exception

# ---------- Configuración ----------
PROJECT_ID = os.environ.get("GCP_PROJECT_ID")  # solo hace falta con BigQuery
DATASET = os.environ.get("BIGQUERY_DATASET", "fitbit_data")
TABLE = os.environ.get("BIGQUERY_TABLE", "workouts")
FULL_TABLE = f"`{PROJECT_ID}.{DATASET}.{TABLE}`" if PROJECT_ID else None

SECRET_ID_TOKENS = os.environ.get("SECRET_ID_TOKENS", "fitbit-tokens")
CLIENT_ID = os.environ["FITBIT_CLIENT_ID"]
CLIENT_SECRET = os.environ["FITBIT_CLIENT_SECRET"]

# Solo se usa en la PRIMERA ejecución (tabla vacía). Para arrancar con el plan
# completo desde el 5/10, pon FITBIT_START_DATE=2026-10-05.
START_DATE = os.environ.get("FITBIT_START_DATE", "2026-06-01")

# Zona horaria del corredor (Buenos Aires). Define cómo se interpreta startTime.
TZ_NAME = os.environ.get("FITBIT_TZ", "America/Argentina/Buenos_Aires")

PAGE_LIMIT = 50

# Modos de ejecución (sin GCP = 100% Python local):
#   FITBIT_TOKENS_FILE : tokens en archivo local (ej. fitbit_tokens.json)
#   FITBIT_LOCAL_LOG   : actividades a JSONL append-only (ej. actividades.jsonl)
SECRETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".secrets")
TOKENS_FILE = os.environ.get("FITBIT_TOKENS_FILE", os.path.join(SECRETS, "fitbit_tokens.json"))
LOCAL_LOG = os.environ.get("FITBIT_LOCAL_LOG")

sm_client = None
bq_client = None
if not TOKENS_FILE:
    sm_client = secretmanager.SecretManagerServiceClient()
if not LOCAL_LOG:
    if bigquery is None:
        raise RuntimeError(
            "Modo BigQuery requiere: pip install google-cloud-bigquery "
            "google-cloud-secret-manager"
        )
    bq_client = bigquery.Client(project=PROJECT_ID)

TABLE_SCHEMA = [
    bigquery.SchemaField("logId", "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("activityName", "STRING"),
    bigquery.SchemaField("activityTypeId", "INTEGER"),
    bigquery.SchemaField("startTime", "STRING"),   # ISO local: 2026-10-06T06:30:00
    bigquery.SchemaField("startTs", "TIMESTAMP"),  # startTime interpretado en TZ_NAME
    bigquery.SchemaField("durationMillis", "INTEGER"),
    bigquery.SchemaField("distanceKm", "FLOAT"),   # unidades según perfil de Fitbit (km)
    bigquery.SchemaField("calories", "INTEGER"),
    bigquery.SchemaField("steps", "INTEGER"),
    bigquery.SchemaField("averageHeartRate", "INTEGER"),
    bigquery.SchemaField("maxHeartRate", "INTEGER"),
    bigquery.SchemaField("logType", "STRING"),
    bigquery.SchemaField(
        "syncedAt", "TIMESTAMP", default_value_expression="CURRENT_TIMESTAMP()"
    ),
]

# Estructura de las filas que viajan como parámetro del MERGE.
STRUCT_DEF = (
    "logId INT64, activityName STRING, activityTypeId INT64, startTime STRING, "
    "durationMillis INT64, distanceKm FLOAT64, calories INT64, steps INT64, "
    "averageHeartRate INT64, maxHeartRate INT64, logType STRING"
)


# ---------- Estado / tokens ----------
def get_stored_tokens():
    """Recupera los tokens: archivo local o Secret Manager."""
    if TOKENS_FILE:
        with open(TOKENS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "refresh_token" in data:
            return data
        return {"refresh_token": data}

    name = f"projects/{PROJECT_ID}/secrets/{SECRET_ID_TOKENS}/versions/latest"
    raw = (
        sm_client.access_secret_version(request={"name": name})
        .payload.data.decode("UTF-8")
        .strip()
    )
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "refresh_token" in data:
            return data
    except json.JSONDecodeError:
        pass
    return {"refresh_token": raw}


def save_tokens(token_data):
    """Guarda (rota) los tokens: archivo local o Secret Manager."""
    if TOKENS_FILE:
        with open(TOKENS_FILE, "w", encoding="utf-8") as f:
            json.dump(token_data, f, indent=2)
        return

    parent = f"projects/{PROJECT_ID}/secrets/{SECRET_ID_TOKENS}"
    payload = {"data": json.dumps(token_data).encode("UTF-8")}
    sm_client.add_secret_version(request={"parent": parent, "payload": payload})


def refresh_fitbit_token(refresh_token):
    """Cambia el refresh token por un access token fresco y rota el secreto."""
    url = "https://api.fitbit.com/oauth2/token"
    auth_header = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    resp = requests.post(
        url,
        headers=headers,
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        timeout=15,
    )
    if resp.status_code == 400 and "invalid_grant" in resp.text:
        raise RuntimeError(
            "Refresh token inválido o expirado: re-autorizá la app en "
            "https://dev.fitbit.com y actualizá el secreto."
        )
    resp.raise_for_status()
    payload = resp.json()

    save_tokens(
        {
            "refresh_token": payload["refresh_token"],
            "access_token": payload["access_token"],
            "expires_at": (
                datetime.now(timezone.utc)
                + timedelta(seconds=payload.get("expires_in", 7200))
            ).isoformat(),
        }
    )
    return payload["access_token"]


# ---------- BigQuery ----------
def ensure_table():
    """Crea dataset/tabla si no existen (particionada por fecha de la sesión)."""
    bq_client.create_dataset(f"{PROJECT_ID}.{DATASET}", exists_ok=True)
    table_ref = bq_client.dataset(DATASET).table(TABLE)
    try:
        bq_client.get_table(table_ref)
        return
    except NotFound:
        pass
    t = bigquery.Table(table_ref, schema=TABLE_SCHEMA)
    t.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY, field="startTs"
    )
    bq_client.create_table(t)
    print(f"Tabla creada: {FULL_TABLE}")


def get_sync_start_date():
    """
    Ventana incremental: un día antes del último registro
    (BigQuery o el log local). El -1 es por si `afterDate` es
    exclusivo; la dedupe elimina solapamientos.
    """
    if LOCAL_LOG:
        last = ""
        if os.path.exists(LOCAL_LOG):
            with open(LOCAL_LOG, encoding="utf-8") as f:
                for line in f:
                    try:
                        d = json.loads(line).get("startTime", "")[:10]
                        if d:
                            last = d
                    except (json.JSONDecodeError, AttributeError):
                        continue
        if last:
            return (
                datetime.strptime(last, "%Y-%m-%d").date()
                - timedelta(days=1)
            ).isoformat()
        # Primera ejecución: backfill desde START_DATE.
        return (
            datetime.strptime(START_DATE, "%Y-%m-%d").date()
            - timedelta(days=1)
        ).isoformat()

    try:
        result = bq_client.query(
            f"SELECT MAX(DATE(startTs)) AS last_date FROM {FULL_TABLE}"
        ).result()
        last = next(iter(result)).last_date
        if last:
            return (last - timedelta(days=1)).isoformat()
    except NotFound:
        pass
    # Primera ejecución (tabla vacía): backfill desde START_DATE.
    return (datetime.strptime(START_DATE, "%Y-%m-%d").date() - timedelta(days=1)).isoformat()


# ---------- Fitbit API ----------
def fetch_activities_since(access_token, since_date):
    """Lista actividades posteriores a `since_date`, paginando con offset."""
    url = "https://api.fitbit.com/1/user/-/activities/list.json"
    headers = {"Authorization": f"Bearer {access_token}"}
    activities = []
    offset = 0
    while True:
        resp = requests.get(
            url,
            headers=headers,
            params={
                "afterDate": since_date,
                "sort": "asc",
                "limit": PAGE_LIMIT,
                "offset": offset,
            },
            timeout=30,
        )
        resp.raise_for_status()
        page = resp.json().get("activities", [])
        activities.extend(page)
        if len(page) < PAGE_LIMIT:
            break
        offset += len(page)
    return activities


# ---------- Transform & load ----------
def _int(v):
    return int(v) if v is not None else None


def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def transform(activities):
    """Payload de Fitbit → filas limpias (None en lugar de crashes)."""
    rows = []
    for item in activities:
        if not item.get("logId"):
            continue
        rows.append(
            {
                "logId": int(item["logId"]),
                "activityName": item.get("activityName"),
                "activityTypeId": _int(item.get("activityTypeId")),
                "startTime": f"{item.get('startDate')}T{item.get('startTime')}",
                "durationMillis": _int(
                    item.get("durationMillis") or item.get("duration")
                ),
                "distanceKm": _float(item.get("distance")),
                "calories": _int(item.get("calories")),
                "steps": _int(item.get("steps")),
                "averageHeartRate": _int(item.get("averageHeartRate")),
                "maxHeartRate": _int(item.get("maxHeartRate")),
                "logType": item.get("logType"),
            }
        )
    return rows


def load(rows):
    """MERGE por logId: seguro para reintentos, sin duplicados."""
    if not rows:
        print("Sin actividades nuevas en la ventana.")
        return 0

    merge_sql = f"""
    MERGE {FULL_TABLE} AS T
    USING (SELECT * FROM UNNEST(@rows)) AS S
    ON T.logId = S.logId
    WHEN NOT MATCHED THEN
      INSERT (logId, activityName, activityTypeId, startTime, startTs, durationMillis,
              distanceKm, calories, steps, averageHeartRate, maxHeartRate, logType)
      VALUES (S.logId, S.activityName, S.activityTypeId, S.startTime,
              TIMESTAMP(S.startTime, "{TZ_NAME}"), S.durationMillis, S.distanceKm,
              S.calories, S.steps, S.averageHeartRate, S.maxHeartRate, S.logType)
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter(
                "rows", f"ARRAY<STRUCT<{STRUCT_DEF}>>", rows
            )
        ]
    )
    bq_client.query(merge_sql, job_config=job_config).result()
    return len(rows)


def append_local_log(rows):
    """Append-only JSONL con dedupe por logId (modo 100% local)."""
    vistos = set()
    if os.path.exists(LOCAL_LOG):
        with open(LOCAL_LOG, encoding="utf-8") as f:
            for line in f:
                try:
                    vistos.add(json.loads(line)["logId"])
                except (json.JSONDecodeError, KeyError):
                    continue
    nuevas = [r for r in rows if r["logId"] not in vistos]
    with open(LOCAL_LOG, "a", encoding="utf-8") as f:
        for r in nuevas:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(nuevas)


# ---------- Entrypoint ----------
def sync_fitbit_workouts(request=None):
    """Entrypoint de Cloud Function (HTTP / Cloud Scheduler) o ejecución local."""
    try:
        if not LOCAL_LOG:
            ensure_table()

        since = get_sync_start_date()
        print(f"Ventana de sync: actividades después de {since}")

        tokens = get_stored_tokens()
        access_token = refresh_fitbit_token(tokens["refresh_token"])

        activities = fetch_activities_since(access_token, since)
        rows = transform(activities)

        if LOCAL_LOG:
            inserted = append_local_log(rows)
            print(f"Sync OK: {inserted} actividad(es) nueva(s) en {LOCAL_LOG}.")
        else:
            inserted = load(rows)
            print(f"Sync OK: {inserted} actividad(es) nueva(s) en {FULL_TABLE}.")
        return ("Sync completed successfully.", 200)
    except Exception as e:
        print(f"Error during Fitbit sync: {e}")
        return (f"Internal Error: {str(e)}", 500)


if __name__ == "__main__":
    print(sync_fitbit_workouts())
