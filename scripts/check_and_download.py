#!/usr/bin/env python3
"""
check_and_download.py — Probar la credencial + Google Health API y bajar datos
a una carpeta. DESCARGA INCREMENTAL (sync_state.json + merge).

PURA API REST (https://health.googleapis.com/v4) + google-auth.
NO necesita Docker, NO necesita gRPC, NO necesita compilar protos.

Uso:
    python check_and_download.py --test                 # solo probar (1 llamada chica)
    python check_and_download.py                        # probar + bajar todo
    python check_and_download.py --since 2026-10-01     # bajar solo desde esa fecha
    python check_and_download.py --only exercise sleep   # bajar solo esos tipos
    python check_and_download.py --full                  # bajar TODO el historial
    python check_and_download.py --reauth               # re-autorizar aunque haya token
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from src.api import get_creds
from src.helpers import num, esc
from src.paths import SECRETS_DIR, DATA_DIR

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

API = "https://health.googleapis.com"

SCOPES = [
    "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
    "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
    "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly",
]

# Tipos de dato a bajar. Los IDs en la URL van con GUIONES (heart-rate),
# pero los filtros AIP-160 usan GUIONES BAJOS (heart_rate).
DATA_TYPES = [
    "exercise", "sleep", "heart-rate", "daily-resting-heart-rate",
    "daily-vo2-max", "weight", "steps", "distance", "total-calories",
]

# heart-rate son muestras crudas de 1 segundo (~160 MB) y NO se usan en los
# reportes (esos usan dailyRollUp). Se saltea por defecto; incluilo con
# --with-heart-rate o pidiéndolo explícitamente con --only heart-rate.
DEFAULT_SKIP = ["heart-rate"]

FILTERS = {
    "exercise": 'exercise.interval.civil_start_time >= "{since}"',
    "sleep": 'sleep.interval.civil_end_time >= "{since}"',
    "heart-rate": 'heart_rate.sample_time.civil_time >= "{since}"',
    "weight": 'weight.sample_time.civil_time >= "{since}"',
    "daily-resting-heart-rate": 'daily_resting_heart_rate.date >= "{since}"',
    "daily-vo2-max": 'daily_vo2_max.date >= "{since}"',
    "total-calories": 'total_calories.interval.civil_start_time >= "{since}"',
}

STATE_FILE = os.path.join(SECRETS_DIR, "sync_state.json")


# ---------------- estado incremental ----------------

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def merge_points(existing, new):
    """Une por 'name' (ID único del punto) — sin duplicados."""
    merged = {}
    for p in existing + new:
        key = p.get("name") or json.dumps(p, sort_keys=True)[:120]
        merged[key] = p
    return list(merged.values())


# ---------------- API REST ----------------

def api_get(creds, path, params=None):
    """GET REST con el bearer token. Devuelve (status_code, body)."""
    if creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
    r = requests.get(
        API + path,
        headers={"Authorization": f"Bearer {creds.token}"},
        params=params or {},
        timeout=60,
    )
    try:
        body = r.json()
    except ValueError:
        body = {"message": r.text[:500]}
    return r.status_code, body


def diagnose(status, body):
    err = body.get("error", {}) if isinstance(body, dict) else {}
    msg = err.get("message") or body.get("message") or ""
    gstatus = err.get("status", "")
    if status == 200:
        return True, "✅ ANDA — credencial válida y API accesible"
    if status == 401:
        return False, "❌ 401 — token inválido o expirado. Reintentá con --reauth"
    if status == 403:
        if "PERMISSION_DENIED" in gstatus or "permission" in msg.lower():
            return False, (
                "❌ 403 PERMISSION_DENIED — Google NO está habilitando proyectos "
                "nuevos (onboarding cerrado). No es error tuyo: reintentá en unos "
                "días o usá import_json_export.py con el export de Downloads"
            )
        if "redirect" in msg.lower():
            return False, (
                "❌ redirect_uri_mismatch — agregá http://127.0.0.1 (y http://localhost) "
                "en Authorized redirect URIs del cliente"
            )
        return False, f"❌ 403 — {msg or gstatus}"
    if status == 404:
        return False, (
            "❌ 404 — Google Health API no habilitada en el proyecto (o la ruta no existe). "
            "Habilitá 'Google Health API' en Library. Detalle: " + (msg or "sin detalle")
        )
    return False, f"❌ HTTP {status} — {msg or gstatus or body}"


def test_api(creds):
    print("\n🔍 Test: 1 solo punto de 'exercise' (pageSize=1)...")
    status, body = api_get(
        creds, "/v4/users/me/dataTypes/exercise/dataPoints", {"pageSize": 1}
    )
    ok, msg = diagnose(status, body)
    print("   " + msg)
    if ok:
        dp = (body.get("dataPoints") or [{}])[0]
        print("   Muestra: " + json.dumps(dp, ensure_ascii=False)[:280])
    return ok


def download(creds, out_dir, since, only=None, full=False, skip=None):
    os.makedirs(out_dir, exist_ok=True)
    print(f"\n⬇️  Bajando a: {out_dir}\n")
    state = load_state()
    resumen = {}
    skip = set(skip or [])
    tipos = [t for t in (only or DATA_TYPES) if t not in skip]
    if skip:
        print(f"  ⏭️  Salteando: {', '.join(sorted(skip))}")
    for dt in tipos:
        page_size = 25 if dt in ("exercise", "sleep") else 10000
        params = {"pageSize": page_size}

        since_eff = since
        if not since_eff and not full and dt in state:
            try:
                last = datetime.strptime(state[dt], "%Y-%m-%d") - timedelta(days=1)
                since_eff = last.strftime("%Y-%m-%d")
                print(f"  🔁 {dt}: incremental desde {since_eff}")
            except ValueError:
                pass

        if since_eff and dt in FILTERS:
            params["filter"] = FILTERS[dt].format(since=since_eff)
        if dt == "total-calories" and "filter" not in params:
            params["filter"] = 'total_calories.interval.civil_start_time >= "2026-01-01"'

        puntos, token, paginas = [], None, 0
        while True:
            if token:
                params["pageToken"] = token
            status, body = api_get(
                creds, f"/v4/users/me/dataTypes/{dt}/dataPoints", params
            )
            if status != 200:
                _, msg = diagnose(status, body)
                print(f"  ⚠️  {dt}: {msg}")
                break
            dps = body.get("dataPoints") or []
            puntos.extend(dps)
            paginas += 1
            token = body.get("nextPageToken")
            if not token or not dps:
                break

        path = os.path.join(out_dir, f"{dt}.json")
        existing = []
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    existing = (json.load(f).get("dataPoints")) or []
            except Exception:
                existing = []
        if existing:
            antes = len(existing)
            puntos = merge_points(existing, puntos)
            print(f"  🔗 merge: {antes} → {len(puntos)} puntos")

        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {"dataType": dt, "count": len(puntos), "dataPoints": puntos},
                f, ensure_ascii=False,
            )
        print(f"  ✅ {dt}: {len(puntos)} puntos ({paginas} pág.) → {dt}.json")
        resumen[dt] = len(puntos)
        state[dt] = datetime.now().strftime("%Y-%m-%d")
    save_state(state)
    print("\n📦 Resumen: " + json.dumps(resumen, ensure_ascii=False))
    print(f"📁 Todo en: {out_dir}")


def main():
    ap = argparse.ArgumentParser(
        description="Probar credencial + Google Health API y bajar datos (sin Docker)"
    )
    ap.add_argument("--test", action="store_true", help="solo probar, no bajar")
    ap.add_argument("--reauth", action="store_true", help="re-autorizar aunque haya token")
    ap.add_argument("--since", help="bajar solo desde YYYY-MM-DD")
    ap.add_argument("--only", nargs="+", help="bajar solo estos data types")
    ap.add_argument("--skip", nargs="+", help="data types a saltear (default: heart-rate)")
    ap.add_argument("--with-heart-rate", action="store_true", help="incluir heart-rate (~160 MB de muestras de 1 s)")
    ap.add_argument("--full", action="store_true", help="bajar TODO el historial")
    ap.add_argument("--out", default=None, help="carpeta de descarga")
    args = ap.parse_args()

    # heart-rate (muestras crudas de 1 s, ~160 MB) se saltea salvo que se pida.
    if args.skip is not None:
        skip = args.skip
    elif args.only or args.with_heart_rate:
        skip = []
    else:
        skip = list(DEFAULT_SKIP)

    out_dir = args.out or DATA_DIR

    print("=" * 62)
    print("🩺 CHEQUEO GOOGLE HEALTH API — REST, sin Docker ni gRPC")
    print("=" * 62)
    creds = get_creds(SECRETS_DIR)

    if not test_api(creds):
        print("\n🚫 Hasta que esto ande no se puede bajar nada. Posibles causas:")
        print("   • redirect_uri_mismatch  → Credentials → tu cliente → Authorized")
        print("     redirect URIs → agregá  http://127.0.0.1  y  http://localhost")
        print("   • 404                    → habilitá 'Google Health API' en Library")
        print("   • 403 PERMISSION_DENIED  → onboarding cerrado; esperá o usá")
        print("     import_json_export.py (backfill desde Downloads)")
        sys.exit(1)

    if args.test:
        print("\n🎉 ¡Todo anda! Para bajar los datos:  python check_and_download.py")
        return

    download(creds, out_dir, args.since, only=args.only, full=args.full, skip=skip)


if __name__ == "__main__":
    main()
