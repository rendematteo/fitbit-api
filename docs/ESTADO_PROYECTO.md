# 🗺️ ESTADO DEL PROYECTO — FitClub + Plan 10K

> Guardado el 04/10/2026 para vaciar contexto. **Leer este archivo primero.**

## 🎯 La idea (3 piezas)

1. **Plan 10K** — carrera el **sáb 28/11/2026**, meta 85–90 min, todo ≤1 h/día,
   fáciles siempre ≤135 bpm. Plan completo 8 semanas (Base→Build→Peak→Taper).
   - Archivos: `C:\Users\R\Desktop\Plan_10K\*.md` y
     `C:\Users\R\Desktop\projects\fitbit-personal\plan_10k_28nov.csv`
2. **FitClub** — app (Docker + Postgres + FastAPI + web) donde Renzo y sus
   amigos suben sus actividades y compiten en un ranking.
   - Código: `C:\Users\R\Desktop\projects\fitbit-personal\fitclub\`
   - `docker-compose.yml` (Postgres + API) · `api/` (main.py, db.py, ingest.py,
     seed.py, test_api.py) · `web/` (dashboard estático + Chart.js)
   - **No probado**: esta PC no tiene Docker ni Python en PATH.
3. **Pipeline de datos** — Fitbit/Google Health → JSONL local → FitClub.

## 📍 Datos del usuario (Renzo, 34a, M, 1.70m, ~65kg, Buenos Aires ART=UTC-3)

| Dato | Ubicación |
|---|---|
| Plan + perfil corredor | `Desktop\Plan_10K\` |
| Export Takeout (CSV, corte jun–oct 2026) | `Desktop\Plan_10K\data-fitbit\Google Health\` |
| **Export JSON nuevo (datos actuales)** | `Downloads\data-fitbit\Google Health\Global Export Data\` |
| OAuth client (Web, id `65081823542-bsgv21a6iohdcmclhhogdnm7mnk9r74b...`) | `fitbit-personal\client_secret.json` ✅ |

## ✅ Hecho

- `fitclub/` completo (API, ingest de CSV del Takeout, leaderboard, tests) —
  revisado por subagentes y corregido (tz, bcrypt, XSS, Docker context, etc.)
- `authorize_fitbit.py` + `fitbit_daily_sync.py` — sync a la **Fitbit Web API**
  (PUENTE: válido hasta el **30/10/2026**, después se apaga)
- `authorize_google_health.py` + `google_health_sync.py` — sync a la **Google
  Health API** (gRPC, `health.googleapis.com:443`), protos del repo googleapis
- `import_json_export.py` (creado por subagente) — parsea el export JSON de
  `Downloads` → `actividades_google_health.jsonl` + `metricas_google_health.jsonl`
- `GOOGLE_HEALTH_SETUP.md` (checklist personal) y
  `GOOGLE_HEALTH_API_PASO_A_PASO.md` (guía genérica con links)

## 🚦 Estado de la auth Google

- Cliente OAuth creado como **Web application** (no Desktop).
- Para que funcione con `authorize_google_health.py`:
  **Credentials → editar cliente → Authorized redirect URIs → agregar
  `http://127.0.0.1`** (Google permite cualquier puerto en loopback, RFC 8252).
  Si da `redirect_uri_mismatch`, agregar también `http://localhost`.
- ⚠️ Google **no está onboarding proyectos nuevos**: si la API devuelve
  `PERMISSION_DENIED`, el puente es `fitbit_daily_sync.py` hasta el 30/10 y
  `import_json_export.py` para backfill desde los JSON de Downloads.

## ▶️ Próximos pasos (en orden)

1. Agregar `http://127.0.0.1` al cliente Web (ver arriba)
2. `pip install google-auth google-auth-oauthlib requests` →
   `python check_and_download.py --test` (autoriza + verifica la API con
   1 llamada REST; equivale a `authorize_google_health.py` pero con
   chequeo incluido) → `token.json`
3. `pip install grpcio googleapis-common-protos` → compilar protos (comando en
   el docstring de `google_health_sync.py`) → `python google_health_sync.py`
4. Si 2–3 fallan por onboarding: `python import_json_export.py` (backfill)
5. Levantar FitClub donde haya Docker: `cd fitclub && docker compose up -d --build`
   → http://localhost:8000
6. **Pendiente**: importador `*.jsonl → FitClub`
   (`POST /api/activities/bulk`, mapear `start_local`→`start_utc` con ART)
7. **Pendiente**: probar `pytest` en `fitclub/api/`

## ⏰ Fechas clave

- **30/09/2026**: fin de soporte Fitbit Web API (ya pasó)
- **30/10/2026**: Fitbit Web API se apaga — migrar a Google Health API
- **28/11/2026**: carrera 10K

## 🛠️ Scripts en `fitbit-personal\`

| Script | Para qué |
|---|---|
| `authorize_fitbit.py` | OAuth one-time Fitbit (puente) |
| `fitbit_daily_sync.py` | Sync diario Fitbit → JSONL/BigQuery |
| `authorize_google_health.py` | OAuth one-time Google Health |
| `google_health_sync.py` | Sync diario gRPC → JSONL |
| `import_json_export.py` | Backfill desde export JSON de Downloads |
| `check_and_download.py` | **Test de credencial + API (REST, sin Docker) y descarga a `descargas_google_health/`** |

> Regla de oro: **nunca compartir** `client_secret.json`, `token.json`, ni
> credenciales por chat.
