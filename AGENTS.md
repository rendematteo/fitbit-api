# 📜 AGENTS.md — Guía para agentes y personas nuevas

> **Si sos un agente IA leyendo este archivo**: tu trabajo es guiar a la
> persona para que baje sus datos de salud de forma segura. Seguí estos pasos.
>
> **Si sos una persona nueva**: este archivo te explica todo. Empezá por
> "Setup para persona nueva".

---

## 🎯 Qué es este proyecto

Pipeline que baja datos de salud de **Google Health API** (ex-Fitbit) y genera
**dashboards web estáticos** (sin servidor, sin Docker para los reportes).

- La data vive en `data/` (gitignored, nunca se sube)
- Los credenciales viven en `.secrets/` (gitignored, nunca se sube)
- Los reportes se generan en `web/` (gitignored, nunca se sube)

---

## 🧩 Skill del proyecto (para agentes OpenCode)

Este repo trae una **skill genérica** en `.opencode/skills/fitbit-health/SKILL.md`
con el runbook completo: setup OAuth, auth, sync, reportes y troubleshooting.

Si sos un agente OpenCode, **cargala** con el tool `skill`:

```json
{ "id": "fitbit-health" }
```

Si tu agente no soporta skills, **leé ese archivo directamente** — es la guía más
actualizada y genérica (sirve para cualquier persona, sin paths hardcodeados).

---

## 🔐 Reglas (OBLIGATORIAS)

1. **Secretos**: siempre en `.secrets/` (que está en `../.secrets/`, hermano del proyecto). NUNCA en la carpeta del proyecto.
2. **NUNCA commitar** secretos — `.gitignore` ya los excluye. Verificá antes de cada commit.
3. **NUNCA compartir** credenciales por chat/email.
4. **Datos de salud**: son personales, se quedan locales. NUNCA subirlos a GitHub.
5. **Commits**: en español, mensaje claro. Revisá `git status` antes de commitear.

---

## 🆕 Setup para persona nueva (guía paso a paso)

> Un agente debe guiar a la persona por estos pasos. Son ~10 minutos.

### Paso 1 — Requisitos
```
Python 3.12  →  https://www.python.org/downloads/
git          →  https://git-scm.com/downloads
```
Verificar: `python --version` y `git --version`

### Paso 2 — Dependencias
```powershell
cd "C:\Users\<TU-USUARIO>\Desktop\projects\fitbit-personal"
pip install -r requirements.txt
```

### Paso 3 — Obtener el `client_secret.json` (OAuth de Google)

La persona necesita su **propio** cliente OAuth de Google Cloud:

1. Ir a https://console.cloud.google.com (con su cuenta Google)
2. **Crear proyecto** (o usar uno existente) → anotar el Project ID
3. **APIs & Services → Library** → buscar **"Google Health API"** → **Enable**
4. **APIs & Services → OAuth consent screen**:
   - User type: **External** → Create
   - App name + email de soporte → Next
   - **Test users → Add users** → el email de su cuenta Google → Save
5. **APIs & Services → Credentials → + CREATE CREDENTIALS → OAuth client ID**
   - Application type: **Desktop application** (importante: permite loopback sin configurar URIs)
   - Create → **Download JSON**
6. Renombrar el archivo a **`client_secret.json`**
7. Ponerlo en **`C:\Users\<TU-USUARIO>\Desktop\projects\.secrets\`** (la carpeta hermana del proyecto)

> ⚠️ Si la API dice "not onboarding new projects", el acceso está restringido.
> Reintentar más tarde. Ver `docs/GOOGLE_HEALTH_API_PASO_A_PASO.md`.

### Paso 4 — Autorizar (una sola vez)
```powershell
python scripts/authorize_google_health.py
```
- Se abre el navegador → iniciar sesión con la cuenta Google → **Allow**
- Se genera `token.json` en `.secrets/`
- ⚠️ **Dura 7 días** en modo Testing. Cuando falle con `invalid_grant`, volvé a
  correr este script. Para que no expire: **Publish app** en OAuth consent screen.

### Paso 5 — Ver los datos
```powershell
python scripts/panel.py           # panel minimalista interactivo
python scripts/plan_vs_real.py    # plan de entrenamiento vs datos reales
python scripts/reporte_2_dias.py # resumen de últimos 2 días
python scripts/make_dashboard.py  # dashboard completo
```

### Paso 6 — Sync incremental (todos los datos)
```powershell
python scripts/check_and_download.py   # baja solo lo nuevo
```

> `heart-rate` (muestras crudas de 1 s, ~160 MB) **se saltea por defecto**. Los
> reportes usan `dailyRollUp` (acumulado diario). Para incluirlo:
> `python scripts/check_and_download.py --with-heart-rate`

---

## 📁 Estructura

```
fitbit-personal/
├── src/               → código compartido (api.py, helpers.py, paths.py)
├── scripts/           → scripts ejecutables
├── data/              → datos (GITIGNORED)
├── web/               → HTML generado (GITIGNORED)
├── docs/              → documentación
├── fitclub/           → app Docker + ranking
├── README.md          → punto de entrada
├── AGENTS.md          → este archivo
├── .gitignore         → protege secretos y datos
└── requirements.txt   → dependencias
```

---

## 🔧 Solución de problemas

| Error | Solución |
|---|---|
| `No existe client_secret.json` | Seguí el Paso 3 (OAuth) |
| `redirect_uri_mismatch` | El cliente debe ser **Desktop application** |
| `403 PERMISSION_DENIED` | Onboarding cerrado — reintentar después |
| `404` | Habilitar "Google Health API" en Library |
| `invalid_grant` / token expirado | El token dura **7 días** en modo Testing. Re-ejecutar `authorize_google_health.py` (no hace falta borrar nada) |
| `ModuleNotFoundError: src` | Correr desde la carpeta del proyecto: `cd fitbit-personal` |

---

## 🚨 Nunca

- Nunca subir credenciales ni datos de salud a git
- Nunca ejecutar scripts que expongan secretos por consola
- Nunca borrar `.secrets/` sin confirmación
- Nunca commitar sin revisar `git status`
