#!/usr/bin/env python3
"""
panel.py — Genera `web/index.html`: panel MINIMALISTA e INTERACTIVO de los
últimos 2 días. Todo en una sola página: se ve lo esencial y se clickea
para expandir el detalle.

Uso:
    python panel.py
"""
import json
import os
import sys
from datetime import datetime, timedelta

# path bootstrap para importar src/ (estamos en scripts/)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api import get_creds, daily_rollup, list_daily
from src.helpers import (num, num_or_none, esc, day_key, rollup_sum,
                         load_local, pace_str, civil_key, fmt_date)
from src.paths import SECRETS_DIR, DATA_DIR, WEB_DIR

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROLLUP_TYPES = ["steps", "distance", "total-calories", "active-minutes",
                "heart-rate", "run-vo2-max"]
DAYS_ES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


def main():
    creds = get_creds(SECRETS_DIR)
    hoy = datetime.now().date()
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    inicio = today - timedelta(days=2)
    fin = today + timedelta(days=1)

    def civil(dt):
        return {"date": {"year": dt.year, "month": dt.month, "day": dt.day},
                "time": {"hours": 0, "minutes": 0, "seconds": 0}}

    body = {"range": {"start": civil(inicio), "end": civil(fin)},
            "windowSizeDays": 1, "pageSize": 10}

    # --- rollups diarios ---
    days = {}
    for dt in ROLLUP_TYPES:
        for p in daily_rollup(creds, dt, body):
            key = day_key(p.get("civilStartTime"))
            if not key:
                continue
            d = days.setdefault(key, {})
            if dt == "steps":
                d["steps"] = rollup_sum(p.get("steps"))
            elif dt == "distance":
                v = rollup_sum(p.get("distance"))
                d["km"] = v / 1e6 if v is not None else None
            elif dt == "total-calories":
                d["kcal"] = rollup_sum(p.get("totalCalories"))
            elif dt == "active-minutes":
                niveles = (p.get("activeMinutes") or {}).get(
                    "activeMinutesRollupByActivityLevel") or []
                d["active_min"] = {
                    (n.get("activityLevel") or "?").title(): num(n.get("activeMinutesSum"))
                    for n in niveles}
                d["active_min_total"] = sum(d["active_min"].values())
            elif dt == "heart-rate":
                hr = p.get("heartRate") or {}
                d["hr_avg"] = num_or_none(hr.get("beatsPerMinuteAvg"))
                d["hr_max"] = num_or_none(hr.get("beatsPerMinuteMax"))
                d["hr_min"] = num_or_none(hr.get("beatsPerMinuteMin"))
            elif dt == "run-vo2-max":
                v = p.get("runVo2Max") or {}
                d["vo2max"] = num_or_none(v.get("rateAvg"))

    # --- FC reposo (list, no soporta rollup) ---
    since = (today - timedelta(days=2)).strftime("%Y-%m-%d")
    for p in list_daily(creds, "daily-resting-heart-rate", since,
                         'daily_resting_heart_rate.date >= "{since}"'):
        d = p.get("dailyRestingHeartRate") or {}
        key = day_key(d.get("date"))
        if key and key in days:
            days[key]["resting_hr"] = num_or_none(d.get("beatsPerMinute"))

    # --- entrenamientos (local) ---
    ex_sessions = {}
    for dp in load_local(DATA_DIR, "exercise"):
        ex = dp.get("exercise") or {}
        iv = ex.get("interval") or {}
        st = iv.get("startTime")
        if not st:
            continue
        try:
            s = datetime.fromisoformat(st.replace("Z", "+00:00"))
            off = iv.get("startUtcOffset")
            if off:
                s += timedelta(seconds=int(str(off).replace("s", "")))
        except ValueError:
            continue
        if s.date() >= (today - timedelta(days=2)).date():
            ms = ex.get("metricsSummary") or {}
            ex_sessions.setdefault(s.date().isoformat(), []).append({
                "fecha": s,
                "tipo": (ex.get("exerciseType") or "OTRO").replace("_", " ").title(),
                "km": num(ms.get("distanceMillimeters")) / 1e6,
                "kcal": num(ms.get("caloriesKcal")),
            })

    # --- sueño (local) ---
    sleep_by_date = {}
    for dp in load_local(DATA_DIR, "sleep"):
        sl = dp.get("sleep") or {}
        iv = sl.get("interval") or {}
        et = iv.get("endTime")
        if not et:
            continue
        try:
            e = datetime.fromisoformat(et.replace("Z", "+00:00"))
        except ValueError:
            continue
        if e.date() >= (today - timedelta(days=2)).date():
            stage_min = {}
            for stg in sl.get("stages") or []:
                s, en = stg.get("startTime"), stg.get("endTime")
                if not s or not en:
                    continue
                try:
                    sv = datetime.fromisoformat(s.replace("Z", "+00:00"))
                    ev = datetime.fromisoformat(en.replace("Z", "+00:00"))
                except ValueError:
                    continue
                t = stg.get("type", "OTHER").upper()
                stage_min[t] = stage_min.get(t, 0.0) + (ev - sv).total_seconds() / 60.0
            sleep_by_date[e.date().isoformat()] = {
                "asleep_h": sum(v for k, v in stage_min.items() if k != "AWAKE") / 60.0,
                "deep_h": stage_min.get("DEEP", 0.0) / 60.0,
                "rem_h": stage_min.get("REM", 0.0) / 60.0,
            }

    # --- armar datos para JS ---
    dias_js = []
    for offset in (1, 0):  # ayer, hoy
        key = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        d = days.get(key, {})
        if not d:
            continue
        es_hoy = offset == 0
        titulo = f"{DAYS_ES[(today - timedelta(days=offset)).weekday()]} " \
                 f"{(today - timedelta(days=offset)):%d/%m}"
        if es_hoy:
            titulo += " · hoy"

        metrics = []
        if d.get("steps") is not None:
            metrics.append({"lbl": "Pasos", "val": f"{d['steps']:,.0f}"})
        if d.get("km") is not None:
            metrics.append({"lbl": "Km", "val": f"{d['km']:.2f}"})
        if d.get("kcal") is not None:
            metrics.append({"lbl": "Kcal", "val": f"{d['kcal']:,.0f}"})
        if d.get("hr_avg") is not None:
            metrics.append({"lbl": "FC", "val": f"{d['hr_avg']:.0f}"})

        detail = []
        if d.get("active_min_total") is not None:
            detalle = " + ".join(f"{k.lower()} {v:.0f}" for k, v in sorted(d["active_min"].items()))
            detail.append({"lbl": "Minutos activos", "val": f"{d['active_min_total']:.0f} min",
                           "sub": detalle})
        if d.get("hr_avg") is not None:
            detail.append({"lbl": "FC avg / máx / mín",
                           "val": f"{d['hr_avg']:.0f} / {d['hr_max']:.0f} / {d['hr_min']:.0f}",
                           "sub": "bpm"})
        if d.get("resting_hr") is not None:
            detail.append({"lbl": "FC en reposo", "val": f"{d['resting_hr']:.0f}", "sub": "bpm"})
        if d.get("vo2max") is not None:
            detail.append({"lbl": "VO2max", "val": f"{d['vo2max']:.1f}", "sub": "ml/kg/min"})

        for s in ex_sessions.get(key, []):
            detail.append({"sec": "ENTRENAMIENTOS"})
            detail.append({"lbl": f"{s['fecha']:%H:%M} {s['tipo']}",
                           "val": f"{s['km']:.2f} km · {s['kcal']:.0f} kcal", "sub": ""})
            break
        for s in ex_sessions.get(key, []):
            detail.append({"lbl": f"{s['fecha']:%H:%M} {s['tipo']}",
                           "val": f"{s['km']:.2f} km · {s['kcal']:.0f} kcal", "sub": ""})

        night = sleep_by_date.get(key)
        if night:
            detail.append({"sec": "SUEÑO"})
            detail.append({"lbl": "Dormido", "val": f"{night['asleep_h']:.1f} h", "sub": ""})
            detail.append({"lbl": "Deep", "val": f"{night['deep_h']:.1f} h", "sub": ""})
            detail.append({"lbl": "REM", "val": f"{night['rem_h']:.1f} h", "sub": ""})

        dias_js.append({"titulo": titulo, "metrics": metrics, "detail": detail})

    # ---------------- HTML ----------------
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FitClub</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
       background: linear-gradient(180deg, #FBF9F6 0%, #F4F1EC 100%);
       color: #1C1B1A; padding: 56px 24px; min-height: 100vh; }}
.wrap {{ max-width: 600px; margin: 0 auto; }}
header {{ margin-bottom: 26px; }}
h1 {{ font-family: Georgia, "Times New Roman", serif; font-size: 28px; font-weight: 700;
      letter-spacing: -0.02em; }}
h1 .accent {{ color: #E85D3D; }}
.sub {{ color: #A39E97; font-size: 13px; margin-top: 6px; }}
.header-line {{ height: 3px; width: 44px; border-radius: 2px;
               background: linear-gradient(90deg, #E85D3D, #F0A65A); margin-top: 14px; }}
.day {{ background: #fff; border-radius: 20px; padding: 22px 24px;
        margin-bottom: 14px; border: 1px solid #F0EDE8;
        box-shadow: 0 1px 2px rgba(28,27,26,.03), 0 4px 14px rgba(28,27,26,.04);
        cursor: pointer; transition: transform 0.18s ease, box-shadow 0.18s ease; }}
.day:hover {{ transform: translateY(-2px);
              box-shadow: 0 2px 4px rgba(28,27,26,.04), 0 10px 26px rgba(28,27,26,.07); }}
.day-head {{ display: flex; justify-content: space-between; align-items: center; }}
.day-title {{ font-size: 12px; font-weight: 600; color: #A39E97;
              text-transform: uppercase; letter-spacing: 0.08em; }}
.day-chevron {{ color: #D6D2CB; font-size: 12px; transition: all 0.25s ease; }}
.day.open .day-chevron {{ transform: rotate(180deg); color: #E85D3D; }}
.day-metrics {{ display: flex; margin-top: 16px; }}
.metric {{ flex: 1; }}
.metric + .metric {{ border-left: 1px solid #F5F2ED; padding-left: 18px; margin-left: 18px; }}
.metric .m-lbl {{ font-size: 10px; color: #B0ABA3; text-transform: uppercase; letter-spacing: 0.06em; }}
.metric .m-val {{ font-size: 26px; font-weight: 700; letter-spacing: -0.02em;
                 font-variant-numeric: tabular-nums; margin-top: 3px; }}
.metric.hero .m-val {{ color: #E85D3D; }}
.day-detail {{ display: none; margin-top: 18px; padding-top: 16px;
               border-top: 1px solid #F5F2ED; }}
.day.open .day-detail {{ display: block; }}
.detail-sec {{ font-size: 10px; color: #B0ABA3; text-transform: uppercase;
               letter-spacing: 0.07em; margin: 14px 0 4px; }}
.detail-row {{ display: flex; justify-content: space-between; padding: 6px 0; font-size: 14px; }}
.detail-row .d-lbl {{ color: #6E6A64; }}
.detail-row .d-val {{ font-weight: 600; font-variant-numeric: tabular-nums; }}
.detail-row .d-sub {{ display: block; font-size: 11px; color: #B0ABA3; font-weight: 400; }}
footer {{ text-align: center; color: #C9C4BC; font-size: 12px; margin-top: 32px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Fit<span class="accent">Club</span></h1>
    <p class="sub">Últimos 2 días · {datetime.now():%d/%m/%Y %H:%M} · clickeá un día para ver el detalle</p>
    <div class="header-line"></div>
  </header>
  <div id="dias"></div>
  <footer>FitClub · python scripts/panel.py</footer>
</div>
<script>
const DIAS = {json.dumps(dias_js, ensure_ascii=False)};
const cont = document.getElementById('dias');
cont.innerHTML = DIAS.map(d => {{
  const metrics = d.metrics.map((m, i) =>
    `<div class="metric${{i === 0 ? ' hero' : ''}}"><div class="m-lbl">${{m.lbl}}</div><div class="m-val">${{m.val}}</div></div>`).join('');
  const detail = d.detail.map(r => {{
    if (r.sec) return `<div class="detail-sec">${{r.sec}}</div>`;
    const sub = r.sub ? `<span class="d-sub">${{r.sub}}</span>` : "";
    return `<div class="detail-row"><span class="d-lbl">${{r.lbl}}</span><span class="d-val">${{r.val}}${{sub}}</span></div>`;
  }}).join('');
  return `<div class="day">
    <div class="day-head">
      <span class="day-title">${{d.titulo}}</span>
      <span class="day-chevron">▾</span>
    </div>
    <div class="day-metrics">${{metrics}}</div>
    <div class="day-detail">${{detail}}</div>
  </div>`;
}}).join('');
cont.querySelectorAll('.day').forEach(el => {{
  el.addEventListener('click', () => el.classList.toggle('open'));
}});
</script>
</body>
</html>
"""

    with open(os.path.join(WEB_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    # ---------------- consola ----------------
    print(f"✅ {os.path.join(WEB_DIR, 'index.html')}")
    for d in dias_js:
        m = " · ".join(f"{x['lbl']} {x['val']}" for x in d["metrics"])
        print(f"  {d['titulo']}: {m}")


if __name__ == "__main__":
    main()
