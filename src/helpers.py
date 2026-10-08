"""
src/helpers.py — Funciones auxiliares compartidas.
"""
import json
import os
from datetime import datetime, timedelta


# ---------------- números ----------------

def num(v, default=0.0):
    """Acepta number o string (int64 de la API viene como string)."""
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def num_or_none(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------- texto ----------------

def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def pace_str(min_per_km):
    """min/km → 'm:ss'/km"""
    if not min_per_km:
        return "-"
    m = int(min_per_km)
    s = int(round((min_per_km - m) * 60))
    return f"{m}:{s:02d}"


# ---------------- fechas ----------------

def parse_ts(s):
    """'2026-10-03T19:03:04Z' -> datetime UTC"""
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_off(s):
    """'-10800s' -> timedelta"""
    if not s:
        return timedelta(0)
    try:
        return timedelta(seconds=int(str(s).replace("s", "")))
    except ValueError:
        return timedelta(0)


def parse_dur_s(s):
    """'775.024s' -> segundos"""
    if not s:
        return None
    try:
        return float(str(s).replace("s", ""))
    except ValueError:
        return None


def to_local(dt_utc, off):
    return (dt_utc + off) if dt_utc else None


def fmt_date(d):
    return d.strftime("%d/%m")


def civil_key(d):
    """Acepta {year,month,day} o {date:{...}, time:{...}} -> 'YYYY-MM-DD'."""
    if not isinstance(d, dict):
        return None
    if isinstance(d.get("date"), dict):
        d = d["date"]
    if not d.get("year"):
        return None
    return f"{int(d['year'])}-{int(d.get('month', 1)):02d}-{int(d.get('day', 1)):02d}"


def day_key(civil_dt):
    """{date:{year,month,day}, time:{...}} -> 'YYYY-MM-DD' (o None)."""
    return civil_key(civil_dt)


# ---------------- rollup ----------------

def rollup_sum(value_obj):
    """Saca el campo *_Sum de un rollup value (string o number)."""
    if not isinstance(value_obj, dict):
        return None
    for k, v in value_obj.items():
        if k.lower().endswith("sum"):
            return num(v)
    return None


# ---------------- locales ----------------

def load_local(data_dir, dt):
    """Carga <data_dir>/<dt>.json (dt con guiones)."""
    p = os.path.join(data_dir, f"{dt}.json")
    if not os.path.exists(p):
        return []
    try:
        with open(p, encoding="utf-8") as f:
            return (json.load(f).get("dataPoints")) or []
    except Exception:
        return []
