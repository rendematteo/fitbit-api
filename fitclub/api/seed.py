"""Backfill: sube el export de Google Health / Fitbit a FitClub.

Se corre DENTRO del contenedor (con el export montado en /data):
    docker compose exec api python seed.py
"""
import os

import httpx

BASE = os.environ.get("CLUB_URL", "http://localhost:8000")
EMAIL = os.environ.get("CLUB_EMAIL", "renzo@fitclub.local")
PASSWORD = os.environ.get("CLUB_PASSWORD", "renzo1234")
NAME = os.environ.get("CLUB_NAME", "Renzo")
TAKEOUT = os.environ.get("TAKEOUT_DIR", "/data/Google Health")

FILES = [
    "Health Fitness Data_GoogleData/UserExercises_2026-06-19.csv",
    "Health Fitness Data_GoogleData/WorkoutSummariesAndRounds.csv",
    "Sleep Score/sleep_score.csv",
    "Health Fitness Data_GoogleData/UserSleeps_2026-06-19.csv",
    "Stress Score/Stress Score.csv",
    "Physical Activity_GoogleData/Daily Vo2 Max/daily_vo2_max.csv",
    "Physical Activity_GoogleData/Weight/weight.csv",
]


def main():
    # Login (solo email+password), o registro si no existe
    r = httpx.post(
        f"{BASE}/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=30,
    )
    if r.status_code == 200:
        token = r.json()["access_token"]
        print("Login OK")
    else:
        r = httpx.post(
            f"{BASE}/api/auth/register",
            json={"email": EMAIL, "display_name": NAME, "password": PASSWORD},
            timeout=30,
        )
        if r.status_code != 201:
            raise SystemExit(f"No se pudo crear la cuenta: {r.text}")
        token = r.json()["access_token"]
        print("Registro OK")

    paths = []
    for rel in FILES:
        p = os.path.join(TAKEOUT, rel)
        if os.path.exists(p):
            paths.append(p)
        else:
            print(f"(no encontrado: {rel})")

    if not paths:
        raise SystemExit("No hay archivos para subir. ¿Montaste el export en /data?")

    files = [
        ("files", (os.path.basename(p), open(p, "rb").read(), "text/csv"))
        for p in paths
    ]
    r = httpx.post(
        f"{BASE}/api/ingest/files",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
        timeout=600,
    )
    r.raise_for_status()
    result = r.json()
    print(result)
    if result.get("errors"):
        print("⚠️ Archivos con problemas:", result["errors"])


if __name__ == "__main__":
    main()
