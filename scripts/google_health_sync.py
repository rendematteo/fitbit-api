"""
google_health_sync.py — Sync diario de la Google Health API (gRPC) → JSONL local.

Reemplaza a la Fitbit Web API, que se apaga el 30/10/2026.

══════════ SETUP ══════════
1. Correr authorize_google_health.py (crea token.json)
2. Compilar los protos (una sola vez):

   git clone --depth 1 https://github.com/googleapis/googleapis.git
   cd googleapis
   python -m grpc_tools.protoc --proto_path=. --python_out=. --grpc_python_out=. \\
     google/devicesandservices/health/v4/data_points.proto \\
     google/devicesandservices/health/v4/data_model.proto \\
     google/devicesandservices/health/v4/data_source.proto \\
     google/devicesandservices/health/v4/data_coordinates.proto \\
     google/devicesandservices/health/v4/medical_device_info.proto
   cd ..

   (el script agrega googleapis/ al sys.path para importar los stubs)

3. pip install grpcio google-auth google-auth-oauthlib googleapis-common-protos

══════════ EJECUCIÓN DIARIA ══════════
python google_health_sync.py

Descarga (con filtro por hora CIVIL = tu zona horaria):
- exercise        → actividades (km, FC avg, pace, pasos, calorías, AZM)
- sleep           → horas de sueño (sleep_summary.minutes_asleep)
- daily-resting-heart-rate → FC reposo
- daily-vo2-max   → VO2max
- weight          → peso

Todo se appendea a JSONL con dedupe (id del data point / fecha):
- actividades_google_health.jsonl
- metricas_google_health.jsonl

Ventana incremental: retoma desde el último registro del log.
Primera ejecución: backfill desde HEALTH_BACKFILL_START (default 2026-06-01).

Variables de entorno:
  HEALTH_TOKEN_FILE       (default token.json)
  HEALTH_GOOGLEAPIS_DIR   (default ./googleapis)
  HEALTH_TZ               (default America/Argentina/Buenos_Aires)
  HEALTH_BACKFILL_START   (default 2026-06-01)
  HEALTH_LOCAL_LOG        (default actividades_google_health.jsonl)
  HEALTH_METRICS_LOG      (default metricas_google_health.jsonl)
"""
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import grpc
from google.auth.transport.grpc import secure_authorized_channel
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

GOOGLEAPIS_DIR = os.environ.get("HEALTH_GOOGLEAPIS_DIR", "googleapis")
sys.path.insert(0, GOOGLEAPIS_DIR)

# Stubs compilados (ver setup arriba)
from google.devicesandservices.health.v4 import data_model_pb2
from google.devicesandservices.health.v4 import data_points_pb2
from google.devicesandservices.health.v4 import data_points_pb2_grpc

# ---------- Configuración ----------
GRPC_ENDPOINT = "health.googleapis.com:443"
SECRETS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".secrets")  # hermano: projects/.secrets
TOKEN_FILE = os.environ.get("HEALTH_TOKEN_FILE", os.path.join(SECRETS, "token.json"))
TZ_NAME = os.environ.get("HEALTH_TZ", "America/Argentina/Buenos_Aires")
BACKFILL_START = os.environ.get("HEALTH_BACKFILL_START", "2026-06-01")
LOCAL_LOG = os.environ.get("HEALTH_LOCAL_LOG", "actividades_google_health.jsonl")
METRICS_LOG = os.environ.get("HEALTH_METRICS_LOG", "metricas_google_health.jsonl")

SCOPES = [
    "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
    "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
    "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly",
]


