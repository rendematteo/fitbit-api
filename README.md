# 🏃 FitClub — fitbit-personal

> Tus datos de Fitbit/Google Health → dashboards web estáticos, sin servidor.
> Todo local, sin Docker para los reportes. Estilo GitHub.

**Empezá por acá.** Las reglas están en [`AGENTS.md`](AGENTS.md). La documentación detallada en [`docs/RESUMEN.md`](docs/RESUMEN.md).

---

## 👋 ¿Sos Sonico o Cotis? (o cualquiera que quiere sus datos)

1. **Abrí una terminal en el repo** y pedile a tu agente IA:
   > *"Leé AGENTS.md y guiame para bajar mis datos de Google Health"*
2. El agente te guía para:
   - Instalar Python + dependencias
   - Crear **tu propio** `client_secret.json` (OAuth Desktop, ~5 min)
   - Autorizar (`authorize_google_health.py`)
   - Bajar tus datos (`check_and_download.py`)
   - Generar tus dashboards (`panel.py`, `plan_vs_real.py`)
3. **Tus datos y credenciales nunca salen de tu máquina** (`.gitignore` los protege).

> 🔐 Cada persona usa su **propio** proyecto de Google Cloud y su **propia**
> carpeta `.secrets/`. No se comparten credenciales.

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
Se abre el navegador → Allow → se genera `token.json` en `.secrets/`.

> ⚠️ **El token dura 7 días** si el OAuth consent screen está en modo **Testing**
> (Google invalida el refresh token). Cuando aparezca `invalid_grant`, volvé a
> correr `authorize_google_health.py`. Para que no expire: OAuth consent screen
> → **Publish app** (con scopes restringidos puede pedir verificación; para uso
> personal alcanza con re-autorizar cada 7 días).

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

> `heart-rate` (muestras crudas de 1 segundo, ~160 MB) **se saltea por defecto**
> porque los reportes usan el acumulado diario (`dailyRollUp`). Si lo querés igual:
> `python scripts/check_and_download.py --with-heart-rate`

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
- `heart-rate.json` (~160 MB) son muestras crudas de 1 segundo — **no hacen falta**
  para los reportes (usan `dailyRollUp`). El sync lo **saltea por defecto**; si ya
  lo tenés, se puede borrar.
- Las credenciales (`client_secret.json`, `token.json`) viven en `.secrets/` y
  **nunca se comparten ni se commitean** (ver `AGENTS.md`).
