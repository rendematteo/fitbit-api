# 🏃 FitClub — Resumen del proyecto

> Pipeline de datos de salud (Fitbit → Google Health API) + dashboard web estático
> + plan de entrenamiento 10K. Todo local, sin Docker para los reportes.

---

## 📁 Archivos

### 🔐 Credenciales (NUNCA compartir)
| Archivo | Qué es |
|---|---|
| `client_secret.json` | OAuth client **Desktop** de Google Cloud (proyecto `analog-fastness-428900-t2`) |
| `token.json` | access + refresh token — **login one-time**, se renueva solo |
| `client_secret_web_backup.json` | backup del cliente Web viejo (ya no se usa) |

### 🐍 Scripts Python
| Script | Para qué |
|---|---|
| `authorize_google_health.py` | OAuth one-time → genera `token.json` (navegador, Allow) |
| `check_and_download.py` | Test de credencial + **descarga incremental** (estado + merge) |
| `reporte_2_dias.py` | Resumen de últimos 2 días vía **dailyRollUp** (acumulado, sin muestras crudas) |
| `panel.py` | Genera `index.html` — **panel minimalista interactivo** (entrada principal) |
| `make_dashboard.py` | Genera `estadisticas.html` — dashboard completo (60 actividades, Top 3, tabla ordenable) |
| `google_health_sync.py` | Sync gRPC alternativo (necesita protos compilados) |
| `fitbit_daily_sync.py` | Sync Fitbit Web API — **puente hasta el 30/10/2026** |
| `authorize_fitbit.py` | OAuth Fitbit (puente) |
| `import_json_export.py` | Backfill desde el export JSON de Downloads |

### 📊 Datos
| Carpeta/Archivo | Qué es |
|---|---|
| `descargas_google_health/` | JSON bajados de la API (exercise, sleep, steps, distance, weight, heart-rate…) |
| `sync_state.json` | Estado de la descarga incremental (última fecha por tipo) |

### 🌐 Web (estáticas, sin servidor)
| Archivo | Qué es |
|---|---|
| `index.html` | **Panel minimalista interactivo** — entrada principal |
| `estadisticas.html` | Dashboard completo |
| `ultimos_2_dias.html` | Reporte de 2 días |

### 📄 Docs
| Archivo | Qué es |
|---|---|
| `ESTADO_PROYECTO.md` | Estado y próximos pasos |
| `GOOGLE_HEALTH_SETUP.md` | Checklist de setup (personal) |
| `GOOGLE_HEALTH_API_PASO_A_PASO.md` | Guía genérica con links |
| `RESUMEN.md` | **Este archivo** |

---

## ⚙️ Cómo funciona el código

### 1. Auth (una sola vez, ya hecha ✅)
```
client_secret.json → navegador Google → Allow → token.json
```
El **refresh token** renueva el access token automáticamente — nunca más te pide login.

### 2. Descarga incremental (`check_and_download.py`)
```
sync_state.json (última fecha) → filtro AIP-160 por fecha civil
→ baja solo lo nuevo (1 día de superposición) → merge por ID de punto
→ actualiza sync_state.json
```
- `--since YYYY-MM-DD` → rango explícito
- `--only <tipos>` → solo esos tipos
- `--full` → todo el historial

### 3. dailyRollUp — acumulado diario (`reporte_2_dias.py`, `panel.py`)
```
POST /v4/users/me/dataTypes/{tipo}/dataPoints:dailyRollUp
{ "range": { "start": {...}, "end": {...} }, "windowSizeDays": 1 }
```
Devuelve **totales por día** (pasos, km, kcal, FC avg/máx/mín, VO2max) —
**sin muestras crudas de 1 segundo**. Es la forma rápida y limpia.

### 4. Generadores web
- `panel.py` → `index.html` (minimalista, interactivo, todo en uno)
- `make_dashboard.py` → `estadisticas.html` (completo, con Top 3 + tabla ordenable)

---

## ✅ Requisitos para correr

```
Python 3.12  ✅ instalado
google-auth, google-auth-oauthlib, requests  ✅ instalados
client_secret.json + token.json  ✅ en el directorio
```

## 🚀 Comandos
```powershell
cd "C:\Users\R\Desktop\projects\fitbit-personal"

python panel.py            # panel minimalista (lo más rápido) ⭐
python reporte_2_dias.py  # resumen 2 días
python check_and_download.py   # sync incremental de todo
python make_dashboard.py       # dashboard completo
```

---

## ⏳ Pendiente
- [ ] Importador `*.jsonl → FitClub` (`POST /api/activities/bulk`)
- [ ] Levantar FitClub con Docker (ranking con amigos)
- [ ] Probar `pytest` en `fitclub/api/`

## 📌 Notas
- `heart-rate.json` (292 MB) son muestras de 1 segundo — **no hacen falta** para los
  reportes (usar dailyRollUp). Se puede borrar para liberar espacio.
- La **Fitbit Web API se apaga el 30/10/2026** — después solo Google Health API.
- Zona horaria: `America/Argentina/Buenos_Aires` (ART, UTC-3).
