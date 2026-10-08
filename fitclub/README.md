# 🏃 FitClub

Base de datos + API + dashboard web para entrenamientos en grupo: cada uno sube
sus actividades de Fitbit y compiten en un ranking.

```
fitclub/
├── docker-compose.yml   # Postgres + API
├── api/
│   ├── main.py          # FastAPI: auth, actividades, métricas, leaderboard, ingest
│   ├── db.py            # Modelos SQLModel (Postgres)
│   ├── ingest.py        # Parsers de CSVs de Google Health / Fitbit
│   ├── seed.py          # Backfill del export de Fitbit
│   └── Dockerfile
└── web/                 # Dashboard estático (Chart.js, sin build)
```

## 1. Requisitos

- **Docker Desktop** (Windows/Mac) o Docker en una VPS (para que entren los amigos)
- Este proyecto

## 2. Levantar

```bash
cd fitclub
cp .env.example .env        # cambiá SECRET_KEY
docker compose up -d --build
```

Abrí **http://localhost:8000** → registrate (o logueate) → listo.

> Sin Docker y con Python 3.11+ instalado:
> ```bash
> cd api
> pip install -r requirements.txt
> uvicorn main:app --reload          # usa SQLite por defecto
> ```

## 3. Cargar tus datos históricos (backfill)

Montá el export de Fitbit en `docker-compose.yml` (descomentá el volumen y
ajustá la ruta a tu máquina, ejemplo Windows):

```yaml
    volumes:
      - C:/Users/R/Desktop/Plan_10K/data-fitbit:/data:ro
```

Y corré el seed:

```bash
docker compose exec api python seed.py
```

Sube: actividades (UserExercises: km, pasos, FC), RPE (WorkoutSummaries),
sueño, FC reposo, estrés, VO2max y peso. **También podés subir los CSVs
desde la pestaña "Subir CSV" del dashboard**, sin tocar nada.

## 4. Invitar amigos

Compartí la URL (si está en tu red local: `http://TU-IP:8000`; para afuera,
una VPS con Docker). Cada amigo:

1. Se registra con su email
2. Sube sus CSVs de Fitbit (o carga actividades a mano con "+ Actividad")
3. Aparece en el ranking 🏆

> ⚠️ El registro es abierto. Para un grupo cerrado, agregá un código de
> invitación en `/api/auth/register` antes de publicarlo.

## 5. Sincronización diaria automática (opcional)

El script `fitbit_daily_sync.py` ya refresca el token de Fitbit; para que
cargue **acá** en vez de BigQuery, reemplazá `load(rows)` por:

```python
import os
from datetime import datetime
from zoneinfo import ZoneInfo
import httpx

TZ = ZoneInfo(os.environ.get("FITBIT_TZ", "America/Argentina/Buenos_Aires"))

def post_to_club(rows):
    payload = []
    for r in rows:
        # Fitbit devuelve startTime en hora LOCAL sin offset → la localizamos
        start_local = datetime.fromisoformat(r["startTime"]).replace(tzinfo=TZ)
        payload.append({
            "external_id": str(r["logId"]),
            "name": r["activityName"],
            "type": "run" if "run" in (r["activityName"] or "").lower() else "other",
            "start_utc": start_local.astimezone(ZoneInfo("UTC")).isoformat(),
            "duration_min": (r["durationMillis"] or 0) / 60000,
            "distance_km": r["distanceKm"],
            "calories": r["calories"],
            "steps": r["steps"],
            "avg_hr": r["averageHeartRate"],
            "max_hr": r["maxHeartRate"],
            "source": "fitbit_api",
        })
    r = httpx.post(
        os.environ["CLUB_URL"] + "/api/activities/bulk",
        headers={"Authorization": f"Bearer {os.environ['CLUB_API_TOKEN']}"},
        json={"activities": payload},
        timeout=30,
    )
    r.raise_for_status()
```

El token de la API se obtiene con `POST /api/auth/login` (solo email+password).

> **Convención de timezone:** `start_utc` siempre es UTC. Si mandás ISO
> con offset (`...-03:00` o `Z`) la API lo convierte; si es naive, lo
> toma como UTC.

## 6. Tests

```bash
docker compose exec api pytest -v     # o: cd api && pytest -v
```

Cubierto: auth, CRUD de actividades, dedupe por `external_id`, upsert de
métricas, leaderboard (orden, streak), e ingestión de CSV de Fitbit.

## 6. Ranking

`GET /api/leaderboard?period=week|month|alltime&metric=km|activities|duration|longest|streak`

- **km / duration / activities**: suma del período
- **longest**: actividad más larga del período
- **streak**: días consecutivos con actividad (hoy sin entrenar no rompe)

## Próximos pasos

- Desafíos fijos (ej. "octubre: 100 km") con tabla propia
- Código de invitación para registro cerrado
- Racha por tipo de actividad (solo runs)
- Notificaciones cuando alguien te pase en el ranking
