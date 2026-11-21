# 🏃 FitClub — fitbit-personal

> Tus datos de Fitbit/Google Health → dashboards web estáticos, sin servidor.
> Todo local. Sin Docker para los reportes.

**Empezá por acá.** Reglas y setup detallado: [`AGENTS.md`](AGENTS.md).
Skill para agentes: [`.opencode/skills/fitbit-health/SKILL.md`](.opencode/skills/fitbit-health/SKILL.md).

---

## ⚡ Quickstart

```powershell
pip install -r requirements.txt

.\run auth     # 1) autorizar (abre el navegador, una sola vez)
.\run all      # 2) bajar datos + generar dashboards
```

> El token dura **7 días** en modo Testing. Si falla con `invalid_grant`:
> `.\run auth`.

## 📊 Dashboards (abrí el HTML en el navegador)

| Dashboard | Archivo |
|---|---|
| Panel minimalista | `web/index.html` |
| Plan vs Real | `web/plan_vs_real.html` |
| Últimos 2 días | `web/ultimos_2_dias.html` |
| Estadísticas completas | `web/estadisticas.html` |

## 🧰 Comandos

```powershell
.\run auth     # re-autorizar
.\run test     # validar credencial + API
.\run sync     # bajar datos (sin heart-rate)
.\run report   # generar los 4 HTML
.\run all      # sync + report
```

Args extra: `.\run sync --since 2026-10-01`

> Si Windows bloquea el `.ps1` (ExecutionPolicy), usá `.\run.cmd` — mismo comando.

## 📁 Estructura

```
fitbit-personal/
├── src/          # api.py, helpers.py, paths.py
├── scripts/      # flujo actual (auth, sync, reportes)
├── legacy/       # scripts viejos (Fitbit Web API, gRPC) — no usar
├── data/         # datos (gitignored)
├── web/          # HTML generado (gitignored)
├── docs/         # documentación + plan 10K
├── fitclub/      # 🧪 experimental: ranking con amigos (Docker)
├── run.ps1       # atajos
├── AGENTS.md     # reglas + setup
└── .opencode/skills/fitbit-health/   # skill para agentes
```

## 🔐 Seguridad

- Secretos en `../.secrets/` (hermano del repo), **nunca** dentro.
- `data/`, `web/`, `.secrets/` están **gitignored**: no se suben.
- Ver [`AGENTS.md`](AGENTS.md) para el setup OAuth completo.
