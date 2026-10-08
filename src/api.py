"""
src/api.py — Cliente de la Google Health API (REST).
Auth (token de .secrets/), dailyRollUp (acumulado) y list (datos crudos).
"""
import os
import time

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

API = "https://health.googleapis.com/v4"


# ---------------- auth ----------------

def get_creds(secrets_dir):
    """Carga el token de .secrets/ y lo refresca si expiró."""
    creds = Credentials.from_authorized_user_file(
        os.path.join(secrets_dir, "token.json"))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


# ---------------- dailyRollUp (acumulado diario) ----------------

def daily_rollup(creds, data_type, body, tries=3):
    """POST /v4/users/me/dataTypes/{tipo}/dataPoints:dailyRollUp"""
    url = f"{API}/users/me/dataTypes/{data_type}/dataPoints:dailyRollUp"
    h = {"Authorization": f"Bearer {creds.token}",
         "Content-Type": "application/json"}
    r = None
    for i in range(tries):
        try:
            r = requests.post(url, headers=h, json=body, timeout=60)
        except Exception:
            r = None
        if r is not None and r.status_code == 503 and i < tries - 1:
            time.sleep(1.5 * (i + 1))
            continue
        break
    if r is None:
        return []
    try:
        return (r.json() or {}).get("rollupDataPoints") or []
    except ValueError:
        return []


# ---------------- list (datos crudos) ----------------

def list_daily(creds, data_type, since, filter_expr):
    """GET paginado con filtro AIP-160 (para tipos sin rollup)."""
    url = f"{API}/users/me/dataTypes/{data_type}/dataPoints"
    h = {"Authorization": f"Bearer {creds.token}"}
    params = {"pageSize": 10, "filter": filter_expr.format(since=since)}
    out = []
    for _ in range(5):
        r = requests.get(url, headers=h, params=params, timeout=60)
        if r.status_code != 200:
            break
        body = r.json()
        out.extend(body.get("dataPoints") or [])
        token = body.get("nextPageToken")
        if not token:
            break
        params["pageToken"] = token
    return out