# ---------- Auth ----------
def get_credentials():
    """Token de archivo; se refresca solo si expiró."""
    with open(TOKEN_FILE, encoding="utf-8") as f:
        creds = Credentials.from_authorized_user_info(json.load(f), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


# ---------- Helpers de tiempo ----------
def proto_ts_to_dt(ts):
    """protobuf Timestamp → datetime UTC naive."""
    return datetime.fromtimestamp(
        ts.seconds + ts.nanos / 1e9, tz=timezone.utc
    ).replace(tzinfo=None)


def civil_to_dt(c):
    """CivilDateTime (hora local) → datetime naive."""
    return datetime(c.year, c.month, c.day, c.hours, c.minutes, c.seconds)


def date_to_str(d):
    return f"{d.year:04d}-{d.month:02d}-{d.day:02d}"


# ---------- Lectura de logs (ventana incremental) ----------
def _read_log(path):
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def _last_activity_date(path):
    last = None
    for r in _read_log(path):
        ts = r.get("start_local") or ""
        d = ts[:10]
        if d and (last is None or d > last):
            last = d
    return date.fromisoformat(last) if last else None


def _last_metric_date(path):
    last = None
    for r in _read_log(path):
        d = r.get("date", "")
        if d and (last is None or d > last):
            last = d
    return date.fromisoformat(last) if last else None


def _existing_ids(path):
    return {r.get("external_id") for r in _read_log(path) if r.get("external_id")}


def _existing_metric_dates(path):
    return {r.get("date") for r in _read_log(path) if r.get("date")}


# ---------- API ----------
def list_data_points(stub, data_type, filter_expr):
    """ListDataPoints con paginación (page_size máx 25 para exercise/sleep)."""
    out = []
    page_token = ""
    while True:
        req = data_points_pb2.ListDataPointsRequest(
            parent=f"users/me/dataTypes/{data_type}",
            page_size=25,
            filter=filter_expr,
            page_token=page_token,
        )
        resp = stub.ListDataPoints(req)
        out.extend(resp.data_points)
        if not resp.next_page_token:
            break
        page_token = resp.next_page_token
    return out


# ---------- Transformación ----------
def transform_exercise(dp):
    ex = dp.exercise
    ms = ex.metrics_summary

    if ex.interval.HasField("civil_start_time"):
        start = civil_to_dt(ex.interval.civil_start_time)
        end = civil_to_dt(ex.interval.civil_end_time)
    else:
        start = proto_ts_to_dt(ex.interval.start_time)
        end = proto_ts_to_dt(ex.interval.end_time)

    dur_min = (end - start).total_seconds() / 60.0
    active_s = (
        ex.active_duration.seconds if ex.HasField("active_duration") else None
    )
    dist_mm = (
        ms.distance_millimeters if ms.HasField("distance_millimeters") else None
    )
    pace = (
        ms.average_pace_seconds_per_meter
        if ms.HasField("average_pace_seconds_per_meter")
        else None
    )

    return {
        "external_id": dp.name.rsplit("/", 1)[-1] if dp.name else None,
        "name": ex.display_name or "Actividad",
        "type": data_model_pb2.Exercise.ExerciseType.Name(ex.exercise_type).lower(),
        "start_local": start.isoformat(),
        "duration_min": round(active_s / 60.0, 1) if active_s else round(dur_min, 1),
        "distance_km": round(dist_mm / 1e6, 3) if dist_mm else None,
        "calories": int(ms.calories_kcal) if ms.HasField("calories_kcal") else None,
        "steps": int(ms.steps) if ms.HasField("steps") else None,
        "avg_hr": (
            int(ms.average_heart_rate_beats_per_minute)
            if ms.HasField("average_heart_rate_beats_per_minute")
            else None
        ),
        "pace_s_per_m": round(pace, 2) if pace else None,
        "active_zone_min": (
            int(ms.active_zone_minutes) if ms.HasField("active_zone_minutes") else None
        ),
        "source": "google_health_api",
    }


def transform_sleep(dp):
    s = dp.sleep
    if s.interval.HasField("civil_start_time"):
        start = civil_to_dt(s.interval.civil_start_time)
        end = civil_to_dt(s.interval.civil_end_time)
    else:
        start = proto_ts_to_dt(s.interval.start_time)
        end = proto_ts_to_dt(s.interval.end_time)

    minutes_asleep = None
    if s.HasField("sleep_summary") and s.sleep_summary.HasField("minutes_asleep"):
        minutes_asleep = int(s.sleep_summary.minutes_asleep)

    return {
        "date": start.date().isoformat(),
        "start_local": start.isoformat(),
        "sleep_hours": (
            round(minutes_asleep / 60.0, 1)
            if minutes_asleep is not None
            else round((end - start).total_seconds() / 3600.0, 1)
        ),
    }


def transform_rhr(dp):
    r = dp.daily_resting_heart_rate
    return {
        "date": date_to_str(r.date),
        "resting_hr": int(r.beats_per_minute),
    }


def transform_vo2max(dp):
    v = dp.daily_vo2_max
    return {"date": date_to_str(v.date), "vo2max": round(v.vo2_max, 1)}


def transform_weight(dp):
    w = dp.weight
    if w.sample_time.HasField("civil_time"):
        when = civil_to_dt(w.sample_time.civil_time)
    else:
        when = proto_ts_to_dt(w.sample_time.sample_time)
    return {
        "date": when.date().isoformat(),
        "weight_kg": round(w.weight_grams / 1000.0, 1),
    }


# ---------- Persistencia ----------
def append_rows(path, rows):
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# ---------- Sync ----------
def sync():
    tz = ZoneInfo(TZ_NAME)
    today = datetime.now(tz).date()

    # Ventana incremental (último registro del log - 1 día)
    since_act = _last_activity_date(LOCAL_LOG) or date.fromisoformat(BACKFILL_START)
    since_met = _last_metric_date(METRICS_LOG) or date.fromisoformat(BACKFILL_START)
    since_act -= timedelta(days=1)
    since_met -= timedelta(days=1)

    creds = get_credentials()
    channel = secure_authorized_channel(creds, Request(), GRPC_ENDPOINT)
    stub = data_points_pb2_grpc.DataPointsServiceStub(channel)

    try:
        # --- Actividades (exercise) ---
        f_ex = (
            f'exercise.interval.civil_start_time >= "{since_act.isoformat()}" '
            f'AND exercise.interval.civil_start_time < "{today.isoformat()}"'
        )
        exercises = [
            transform_exercise(dp)
            for dp in list_data_points(stub, "exercise", f_ex)
        ]
        vistos = _existing_ids(LOCAL_LOG)
        nuevas = [a for a in exercises if a["external_id"] not in vistos]
        append_rows(LOCAL_LOG, nuevas)
        print(f"Actividades: +{len(nuevas)} (total en ventana: {len(exercises)})")

        # --- Métricas diarias ---
        metricas = {}

        f_rhr = f'daily_resting_heart_rate.date >= "{since_met.isoformat()}"'
        for dp in list_data_points(stub, "daily-resting-heart-rate", f_rhr):
            m = transform_rhr(dp)
            metricas.setdefault(m["date"], {}).update(m)

        f_vo2 = f'daily_vo2_max.date >= "{since_met.isoformat()}"'
        for dp in list_data_points(stub, "daily-vo2-max", f_vo2):
            m = transform_vo2max(dp)
            metricas.setdefault(m["date"], {}).update(m)

        f_sleep = (
            f'sleep.interval.civil_end_time >= "{since_met.isoformat()}" '
            f'AND sleep.interval.civil_end_time < "{today.isoformat()}"'
        )
        for dp in list_data_points(stub, "sleep", f_sleep):
            m = transform_sleep(dp)
            metricas.setdefault(m["date"], {}).update(m)

        f_w = f'weight.sample_time.civil_time >= "{since_met.isoformat()}"'
        for dp in list_data_points(stub, "weight", f_w):
            m = transform_weight(dp)
            metricas.setdefault(m["date"], {}).update(m)

        fechas_viejas = _existing_metric_dates(METRICS_LOG)
        nuevas_metricas = [
            v for k, v in metricas.items() if k not in fechas_viejas
        ]
        append_rows(METRICS_LOG, nuevas_metricas)
        print(f"Métricas: +{len(nuevas_metricas)} días (total en ventana: {len(metricas)})")

        print("Sync OK ✅")
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.PERMISSION_DENIED:
            print(
                "❌ PERMISSION_DENIED: Google aún no habilitó tu proyecto "
                "('not onboarding new projects'). Seguí con fitbit_daily_sync.py "
                "hasta el 30/10/2026 y reintentá después."
            )
        else:
            print(f"❌ gRPC error {e.code()}: {e.details()}")
        raise
    finally:
        channel.close()


if __name__ == "__main__":
    sync()
