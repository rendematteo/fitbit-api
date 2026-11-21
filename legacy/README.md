# 🗄️ legacy/ — scripts deprecados

Estos scripts **ya no son parte del flujo principal**. Se conservan por
referencia / fallback. El flujo actual está en `scripts/` y usa solo **REST**
(`src/api.py`).

| Script | Por qué está acá |
|---|---|
| `authorize_fitbit.py` | OAuth de la **Fitbit Web API** (se apagó el 30/10/2026) |
| `fitbit_daily_sync.py` | Sync de la Fitbit Web API → BigQuery (API muerta) |
| `google_health_sync.py` | Sync **gRPC** (reemplazado por REST en `check_and_download.py`) |
| `import_json_export.py` | Backfill desde un export JSON/Takeout (fallback si la API falla) |

> No los uses salvo que sepas lo que hacés. Para el día a día: `scripts/`.
