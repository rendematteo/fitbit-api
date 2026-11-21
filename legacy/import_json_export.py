"""
import_json_export.py — Backfill OFFLINE desde el export JSON de Fitbit
("Global Export Data") → las mismas dos JSONL que google_health_sync.py.

Útil mientras la Google Health API no está disponible para proyectos nuevos
("not onboarding new projects") o para recuperar historial completo: el
export trae todo el account, no solo la ventana de la API.

═════════ ESQUEMA REAL DEL EXPORT (¡NO es la Google Health API!) ═════════
Los JSON del export son el formato de la **Fitbit Web API**: listas de
registros con campos camelCase. Los que importan acá:

- exercise-*.json → actividades. Campos: logId, activityName,
  activityTypeId, startTime "MM/DD/YY HH:MM:SS", duration y
  activeDuration (milisegundos), distance (float) + distanceUnit
  ("Kilometer"), calories (kcal), steps, averageHeartRate (solo si el
  tracker midió FC), activeZoneMinutes.totalMinutes, heartRateZones[].
  NO todos los registros tienen averageHeartRate/steps/distance.
- resting_heart_rate-*.json → [{dateTime, value:{date "MM/DD/YY",
  value (FC reposo, float), error}}]. value=0.0 es placeholder (se salta).
- sleep-*.json → [{logId, dateOfSleep "YYYY-MM-DD", minutesAsleep,
  mainSleep, ...}]. Puede haber varias siestas por fecha: gana la
  mainSleep, o si no, la de mayor minutesAsleep.
- demographic_vo2_max-*.json → [{dateTime, value:{demographicVO2Max, ...}}]
- run_vo2_max-*.json → [{dateTime, value:{runVO2Max, exerciseId, ...}}]
  (si un día tiene ambos, gana el de run: es medición directa)
- weight-*.json → [{logId, weight, bmi, date "MM/DD/YY"}]. El peso viene
  en la unidad del perfil de Fitbit; se autodetecta lb vs kg con el bmi
  (ver transform_weight).

El resto (heart_rate-/distance-/calories-/steps- intradiarios, badge.json,
time_in_heart_rate_zones-, height-, swim_lengths_data-, *active_minutes-,
sedentary_minutes-) se parsea pero no mapea a estas dos JSONL.

═════════ EJECUCIÓN ═════════
python import_json_export.py

Variables de entorno:
  EXPORT_DIR         (default C:\\Users\\R\\Downloads\\data-fitbit\\Google Health\\Global Export Data)
  HEALTH_LOCAL_LOG   (default actividades_google_health.jsonl)
  HEALTH_METRICS_LOG (default metricas_google_health.jsonl)

Dedupe por external_id (actividades) y date (métricas): lee los JSONL
existentes y solo appendea lo nuevo. Stdlib únicamente (json, glob, os,
datetime).
"""
import glob
import json
import os
from datetime import datetime

EXPORT_DIR = os.environ.get(
    "EXPORT_DIR",
    r"C:\Users\R\Downloads\data-fitbit\Google Health\Global Export Data",
)
ACTIVITIES_LOG = os.environ.get("HEALTH_LOCAL_LOG", "actividades_google_health.jsonl")
METRICS_LOG = os.environ.get("HEALTH_METRICS_LOG", "metricas_google_health.jsonl")

# Prefijos de archivo que SÍ mapean a las JSONL → tipo de dato.
# "heart_rate-" (serie intradiaria) no está: cae en "other".
PREFIX_KINDS = (
    ("exercise-", "exercise"),
    ("resting_heart_rate-", "resting_hr"),
    ("sleep-", "sleep"),
    ("demographic_vo2_max-", "vo2_demographic"),
    ("run_vo2_max-", "vo2_run"),
    ("weight-", "weight"),
)


# ---------- Tiempo ----------
def parse_fitbit_datetime(s):
    """'MM/DD/YY HH:MM:SS' (formato Fitbit) → datetime naive."""
    return datetime.strptime(s.strip(), "%m/%d/%y %H:%M:%S")


def parse_fitbit_date(s):
    """'MM/DD/YY' → date (tolera 'MM/DD/YY HH:MM:SS': toma los 10 primeros)."""
    return datetime.strptime(s.strip()[:10], "%m/%d/%y").date()


# ---------- Actividades (exercise-*.json) ----------
def distance_to_km(value, unit):
    """Convierte distance a km según distanceUnit del export."""
    unit = (unit or "").strip().lower()
    if unit.startswith("mile"):
        return value * 1.609344
    if unit.startswith("meter"):
        return value / 1000.0
    return value  # "Kilometer" (unidad por defecto del export)


