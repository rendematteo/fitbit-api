"""Parsers para los CSVs del export de Google Health / Fitbit.

Formatos soportados (detección automática por encabezado):
- UserExercises_*.csv            → actividades (km, pasos, FC, calorías)
- WorkoutSummariesAndRounds.csv  → RPE por sesión (se une por hora)
- sleep_score.csv                → score de sueño, FC reposo, sueño profundo
- UserSleeps_*.csv               → horas de sueño
- Stress Score.csv               → estrés diario
- daily_vo2_max.csv              → VO2max
- weight.csv                     → peso

Nota de timezone: los valores sin offset (ej. Stress Score) son hora
LOCAL del usuario; se interpretan con la tz que recibe cada parser.
Los que vienen con Z ya son UTC.
"""
import csv
import io
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def _num(v):
    try:
        if v is None or str(v).strip() == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _int(v):
    n = _num(v)
    return int(n) if n is not None else None


def _iso(v, tz="UTC"):
    """'2026-08-21T23:00:15Z' → datetime UTC naive (sin tzinfo)."""
    if not v:
        return None
    s = str(v).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        dt = datetime.fromisoformat(s.split(".")[0])
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _date(v, tz="UTC"):
    dt = _iso(v, tz)
    return dt.date() if dt else None


def classify_activity(name: str) -> str:
    n = (name or "").lower()
    if "run" in n:
        return "run"
    if "walk" in n:
        return "walk"
    if "bike" in n or "cycle" in n:
        return "bike"
    if "swim" in n:
        return "swim"
    if "yoga" in n or "pilates" in n:
        return "flexibility"
    if "strength" in n or "weight" in n:
        return "strength"
    if "hiit" in n:
        return "hiit"
    if "workout" in n:
        return "workout"
    return "other"


# ---------- Actividades (UserExercises) ----------
def parse_exercises(text, tz="UTC"):
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        start = _iso(row.get("exercise_start"), tz)
        end = _iso(row.get("exercise_end"), tz)
        if not start:
            continue
        dur_min = (end - start).total_seconds() / 60.0 if end else None
        dist_mm = _num(row.get("tracker_total_distance_mm"))
        out.append(
            {
                "external_id": row.get("exercise_id") or None,
                "name": row.get("activity_name") or "Actividad",
                "type": classify_activity(row.get("activity_name")),
                "start_utc": start,
                "duration_min": dur_min,
                "distance_km": (dist_mm / 1e6) if dist_mm else None,
                "steps": _int(row.get("tracker_total_steps")),
                "calories": _int(row.get("tracker_total_calories")),
                "avg_hr": _int(row.get("tracker_avg_heart_rate")),
                "max_hr": _int(row.get("tracker_peak_heart_rate")),
                "rpe": None,  # se completa desde WorkoutSummaries
                "source": "fitbit_csv",
            }
        )
    return out


# ---------- RPE (WorkoutSummaries) ----------
def parse_workouts(text, tz="UTC"):
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        start = _iso(row.get("interval_start"), tz)
        rpe = _num(row.get("rate_perceived_exertion"))
        if start and rpe is not None:
            out.append({"start_utc": start, "rpe": int(rpe)})
    return out


# ---------- Métricas diarias ----------
def parse_sleep_score(text, tz="UTC"):
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        d = _date(row.get("timestamp"), tz)
        if not d:
            continue
        out.append(
            {
                "date": d,
                "sleep_score": _int(row.get("overall_score")),
                "deep_sleep_min": _int(row.get("deep_sleep_in_minutes")),
                "resting_hr": _int(row.get("resting_heart_rate")),
            }
        )
    return out


def parse_sleep_sessions(text, tz="UTC"):
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        d = _date(row.get("sleep_end"), tz)
        mins = _num(row.get("minutes_asleep"))
        if d and mins is not None:
            out.append({"date": d, "sleep_hours": round(mins / 60.0, 1)})
    return out


def parse_stress(text, tz="UTC"):
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        d = _date(row.get("DATE") or row.get("timestamp"), tz)
        stress = _num(row.get("STRESS_SCORE") or row.get("stress_score"))
        if d and stress is not None:
            out.append({"date": d, "stress": int(stress)})
    return out


def parse_vo2max(text, tz="UTC"):
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        d = _date(row.get("timestamp"), tz)
        v = _num(row.get("daily vo2 max value"))
        if d and v is not None:
            out.append({"date": d, "vo2max": round(v, 1)})
    return out


def parse_weight(text, tz="UTC"):
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        d = _date(row.get("timestamp"), tz)
        g = _num(row.get("weight grams"))
        if d and g is not None:
            out.append({"date": d, "weight_kg": round(g / 1000.0, 1)})
    return out


# ---------- Detección de formato ----------
def detect_and_parse(text, tz="UTC"):
    """Devuelve (kind, items) con kind en activities|workouts|metrics."""
    header = next(csv.reader(io.StringIO(text)), []) or []
    h = {c.strip().lower() for c in header}

    if "exercise_id" in h:
        return "activities", parse_exercises(text, tz)
    if "workout_name" in h:
        return "workouts", parse_workouts(text, tz)
    if "sleep_log_entry_id" in h:
        return "metrics", parse_sleep_score(text, tz)
    if "sleep_id" in h:
        return "metrics", parse_sleep_sessions(text, tz)
    if "daily vo2 max value" in h:
        return "metrics", parse_vo2max(text, tz)
    if "weight grams" in h:
        return "metrics", parse_weight(text, tz)
    if "stress_score" in h:
        return "metrics", parse_stress(text, tz)
    raise ValueError("Formato de CSV no reconocido")
