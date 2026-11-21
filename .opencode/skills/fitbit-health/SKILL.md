---
name: Fitbit / Google Health Pipeline
description: Runbook genérico para configurar, autorizar, sincronizar y generar dashboards con datos de Google Health API (ex-Fitbit). Usala cuando el usuario quiera bajar sus datos de salud, arreglar errores de autenticación (invalid_grant, PermissionError, redirect_uri_mismatch, 403, 404), correr los scripts de scripts/, o regenerar los reportes de web/.
---

# Fitbit / Google Health Pipeline

Runbook **genérico** para cualquier persona que use este repo. Corré **siempre**
desde la raíz del repo.

## Cuándo usar esta skill

- Bajar datos de salud (pasos, km, sueño, FC, VO2max, peso, actividades).
- Arreglar errores de auth (`invalid_grant`, `PermissionError`, `redirect_uri_mismatch`, 403, 404).
- Correr o debuggear los scripts de `scripts/`.
- Generar/regenerar los dashboards de `web/`.

## 🔐 Reglas de seguridad (OBLIGATORIAS)

1. **Secretos** en `../.secrets/` (carpeta **hermana** del repo), NUNCA dentro.
2. **NUNCA** commitear `data/`, `web/`, `.secrets/`, `token.json`,
   `client_secret.json`, `sync_state.json`.
3. **NUNCA** compartir credenciales por chat/email.
4. Antes de cada commit: `git status --short` y verificar que no haya datos.

## Prerequisitos

```powershell
python --version          # 3.12+
pip install -r requirements.txt
```

## Paso 1 — OAuth (una sola vez por persona)

Cada persona usa **su propio** proyecto de Google Cloud:

1. https://console.cloud.google.com → crear/elegir proyecto.
2. **APIs & Services → Library** → habilitar **"Google Health API"**.
3. **OAuth consent screen**: External → nombre + email → **Test users → Add users** → tu email.
4. **Credentials → Create credentials → OAuth client ID** → tipo **Desktop application** → **Download JSON**.
5. Renombrar a `client_secret.json` y ponerlo en `../.secrets/`.

> Si dice "not onboarding new projects", reintentar más tarde (403).

## Paso 2 — Autorizar (una sola vez, dura ~7 días)

```powershell
python scripts/authorize_google_health.py
```

- Abre el navegador → elegir cuenta → **Allow**.
- Guarda `token.json` en `../.secrets/`.
- ⚠️ En modo **Testing** el refresh token dura **7 días**. Si falla con
  `invalid_grant`, volvé a correr el script (no hace falta borrar nada).
  Para que no expire: **Publish app** en OAuth consent screen.

## Paso 3 — Sync de datos

```powershell
python scripts/check_and_download.py                        # incremental, SIN heart-rate
python scripts/check_and_download.py --since 2026-10-01     # desde una fecha
python scripts/check_and_download.py --full                 # todo el historial
python scripts/check_and_download.py --only exercise sleep  # solo esos tipos
python scripts/check_and_download.py --with-heart-rate      # incluir heart-rate (~160 MB)
```

- `heart-rate` (muestras crudas de 1 s) se **saltea por defecto**; los reportes usan
  `dailyRollUp` (acumulado diario).
- `total-calories` solo soporta rollup/dailyRollup, **NO** list (devuelve 400). Es normal.
- Estado incremental en `../.secrets/sync_state.json`; merge por `name` (sin duplicados).
- Datos → `data/descargas_google_health/*.json`.

## Paso 4 — Reportes (HTML estático)

```powershell
python scripts/panel.py           # web/index.html — panel minimalista
python scripts/plan_vs_real.py    # web/plan_vs_real.html — plan vs real
python scripts/reporte_2_dias.py  # web/ultimos_2_dias.html — últimos 2 días
python scripts/make_dashboard.py  # web/estadisticas.html — dashboard completo
```

- Todo estático: abrí el HTML en el navegador, no necesita servidor.
- `web/` está gitignored (contiene datos personales).

## 🧪 Verificación rápida

```powershell
python scripts/check_and_download.py --test   # 1 llamada: valida credencial + API
```

## 🔧 Troubleshooting

| Síntoma | Causa / Solución |
|---|---|
| `invalid_grant` | Token de 7 días vencido → `authorize_google_health.py` |
| `PermissionError ... token.json` | Archivo memory-mapped; el script usa escritura atómica (temp + replace). Si persiste, cerrá editores que lo tengan abierto |
| `UnicodeEncodeError` en consola | El script ya fuerza UTF-8; si no, `set PYTHONUTF8=1` |
| `redirect_uri_mismatch` | El cliente debe ser **Desktop application** |
| `403 PERMISSION_DENIED` | Onboarding cerrado → reintentar más tarde |
| `404` | Habilitar "Google Health API" en Library |
| `No existe client_secret.json` | Falta el Paso 1 (OAuth) |
| `ModuleNotFoundError: src` | Correr desde la raíz del repo |
| `total-calories` HTTP 400 | Normal: solo soporta rollup, no list |
| `steps`/`distance` 503 | Retry con backoff (ya implementado en `src/api.py`) |

## 📁 Dónde está qué

- `src/api.py` — cliente REST (auth, `daily_rollup`, `list_daily`).
- `src/paths.py` — rutas (`SECRETS_DIR`, `DATA_DIR`, `WEB_DIR`, `PLAN_CSV`).
- `scripts/` — ejecutables.
- `data/` — datos (gitignored).
- `web/` — HTML generado (gitignored).
- `../.secrets/` — credenciales (gitignored, fuera del repo).

## 🔗 Referencias

- Detalles de la API: [`references/api.md`](references/api.md)