def transform_exercise(log):
    """Un registro de exercise → fila de actividades_google_health.jsonl."""
    def _int(key):
        v = log.get(key)
        return int(v) if isinstance(v, (int, float)) else None

    active_ms = log.get("activeDuration") or 0
    total_ms = log.get("duration") or 0
    dur_ms = active_ms if active_ms > 0 else total_ms

    dist = log.get("distance")
    distance_km = (
        distance_to_km(dist, log.get("distanceUnit")) if dist is not None else None
    )

    # El export no trae pace directo: se deriva de duración activa / distancia.
    pace_s_per_m = None
    if distance_km and distance_km > 0 and dur_ms:
        pace_s_per_m = round((dur_ms / 1000.0) / (distance_km * 1000.0), 2)

    # AZM: activeZoneMinutes.totalMinutes; fallback = suma de heartRateZones.
    active_zone_min = None
    azm = log.get("activeZoneMinutes")
    if isinstance(azm, dict) and isinstance(azm.get("totalMinutes"), (int, float)):
        active_zone_min = int(azm["totalMinutes"])
    else:
        hz = log.get("heartRateZones")
        if isinstance(hz, list) and hz:
            active_zone_min = int(sum(z.get("minutes") or 0 for z in hz))

    start = parse_fitbit_datetime(log["startTime"])
    return {
        "external_id": str(log["logId"]),
        "name": log.get("activityName") or "Actividad",
        "type": (log.get("activityName") or "actividad").strip().lower(),
        "start_local": start.isoformat(),
        "duration_min": round(dur_ms / 60000.0, 1),
        "distance_km": round(distance_km, 3) if distance_km is not None else None,
        "calories": _int("calories"),
        "steps": _int("steps"),
        "avg_hr": _int("averageHeartRate"),  # solo si el tracker midió FC
        "pace_s_per_m": pace_s_per_m,
        "active_zone_min": active_zone_min,
        "source": "google_health_json_export",
    }


# ---------- Métricas diarias ----------
def transform_resting_hr(entry):
    """resting_heart_rate-*.json → {date, resting_hr} (None si no hay dato)."""
    val = entry.get("value")
    bpm = val.get("value") if isinstance(val, dict) else None
    if not isinstance(bpm, (int, float)) or bpm <= 0:
        return None  # el export trae placeholders con 0.0
    d = (val.get("date") if isinstance(val, dict) else None) or entry.get("dateTime")
    if not d:
        return None
    return {"date": parse_fitbit_date(d).isoformat(), "resting_hr": int(round(bpm))}


def transform_sleep(entries):
    """sleep-*.json → una fila {date, sleep_hours} por dateOfSleep.

    Si hay varios registros para la misma fecha (siestas), gana el
    mainSleep; si no hay main, el de mayor minutesAsleep.
    """
    by_date = {}
    for e in entries:
        d = e.get("dateOfSleep")  # "YYYY-MM-DD"
        mins = e.get("minutesAsleep")
        if not d or not isinstance(mins, (int, float)):
            continue
        cand = {
            "date": d,
            "sleep_hours": round(mins / 60.0, 1),
            "main": bool(e.get("mainSleep")),
            "mins": mins,
        }
        cur = by_date.get(d)
        if (
            cur is None
            or (cand["main"] and not cur["main"])
            or (cand["main"] == cur["main"] and cand["mins"] > cur["mins"])
        ):
            by_date[d] = cand
    return [{"date": c["date"], "sleep_hours": c["sleep_hours"]} for c in by_date.values()]


def transform_vo2(entry, field):
    """demographic_vo2_max- / run_vo2_max- → {date, vo2max}."""
    val = entry.get("value")
    v = val.get(field) if isinstance(val, dict) else None
    if not isinstance(v, (int, float)) or v <= 0:
        return None
    d = entry.get("dateTime")
    if not d:
        return None
    return {"date": parse_fitbit_date(d).isoformat(), "vo2max": round(v, 1)}


def transform_weight(entry):
    """weight-*.json → {date, weight_kg}.

    Fitbit exporta el peso en la unidad del perfil. Se interpreta como
    libras si, tomado como kg, el BMI implicaría una altura implausible
    (h² = weight/bmi fuera de [1.88, 4.20] m² ≈ fuera de 1.37–2.05 m).
    En el export actual: 149.9 con BMI 23.53 → h²=6.37 → libras → 68.0 kg.
    """
    w = entry.get("weight")
    if not isinstance(w, (int, float)) or w <= 0:
        return None
    kg = w
    bmi = entry.get("bmi")
    if isinstance(bmi, (int, float)) and bmi > 0:
        h2_if_kg = w / bmi
        if h2_if_kg > 4.20 or h2_if_kg < 1.88:
            kg = w * 0.45359237  # lb → kg
    d = entry.get("date")
    if not d:
        return None
    return {"date": parse_fitbit_date(d).isoformat(), "weight_kg": round(kg, 1)}


