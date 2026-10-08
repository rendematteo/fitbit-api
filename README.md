# 🏃 FitClub — fitbit-personal

> Tus datos de Fitbit/Google Health → dashboards web estáticos, sin servidor.
> Todo local, sin Docker para los reportes. Estilo GitHub.

**Empezá por acá.** Las reglas están en [`AGENTS.md`](AGENTS.md). La documentación detallada en [`docs/RESUMEN.md`](docs/RESUMEN.md).

---

## 📁 Estructura (estilo repo)

```
fitbit-personal/
├── README.md              ← estás acá
├── AGENTS.md              ← 📜 reglas del proyecto
├── .gitignore             ← 🔐 secretos y datos NUNCA se suben
├── requirements.txt       ← dependencias Python
│
├── src/                   ← 📦 código compartido (módulos)
│   ├── api.py             ← cliente Google Health API (auth, dailyRollUp, list)
│   ├── helpers.py         ← funciones auxiliares
│   └── paths.py           ← rutas centralizadas
│
├── scripts/               ← 🚀 scripts ejecutables
│   ├── panel.py           ← panel minimalista interactivo ⭐
│   ├── plan_vs_real.py    ← ⭐ plan de entrenamiento vs datos reales
│   ├── reporte_2_dias.py ← resumen de últimos 2 días
│   ├── check_and_download.py ← descarga incremental
│   ├── make_dashboard.py  ← dashboard completo
│   ├── google_health_sync.py ← sync gRPC (alternativo)
│   ├── fitbit_daily_sync.py  ← sync Fitbit Web API (puente)
│   ├── authorize_google_health.py / authorize_fitbit.py ← OAuth one-time
│   └── import_json_export.py ← backfill desde export JSON
│
├── data/                  ← 📊 datos (en .gitignore)
│   ├── descargas_google_health/  ← bajados de la API
│   └── takeout/           ← export CSV de Google Health (Plan_10K)
│
├── web/                   ← 🌐 HTML generado (estático)
│   ├── index.html         ← panel minimalista
│   ├── estadisticas.html  ← dashboard completo
│   ├── ultimos_2_dias.html
│   └── plan_vs_real.html
│
├── docs/                  ← 📄 documentación
│   ├── RESUMEN.md  ESTADO_PROYECTO.md
│   ├── GOOGLE_HEALTH_API_PASO_A_PASO.md  GOOGLE_HEALTH_SETUP.md
│   └── plan_10k_28nov.csv ← plan de entrenamiento 10K
│
└── fitclub/               ← app (Docker + ranking con amigos)
```

**Los secretos viven afuera, en `../.secrets/`** (junto al proyecto, nunca adentro).

---

## 🔐 Cómo obtener el `client_secret.json` (OAuth)

> Para que **otra persona** levante el proyecto, necesita su propio
> `client_secret.json`. Son 5 minutos:

1. **Google Cloud Console** → https://console.cloud.google.com
2. **Crear proyecto** (o usar uno) → anotar el **Project ID**
3. **APIs & Services → Library** → buscar **"Google Health API"** → **Enable**
4. **APIs & Services → OAuth consent screen**:
   - User type: **External** → Create
   - App name + email → Next
   - **Test users → Add users** → el email de la cuenta Google → Save
5. **APIs & Services → Credentials → + CREATE CREDENTIALS → OAuth client ID**
   - Application type: **Desktop application** ← (importante: permite loopback sin configurar URIs)
   - Create → **Download JSON**
6. Renombrar a **`client_secret.json`** y ponerlo en **`C:\Users\R\Desktop\projects\.secrets\`**

> ⚠️ Si la API dice "not onboarding new projects", el acceso está restringido.
> Ver [`docs/GOOGLE_HEALTH_API_PASO_A_PASO.md`](docs/GOOGLE_HEALTH_API_PASO_A_PASO.md).

---

## 🚀 Cómo levantarlo

### Requisitos
```
Python 3.12
pip install -r requirements.txt
```

### 1. Autorizar (una sola vez)
```powershell
cd "C:\Users\R\Desktop\projects\fitbit-personal"
python scripts/authorize_google_health.py
```
Se abre el navegador → Allow → se genera `token.json` en `.secrets/`. **Nunca más login.**

### 2. Ver tus datos
```powershell
python scripts/panel.py           # panel minimalista interactivo ⭐
python scripts/plan_vs_real.py    # ⭐ plan vs datos reales
python scripts/reporte_2_dias.py # resumen 2 días
python scripts/make_dashboard.py  # dashboard completo
```

### 3. Sync incremental (todos los datos)
```powershell
python scripts/check_and_download.py   # baja solo lo nuevo (estado + merge)
```

---

## 🔄 Flujo de datos

```
Google Health API
   ↓  (dailyRollUp = acumulado diario, o list = datos crudos)
data/descargas_google_health/*.json
   ↓
scripts/ (panel, plan_vs_real, make_dashboard, ...)
   ↓
web/*.html  (web estática, sin servidor)
```

---

## 📌 Notas

- **Zona horaria:** `America/Argentina/Buenos_Aires` (ART, UTC-3)
- **Fitbit Web API se apaga el 30/10/2026** — después solo Google Health API
- `heart-rate.json` (292 MB) son muestras de 1 segundo — no hacen falta para los
  reportes (usar dailyRollUp). Se puede borrar.
- Las credenciales (`client_secret.json`, `token.json`) viven en `.secrets/` y
  **nunca se comparten ni se commitean** (ver `AGENTS.md`).
