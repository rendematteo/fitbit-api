#!/usr/bin/env python3
"""
reporte_2_dias.py — Resumen de los ÚLTIMOS 2 DÍAS vía dailyRollUp
(acumulado diario — sin muestras crudas de 1 segundo).

Genera `web/ultimos_2_dias.html` (web estática).

Uso:
    python reporte_2_dias.py
"""
import json
import os
import sys
from datetime import datetime, timedelta

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
                "hr": num_or_none(ms.get("averageHeartRateBeatsPerMinute")),
                "pace": num_or_none(ms.get("averagePaceSecondsPerMeter")),
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

    # --- HTML ---
    html_days = ""
    for offset in (1, 0):
        key = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        d = days.get(key, {})
        if not d:
            continue
        es_hoy = offset == 0
        titulo = f"{DAYS_ES[(today - timedelta(days=offset)).weekday()]} " \
                 f"{(today - timedelta(days=offset)):%d/%m}"
        if es_hoy:
            titulo += " — hoy (en curso)"
        rows = ""
        if d.get("steps") is not None:
            rows += f'<div class="row"><span class="lbl">👣 Pasos</span><span class="val">{d["steps"]:,.0f}</span></div>'
        if d.get("km") is not None:
            rows += f'<div class="row"><span class="lbl">🛣️ Distancia</span><span class="val">{d["km"]:.2f} km</span></div>'
        if d.get("kcal") is not None:
            rows += f'<div class="row"><span class="lbl">🔥 Calorías totales</span><span class="val">{d["kcal"]:,.0f} kcal</span></div>'
        if d.get("active_min_total") is not None:
            detalle = " + ".join(f"{k.lower()} {v:.0f}" for k, v in sorted(d["active_min"].items()))
            rows += f'<div class="row"><span class="lbl">⏱️ Minutos activos</span><span class="val">{d["active_min_total"]:.0f} min</span><span class="det">{esc(detalle)}</span></div>'
        if d.get("hr_avg") is not None:
            rows += f'<div class="row"><span class="lbl">❤️ FC (avg / máx / mín)</span><span class="val">{d["hr_avg"]:.0f} / {d["hr_max"]:.0f} / {d["hr_min"]:.0f} bpm</span></div>'
        if d.get("resting_hr") is not None:
            rows += f'<div class="row"><span class="lbl">💤 FC en reposo</span><span class="val">{d["resting_hr"]:.0f} bpm</span></div>'
        if d.get("vo2max") is not None:
            rows += f'<div class="row"><span class="lbl">🫁 VO2max</span><span class="val">{d["vo2max"]:.1f} ml/kg/min</span></div>'

        for s in ex_sessions.get(key, []):
            pace = ""
            if s["pace"] and s["pace"] > 0:
                m = int(s["pace"] * 1000 / 60)
                sec = int(round((s["pace"] * 1000 / 60 - m) * 60))
                pace = f" · {m}:{sec:02d}/km"
            rows += f'<div class="row"><span class="lbl">🏃 {s["fecha"]:%H:%M} {s["tipo"]}</span><span class="val">{s["km"]:.2f} km · {s["kcal"]:.0f} kcal{pace}</span></div>'

        night = sleep_by_date.get(key)
        if night:
            rows += f'<div class="row"><span class="lbl">😴 Dormido</span><span class="val">{night["asleep_h"]:.1f} h</span></div>'
            rows += f'<div class="row"><span class="lbl">Deep</span><span class="val">{night["deep_h"]:.1f} h</span></div>'
            rows += f'<div class="row"><span class="lbl">REM</span><span class="val">{night["rem_h"]:.1f} h</span></div>'

        html_days += f"""
<div class="day-card {'hoy' if es_hoy else ''}">
  <h2>{esc(titulo)}</h2>
  {rows or '<p class="muted">sin datos todavía</p>'}
</div>
"""

    ex_html = ""
    for s in [x for k in ex_sessions for x in ex_sessions[k]]:
        pace = ""
        if s["pace"] and s["pace"] > 0:
            m = int(s["pace"] * 1000 / 60)
            sec = int(round((s["pace"] * 1000 / 60 - m) * 60))
            pace = f"{m}:{sec:02d}/km"
        hr_str = f"{s['hr']:.0f}" if s["hr"] else "-"
        ex_html += (
            f"<tr><td>{s['fecha']:%d/%m %H:%M}</td><td>{esc(s['tipo'])}</td>"
            f"<td>{s['km']:.2f} km</td><td>{s['kcal']:.0f} kcal</td>"
            f"<td>{hr_str}</td><td>{pace}</td></tr>"
        )
    if not ex_html:
        ex_html = '<tr><td colspan="5" class="muted">sin entrenamientos en los últimos 2 días</td></tr>'

    sleep_html = ""
    for k, n in sleep_by_date.items():
        fecha = datetime.strptime(k, "%Y-%m-%d").date()
        sleep_html += (
            f"<tr><td>{fecha:%d/%m}</td><td>{n['asleep_h']:.1f} h</td>"
            f"<td>{n['deep_h']:.1f} h</td><td>{n['rem_h']:.1f} h</td></tr>"
        )
    if not sleep_html:
        sleep_html = '<tr><td colspan="4" class="muted">sin datos</td></tr>'

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FitClub — Últimos 2 días</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
       background: linear-gradient(180deg, #FBF9F6 0%, #F4F1EC 100%);
       color: #1C1B1A; padding: 48px 24px; min-height: 100vh; }}
.wrap {{ max-width: 640px; margin: 0 auto; }}
h1 {{ font-family: Georgia, "Times New Roman", serif; font-size: 26px; font-weight: 700;
      letter-spacing: -0.02em; }}
h1 .accent {{ color: #E85D3D; }}
.sub {{ color: #A39E97; font-size: 13px; margin-top: 6px; }}
.header-line {{ height: 3px; width: 44px; border-radius: 2px;
               background: linear-gradient(90deg, #E85D3D, #F0A65A); margin-top: 14px; }}
.days {{ display: flex; gap: 14px; flex-wrap: wrap; margin-top: 28px; }}
.day-card {{ flex: 1; min-width: 300px; background: #fff; border-radius: 16px;
             padding: 18px; border: 1px solid #F0EDE8;
             box-shadow: 0 1px 2px rgba(28,27,26,.03); }}
.day-card.hoy {{ border: 2px solid #c7d2fe; }}
.day-card h2 {{ font-size: 17px; margin-bottom: 12px; }}
.row {{ display: flex; justify-content: space-between; align-items: baseline;
        padding: 7px 0; border-bottom: 1px solid #f1f2f8; font-size: 14px; }}
.row:last-child {{ border-bottom: none; }}
.row .lbl {{ color: #4b5563; }}
.row .val {{ font-weight: 700; color: #1e2235; text-align: right;
             font-variant-numeric: tabular-nums; }}
.row .det {{ display: block; font-size: 11.5px; color: #9ca3af; font-weight: 400; }}
.card {{ background: #fff; border-radius: 16px; padding: 18px; margin-top: 28px;
         border: 1px solid #F0EDE8; box-shadow: 0 1px 2px rgba(28,27,26,.03); }}
.card h2 {{ font-size: 16px; margin-bottom: 10px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; }}
th, td {{ text-align: left; padding: 7px 9px; border-bottom: 1px solid #eef0f6; }}
th {{ color: #6b7280; font-size: 11px; text-transform: uppercase; }}
.muted {{ color: #9ca3af; font-size: 13px; }}
footer {{ text-align: center; color: #C9C4BC; font-size: 12px; margin-top: 40px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Fit<span class="accent">Club</span> — Últimos 2 días</h1>
    <p class="sub">Generado el {datetime.now():%d/%m/%Y %H:%M} · Acumulado diario vía Google Health API (dailyRollUp)</p>
    <div class="header-line"></div>
  </header>
  <div class="days">{html_days}</div>
  <div class="card">
    <h2>🏋️ Entrenamientos (últimos 2 días)</h2>
    <table>
      <tr><th>Fecha</th><th>Tipo</th><th>Km</th><th>Kcal</th><th>Ritmo</th></tr>
      {ex_html}
    </table>
  </div>
  <div class="card">
    <h2>😴 Sueño (últimas noches)</h2>
    <table>
      <tr><th>Noche del</th><th>Dormido</th><th>Deep</th><th>REM</th></tr>
      {sleep_html}
    </table>
  </div>
  <footer>FitClub · python scripts/reporte_2_dias.py</footer>
</div>
</body>
</html>
"""

    with open(os.path.join(WEB_DIR, "ultimos_2_dias.html"), "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ {os.path.join(WEB_DIR, 'ultimos_2_dias.html')}")
    for offset in (1, 0):
        key = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        d = days.get(key, {})
        if not d:
            continue
        etiqueta = "HOY " if offset == 0 else "AYER"
        partes = []
        if d.get("steps") is not None:
            partes.append(f"{d['steps']:,.0f} pasos")
        if d.get("km") is not None:
            partes.append(f"{d['km']:.2f} km")
        if d.get("kcal") is not None:
            partes.append(f"{d['kcal']:,.0f} kcal")
        if d.get("active_min_total") is not None:
            partes.append(f"{d['active_min_total']:.0f} min activos")
        if d.get("hr_avg") is not None:
            partes.append(f"FC {d['hr_avg']:.0f}/{d['hr_max']:.0f}")
        if d.get("vo2max") is not None:
            partes.append(f"VO2max {d['vo2max']:.1f}")
        if d.get("resting_hr") is not None:
            partes.append(f"reposo {d['resting_hr']:.0f}")
        print(f"  {etiqueta} {key}: " + " | ".join(partes))
    print(f"  Entrenamientos: {sum(len(v) for v in ex_sessions.values())} | Noches: {len(sleep_by_date)}")


if __name__ == "__main__":
    main()