# ---------- JSONL ----------
def read_jsonl(path):
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def append_rows(path, rows):
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def classify(filename):
    """Tipo de dato según el prefijo del archivo; desconocido → 'other'."""
    base = os.path.basename(filename).lower()
    for prefix, kind in PREFIX_KINDS:
        if base.startswith(prefix):
            return kind
    return "other"


def _map_records(records, fn):
    """Aplica fn a cada registro; salta (y cuenta) los malformados."""
    out, malos = [], 0
    for rec in records:
        try:
            row = fn(rec)
        except Exception:
            malos += 1
            continue
        if row is not None:
            out.append(row)
    return out, malos


# ---------- Main ----------
def main():
    actividades = []
    metricas = {}  # date → fila mergeada (mismo patrón que google_health_sync)
    archivos = glob.glob(os.path.join(EXPORT_DIR, "*.json"))
    errores = []
    otros = 0
    registros_malos = 0

    for path in sorted(archivos):
        nombre = os.path.basename(path)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("el JSON no es una lista de registros")

            kind = classify(path)
            if kind == "exercise":
                rows, malos = _map_records(data, transform_exercise)
                actividades.extend(rows)
                registros_malos += malos
            elif kind == "resting_hr":
                rows, malos = _map_records(data, transform_resting_hr)
                registros_malos += malos
                for m in rows:
                    metricas.setdefault(m["date"], {}).update(m)
            elif kind == "sleep":
                # transform_sleep ya es robusta por registro (salta los
                # que no tienen dateOfSleep/minutesAsleep) y toma la lista.
                rows = transform_sleep(data)
                for m in rows:
                    metricas.setdefault(m["date"], {}).update(m)
            elif kind == "vo2_demographic":
                rows, malos = _map_records(data, lambda x: transform_vo2(x, "demographicVO2Max"))
                registros_malos += malos
                for m in rows:
                    metricas.setdefault(m["date"], {}).update(m)
            elif kind == "vo2_run":
                rows, malos = _map_records(data, lambda x: transform_vo2(x, "runVO2Max"))
                registros_malos += malos
                for m in rows:
                    metricas.setdefault(m["date"], {}).update(m)
            elif kind == "weight":
                rows, malos = _map_records(data, transform_weight)
                registros_malos += malos
                for m in rows:
                    metricas.setdefault(m["date"], {}).update(m)
            else:
                otros += 1  # parseado OK, pero no mapea a estas dos JSONL
        except Exception as e:  # un archivo roto/vacío no debe matar el backfill
            errores.append(f"{nombre}: {type(e).__name__}: {e}")

    # --- Dedupe: descartar lo que ya está en los JSONL (y duplicados del run) ---
    ids_vistos = {
        r.get("external_id") for r in read_jsonl(ACTIVITIES_LOG) if r.get("external_id")
    }
    act_nuevas = []
    for a in actividades:
        if a["external_id"] not in ids_vistos:
            ids_vistos.add(a["external_id"])
            act_nuevas.append(a)

    fechas_vistas = {r.get("date") for r in read_jsonl(METRICS_LOG) if r.get("date")}
    met_nuevas = []
    for fecha in sorted(metricas):
        if fecha not in fechas_vistas:
            fechas_vistas.add(fecha)
            met_nuevas.append(metricas[fecha])

    if act_nuevas:
        append_rows(ACTIVITIES_LOG, act_nuevas)
    if met_nuevas:
        append_rows(METRICS_LOG, met_nuevas)

    # --- Resumen ---
    print(f"Export: {len(archivos)} archivos JSON en {EXPORT_DIR}")
    print(f"  Actividades: +{len(act_nuevas)} nuevas ({len(actividades)} en el export)")
    print(f"  Métricas:    +{len(met_nuevas)} días nuevos ({len(metricas)} días en el export)")
    print(f"  Otros archivos (parseados, sin mapeo): {otros}")
    if registros_malos:
        print(f"  Registros saltados por formato inesperado: {registros_malos}")
    if errores:
        print(f"  ⚠️ {len(errores)} archivo(s) con error:")
        for e in errores:
            print(f"    - {e}")
    else:
        print("  Sin errores de archivo.")
    print("OK ✅")


if __name__ == "__main__":
    main()
