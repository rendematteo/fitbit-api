# Google Health API — referencia rápida (REST)

Base: `https://health.googleapis.com` (sin `/v4` en la base; las rutas llevan `/v4/...`).

## Auth

- OAuth2 **Desktop**, scopes:
  - `https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly`
  - `https://www.googleapis.com/auth/googlehealth.sleep.readonly`
  - `https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly`
- Token en `../.secrets/token.json` (refresh automático).

## List (datos crudos)

`GET /v4/users/me/dataTypes/{tipo}/dataPoints?pageSize=N&filter=...`

- Paginado con `nextPageToken`.
- Filtros AIP-160 (guiones bajos en el campo): `heart_rate.sample_time.civil_time >= "..."`.

## Daily rollup (acumulado diario)

`POST /v4/users/me/dataTypes/{tipo}/dataPoints:dailyRollUp`

Body:

```json
{
  "range": { "start": "YYYY-MM-DD", "end": "YYYY-MM-DD" },
  "windowSizeDays": 1,
  "pageSize": 100
}
```

Respuesta: `rollupDataPoints[]` con `civilStartTime` / `civilEndTime`.

## Data types

| ID (URL) | Filtro (AIP-160) | Notas |
|---|---|---|
| `exercise` | `exercise.interval.civil_start_time` | actividades |
| `sleep` | `sleep.interval.civil_end_time` | noches |
| `heart-rate` | `heart_rate.sample_time.civil_time` | muestras de 1 s (~160 MB) |
| `daily-resting-heart-rate` | `daily_resting_heart_rate.date` | 1/día |
| `daily-vo2-max` | `daily_vo2_max.date` | 1/día |
| `weight` | `weight.sample_time.civil_time` | |
| `steps` | — (rollup) | 1/día |
| `distance` | — (rollup) | 1/día |
| `total-calories` | `total_calories.interval.civil_start_time` | solo rollup, no list |

## Zona horaria

`America/Argentina/Buenos_Aires` (ART, UTC-3, offset `-10800s`).

## Notas

- `dailyRollUp` deduplica fuentes crudas (Fitbit Air + teléfono + MobileTrack).
- `steps` / `distance` a veces devuelven 503 → retry con backoff.
- La Fitbit Web API se apaga el **30/10/2026**; después solo Google Health API.
