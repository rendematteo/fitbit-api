"""Suite de tests para la API FitClub (pytest + fastapi.testclient.TestClient).

Requiere: fastapi, sqlmodel, httpx, python-jose, passlib, python-multipart, pytest.
Ejecutar desde la carpeta fitclub/api:  pytest test_api.py
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# ¡EL ORDEN IMPORTA! db.py lee DATABASE_URL y main.py lee SECRET_KEY al
# importar, así que hay que setear las env vars ANTES de importar db/main.
# Usamos SQLite de archivo en un temp dir: es la opción más simple y robusta
# con SQLModel (:memory: crearía una DB distinta por conexión; db.py ya
# agrega check_same_thread=False para SQLite).
# ---------------------------------------------------------------------------
_TMP_DIR = tempfile.mkdtemp(prefix="fitclub_test_")
os.environ["DATABASE_URL"] = "sqlite:///" + _TMP_DIR.replace(os.sep, "/") + "/test_fitclub.db"
os.environ["SECRET_KEY"] = "test-secret-key"

# Para que `from db import ...` (import absoluto de main.py) funcione sin
# importar desde dónde corre pytest.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete  # noqa: E402
from sqlmodel import Session, SQLModel  # noqa: E402

from db import Activity, DailyMetric, User, engine  # noqa: E402
from main import app  # noqa: E402


# ---------- Fixtures y helpers ----------
@pytest.fixture()
def client():
    SQLModel.metadata.create_all(engine)
    with TestClient(app) as c:  # el lifespan corre init_db()
        yield c
    # Limpieza entre tests
    with Session(engine) as s:
        s.exec(delete(Activity))
        s.exec(delete(DailyMetric))
        s.exec(delete(User))
        s.commit()


def register(client, email, display_name="Tester", password="test1234"):
    r = client.post(
        "/api/auth/register",
        json={"email": email, "display_name": display_name, "password": password},
    )
    assert r.status_code == 201, r.text
    return r.json()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def act_json(name, start_utc, **kw):
    d = {"name": name, "type": "run", "start_utc": start_utc}
    d.update(kw)
    return d


# ---------- Auth ----------
def test_register_login_ok_and_bad(client):
    body = {"email": "ana@example.com", "display_name": "Ana", "password": "test1234"}

    # register → 201 con token
    r = client.post("/api/auth/register", json=body)
    assert r.status_code == 201
    data = r.json()
    assert data["token_type"] == "bearer"
    assert data["access_token"]
    assert data["user"]["email"] == "ana@example.com"
    assert data["user"]["display_name"] == "Ana"

    # login ok → token válido
    r = client.post("/api/auth/login", json=body)
    assert r.status_code == 200
    token = r.json()["access_token"]
    me = client.get("/api/me", headers=auth(token))
    assert me.status_code == 200
    assert me.json()["email"] == "ana@example.com"

    # login malo → 401
    bad = dict(body, password="wrong")
    assert client.post("/api/auth/login", json=bad).status_code == 401
    # login con email inexistente → 401
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "nadie@example.com", "display_name": "N", "password": "x"},
        ).status_code
        == 401
    )


def test_register_duplicate_email_409(client):
    body = {"email": "dupe@example.com", "display_name": "Dupe", "password": "test1234"}
    assert client.post("/api/auth/register", json=body).status_code == 201
    r = client.post("/api/auth/register", json=body)
    assert r.status_code == 409


def test_protected_endpoints_require_token(client):
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/activities").status_code == 401
    assert client.get("/api/leaderboard").status_code == 401
    assert (
        client.post(
            "/api/activities",
            json=act_json("Run", datetime.utcnow().isoformat()),
        ).status_code
        == 401
    )
    # token inválido → 401
    r = client.get("/api/me", headers={"Authorization": "Bearer no-es-un-token"})
    assert r.status_code == 401


# ---------- Actividades ----------
def test_activities_create_and_list_sorted(client):
    token = register(client, "act@example.com")["access_token"]
    headers = auth(token)
    now = datetime.utcnow()

    r1 = client.post(
        "/api/activities",
        json=act_json("Trote de ayer", (now - timedelta(days=1)).isoformat(), distance_km=5.0, duration_min=30),
        headers=headers,
    )
    assert r1.status_code == 201
    assert r1.json()["name"] == "Trote de ayer"

    r2 = client.post(
        "/api/activities",
        json=act_json("Run de hoy", now.isoformat(), distance_km=3.0),
        headers=headers,
    )
    assert r2.status_code == 201

    lst = client.get("/api/activities", headers=headers).json()
    assert len(lst) == 2
    # ordenado por start_utc descendente (más reciente primero)
    assert lst[0]["id"] == r2.json()["id"]
    assert lst[0]["name"] == "Run de hoy"
    assert lst[1]["name"] == "Trote de ayer"
    assert lst[0]["distance_km"] == 3.0


def test_bulk_skips_repeated_external_id(client):
    token = register(client, "bulk@example.com")["access_token"]
    headers = auth(token)
    now = datetime.utcnow().isoformat()
    payload = {
        "activities": [
            act_json("Primera", now, external_id="ext-1", distance_km=4.0),
            act_json("Repetida", now, external_id="ext-1", distance_km=99.0),
        ]
    }

    r = client.post("/api/activities/bulk", json=payload, headers=headers)
    assert r.status_code == 200
    assert r.json() == {"added": 1, "skipped": 1}

    lst = client.get("/api/activities", headers=headers).json()
    assert len(lst) == 1  # no duplicó
    assert lst[0]["external_id"] == "ext-1"
    assert lst[0]["name"] == "Primera"

    # segunda vez con el mismo payload: todo skipped
    r2 = client.post("/api/activities/bulk", json=payload, headers=headers)
    assert r2.json() == {"added": 0, "skipped": 2}
    assert len(client.get("/api/activities", headers=headers).json()) == 1


def test_delete_activity(client):
    token = register(client, "del@example.com")["access_token"]
    headers = auth(token)

    r = client.post(
        "/api/activities",
        json=act_json("Para borrar", datetime.utcnow().isoformat()),
        headers=headers,
    )
    activity_id = r.json()["id"]

    d = client.delete(f"/api/activities/{activity_id}", headers=headers)
    assert d.status_code == 200
    assert d.json() == {"ok": True}
    assert client.get("/api/activities", headers=headers).json() == []

    # borrar de nuevo (o inexistente) → 404
    assert client.delete(f"/api/activities/{activity_id}", headers=headers).status_code == 404


# ---------- Métricas diarias (upsert) ----------
def test_metrics_upsert_same_date_updates(client):
    token = register(client, "met@example.com")["access_token"]
    headers = auth(token)
    today = datetime.utcnow().date().isoformat()

    r1 = client.post(
        "/api/metrics",
        json={"date": today, "resting_hr": 60, "sleep_hours": 7.5},
        headers=headers,
    )
    assert r1.status_code == 200

    # misma fecha → actualiza, no duplica
    r2 = client.post("/api/metrics", json={"date": today, "resting_hr": 55}, headers=headers)
    assert r2.status_code == 200

    stats = client.get("/api/me/stats", headers=headers).json()
    entries = [m for m in stats["metrics"] if m["date"] == today]
    assert len(entries) == 1
    assert entries[0]["resting_hr"] == 55
    assert entries[0]["sleep_hours"] == 7.5  # campo no enviado se conserva


# ---------- Leaderboard ----------
def test_leaderboard_week_km_order_and_you(client):
    u1 = register(client, "uno@example.com", "Uno")
    u2 = register(client, "dos@example.com", "Dos")
    now = datetime.utcnow().isoformat()  # dentro de la semana actual

    for token, km in ((u1["access_token"], 10.0), (u2["access_token"], 4.0)):
        r = client.post(
            "/api/activities",
            json=act_json("Run", now, distance_km=km),
            headers=auth(token),
        )
        assert r.status_code == 201

    lb = client.get(
        "/api/leaderboard",
        params={"period": "week", "metric": "km"},
        headers=auth(u1["access_token"]),
    ).json()

    assert len(lb) == 2
    assert lb[0]["rank"] == 1
    assert lb[0]["name"] == "Uno"
    assert lb[0]["km"] == 10.0
    assert lb[0]["you"] is True
    assert lb[1]["rank"] == 2
    assert lb[1]["name"] == "Dos"
    assert lb[1]["km"] == 4.0
    assert lb[1]["you"] is False


# ---------- Streak ----------
def test_streak_consecutive_days(client):
    token = register(client, "streak@example.com")["access_token"]
    headers = auth(token)

    today = datetime.utcnow().date()
    for days_ago in (2, 1, 0):  # antes de ayer, ayer, hoy
        start = datetime(today.year, today.month, today.day) - timedelta(days=days_ago)
        r = client.post(
            "/api/activities",
            json=act_json("Run", start.isoformat()),
            headers=headers,
        )
        assert r.status_code == 201

    stats = client.get("/api/me/stats", headers=headers).json()
    assert stats["streak"] == 3


# ---------- Ingestión de CSVs ----------
# Header real de UserExercises de Fitbit (lo relevante para el parser:
# exercise_id, exercise_start/end, activity_name y los tracker_*)
_EXERCISES_HEADER = [
    "exercise_id", "exercise_start", "exercise_end", "utc_offset",
    "exercise_created", "exercise_last_updated", "activity_name", "log_type",
    "pool_length", "pool_length_unit", "intervals", "distance_units",
    "tracker_total_calories", "tracker_total_steps", "tracker_total_distance_mm",
    "tracker_total_altitude_mm", "tracker_avg_heart_rate", "tracker_peak_heart_rate",
]
_EXERCISES_ROW = [
    "98765", "2026-10-02T10:00:00Z", "2026-10-02T10:30:00Z", "-180",
    "2026-10-02T10:31:00Z", "2026-10-02T10:31:00Z", "Running", "FitbitRun",
    "0", "", "0", "km", "300", "1000", "5000000", "10000", "120", "160",
]
_EXERCISES_CSV = "\n".join([",".join(_EXERCISES_HEADER), ",".join(_EXERCISES_ROW)]) + "\n"


def test_ingest_userexercises_csv(client):
    token = register(client, "ingest@example.com")["access_token"]
    headers = auth(token)

    r = client.post(
        "/api/ingest/files",
        headers=headers,
        files={"files": ("UserExercises.csv", _EXERCISES_CSV, "text/csv")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["activities_added"] == 1
    assert body["activities_skipped"] == 0
    assert body["errors"] == []

    lst = client.get("/api/activities", headers=headers).json()
    assert len(lst) == 1
    a = lst[0]
    assert a["external_id"] == "98765"
    assert a["name"] == "Running"
    assert a["type"] == "run"
    assert a["source"] == "fitbit_csv"
    assert a["distance_km"] == 5.0  # 5.000.000 mm / 1e6
    assert a["duration_min"] == 30.0
    assert a["steps"] == 1000
    assert a["calories"] == 300
    assert a["avg_hr"] == 120
    assert a["max_hr"] == 160


def test_ingest_unknown_csv_reports_error(client):
    token = register(client, "unk@example.com")["access_token"]

    r = client.post(
        "/api/ingest/files",
        headers=auth(token),
        files={"files": ("unknown.csv", "foo,bar\n1,2\n", "text/csv")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["activities_added"] == 0
    assert len(body["errors"]) == 1
    assert "unknown.csv" in body["errors"][0]
    assert "no reconocido" in body["errors"][0]
