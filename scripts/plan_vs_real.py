#!/usr/bin/env python3
"""
plan_vs_real.py — Cruza el plan de entrenamiento (docs/plan_10k_28nov.csv)
con los datos reales de salud (Google Health API vía dailyRollUp + exercise.json).

Genera `web/plan_vs_real.html`: por cada sesión planeada, muestra si se hizo,
cómo fue, y las métricas reales vs las planeadas.

Uso:
    python plan_vs_real.py
"""
import csv
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api import get_creds, daily_rollup, list_daily
from src.helpers import (num, num_or_none, esc, day_key, rollup_sum,
                         load_local, pace_str, civil_key, fmt_date)
from src.paths import SECRETS_DIR, DATA_DIR, WEB_DIR, PLAN_CSV

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
         "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12}
DAYS_ES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


def parse_plan():
    sesiones = []
    with open(PLAN_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            dia = row.get("Día", "").strip()
            fecha_str = None
            for p in dia.split():
                if "/" in p:
                    fecha_str = p
                    break
            if not fecha_str:
                continue
            try:
                d, m = fecha_str.split("/")
                fecha = datetime(2026, MESES[m.lower()], int(d)).date()
            except (ValueError, KeyError):
                continue
            sesiones.append({
                "semana": row.get("Semana", ""),
                "fase": row.get("Fase", ""),
                "dia": dia,
                "fecha": fecha,
                "sesion": row.get("Sesión", ""),
                "detalle": row.get("Detalle", ""),
                "duracion": row.get("Duración", ""),
                "rpe": row.get("RPE", ""),
                "zona": row.get("Zona HR", ""),
                "fc_obj": row.get("FC objetivo (HRmáx 181)", ""),
                "objetivo": row.get("Objetivo", ""),
            })
    return sesiones


def main():
    creds = get_creds(SECRETS_DIR)
    sesiones = parse_plan()
    if not sesiones:
        print("❌ No se pudo leer el plan")
        return

    fechas = [s["fecha"] for s in sesiones]
    inicio = min(fechas)
    fin = max(fechas) + timedelta(days=1)
    hoy = datetime.now().date()

    print(f"📅 Plan: {inicio:%d/%m} → {fin:%d/%m} ({len(sesiones)} sesiones)")

    def civil(dt):
        return {"date": {"year": dt.year, "month": dt.month, "day": dt.day},
                "time": {"hours": 0, "minutes": 0, "seconds": 0}}

    body = {"range": {"start": civil(inicio), "end": civil(fin)},
            "windowSizeDays": 1, "pageSize": 100}

    # --- dailyRollUp para todo el plan ---
    days = {}
    for dt in ["steps", "distance", "total-calories", "active-minutes", "heart-rate"]:
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
                d["active_min_total"] = sum(
                    num(n.get("activeMinutesSum")) for n in niveles)
            elif dt == "heart-rate":
                hr = p.get("heartRate") or {}
                d["hr_avg"] = num_or_none(hr.get("beatsPerMinuteAvg"))
                d["hr_max"] = num_or_none(hr.get("beatsPerMinuteMax"))
        print(f"  ✅ {dt}")

    # --- FC reposo (list, no soporta rollup) ---
    since = (hoy - timedelta(days=2)).strftime("%Y-%m-%d")
    for p in list_daily(creds, "daily-resting-heart-rate", since,
                         'daily_resting_heart_rate.date >= "{since}"'):
        d = p.get("dailyRestingHeartRate") or {}
        key = day_key(d.get("date"))
        if key and key in days:
            days[key]["resting_hr"] = num_or_none(d.get("beatsPerMinute"))

    # --- entrenamientos reales (local) ---
    ex_by_date = {}
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
        ms = ex.get("metricsSummary") or {}
        ex_by_date.setdefault(s.date().isoformat(), []).append({
            "tipo": (ex.get("exerciseType") or "OTRO").replace("_", " ").title(),
            "hora": s,
            "km": num(ms.get("distanceMillimeters")) / 1e6,
            "kcal": num(ms.get("caloriesKcal")),
            "hr": num_or_none(ms.get("averageHeartRateBeatsPerMinute")),
            "pace": num_or_none(ms.get("averagePaceSecondsPerMeter")),
        })

    # --- actividad reciente (últimos 7 días) ---
    reciente_inicio = hoy - timedelta(days=7)
    body_rec = {"range": {"start": civil(reciente_inicio), "end": civil(fin)},
                "windowSizeDays": 1, "pageSize": 100}
    reciente = {}
    for dt in ["steps", "distance", "total-calories", "heart-rate"]:
        for p in daily_rollup(creds, dt, body_rec):
            key = day_key(p.get("civilStartTime"))
            if not key:
                continue
            d = reciente.setdefault(key, {})
            if dt == "steps":
                d["steps"] = rollup_sum(p.get("steps"))
            elif dt == "distance":
                v = rollup_sum(p.get("distance"))
                d["km"] = v / 1e6 if v is not None else None
            elif dt == "total-calories":
                d["kcal"] = rollup_sum(p.get("totalCalories"))
            elif dt == "heart-rate":
                hr = p.get("heartRate") or {}
                d["hr_avg"] = num_or_none(hr.get("beatsPerMinuteAvg"))

    # --- cruzar plan vs real ---
    for s in sesiones:
        key = s["fecha"].isoformat()
        s["actual"] = days.get(key, {})
        s["sessions"] = ex_by_date.get(key, [])
        es_descanso = "descanso" in s["sesion"].lower() or "pilates" in s["sesion"].lower()
        if s["fecha"] < hoy:
            if s["sessions"]:
                s["status"] = "done"
            elif es_descanso:
                s["status"] = "rest"
            else:
                s["status"] = "missed"
        elif s["fecha"] == hoy:
            s["status"] = "today"
        else:
            s["status"] = "upcoming"

    # --- agrupar por semana ---
    semanas = {}
    for s in sesiones:
        semanas.setdefault(s["semana"], []).append(s)

    # --- HTML ---
    STATUS = {
        "done": ("✅", "hecho"),
        "missed": ("❌", "perdido"),
        "rest": ("😴", "descanso"),
        "today": ("⏳", "hoy"),
        "upcoming": ("·", "próximo"),
    }

    semanas_html = ""
    for semana, ses in semanas.items():
        fase = ses[0]["fase"]
        dias_html = ""
        for s in ses:
            icono, lbl_status = STATUS[s["status"]]
            actual = s["actual"]
            real_bits = []
            if actual.get("steps") is not None:
                real_bits.append(f"{actual['steps']:,.0f} pasos")
            if actual.get("km") is not None:
                real_bits.append(f"{actual['km']:.2f} km")
            if actual.get("kcal") is not None:
                real_bits.append(f"{actual['kcal']:,.0f} kcal")
            if actual.get("hr_avg") is not None:
                real_bits.append(f"FC {actual['hr_avg']:.0f}")
            real = " · ".join(real_bits) if real_bits else "—"

            sessions_html = ""
            for e in s["sessions"]:
                pace = ""
                if e["pace"] and e["pace"] > 0:
                    m = int(e["pace"] * 1000 / 60)
                    sec = int(round((e["pace"] * 1000 / 60 - m) * 60))
                    pace = f" · {m}:{sec:02d}/km"
                sessions_html += (
                    f'<div class="sess"><span class="sess-t">{e["hora"]:%H:%M} {esc(e["tipo"])}</span>'
                    f'<span class="sess-v">{e["km"]:.2f} km · {e["kcal"]:.0f} kcal'
                    f'{" · " + str(int(e["hr"])) + " bpm" if e["hr"] else ""}{pace}</span></div>'
                )

            plan_txt = s["sesion"]
            if s["duracion"]:
                plan_txt += f" · {s['duracion']}"
            if s["zona"]:
                plan_txt += f" · {s['zona']}"

            dias_html += f"""
<div class="pday {s['status']}">
  <div class="pday-head">
    <span class="pday-fecha">{s['dia']}</span>
    <span class="pday-status">{icono} {lbl_status}</span>
  </div>
  <div class="pday-plan">{esc(plan_txt)}</div>
  <div class="pday-real">{esc(real)}</div>
  {sessions_html}
</div>"""
        semanas_html += f"""
<div class="semana">
  <h2>{semana} <span class="fase">{fase}</span></h2>
  {dias_html}
</div>"""

    # --- sección: actividad reciente ---
    reciente_html = '<div class="recent"><h2>Tu actividad reciente</h2>'
    for offset in range(6, -1, -1):
        key = (hoy - timedelta(days=offset)).isoformat()
        d = reciente.get(key, {})
        fecha = hoy - timedelta(days=offset)
        titulo = f"{DAYS_ES[fecha.weekday()]} {fecha:%d/%m}"
        if offset == 0:
            titulo += " · hoy"
        bits = []
        if d.get("steps") is not None:
            bits.append(f"{d['steps']:,.0f} pasos")
        if d.get("km") is not None:
            bits.append(f"{d['km']:.2f} km")
        if d.get("kcal") is not None:
            bits.append(f"{d['kcal']:,.0f} kcal")
        if d.get("hr_avg") is not None:
            bits.append(f"FC {d['hr_avg']:.0f}")
        real = " · ".join(bits) if bits else "sin datos"
        reciente_html += f'<div class="rday"><span class="rday-f">{titulo}</span><span class="rday-v">{real}</span></div>'
    reciente_html += '</div>'

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FitClub — Plan vs Real</title>
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
.recent {{ margin-top: 28px; background: #fff; border-radius: 16px; padding: 18px 20px;
           border: 1px solid #F0EDE8; box-shadow: 0 1px 2px rgba(28,27,26,.03); }}
.recent h2 {{ font-size: 12px; font-weight: 600; color: #999; text-transform: uppercase;
              letter-spacing: 0.07em; margin-bottom: 8px; }}
.rday {{ display: flex; justify-content: space-between; padding: 5px 0;
         border-bottom: 1px solid #F7F5F1; font-size: 13px; }}
.rday:last-child {{ border-bottom: none; }}
.rday-f {{ color: #6E6A64; font-weight: 500; }}
.rday-v {{ color: #1C1B1A; font-variant-numeric: tabular-nums; }}
.semana {{ margin-top: 32px; }}
.semana h2 {{ font-size: 13px; font-weight: 700; color: #1C1B1A;
              text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 10px; }}
.semana h2 .fase {{ color: #B0ABA3; font-weight: 500; margin-left: 6px; }}
.pday {{ background: #fff; border-radius: 16px; padding: 14px 18px;
         margin-bottom: 10px; border: 1px solid #F0EDE8;
         box-shadow: 0 1px 2px rgba(28,27,26,.03); }}
.pday.done {{ border-left: 3px solid #4CAF7D; }}
.pday.missed {{ border-left: 3px solid #E85D3D; opacity: 0.75; }}
.pday.rest {{ border-left: 3px solid #D6D2CB; opacity: 0.6; }}
.pday.today {{ border-left: 3px solid #6366F1; }}
.pday.upcoming {{ border-left: 3px solid #E5E2DC; opacity: 0.55; }}
.pday-head {{ display: flex; justify-content: space-between; align-items: baseline; }}
.pday-fecha {{ font-size: 12px; font-weight: 600; color: #A39E97;
               text-transform: uppercase; letter-spacing: 0.06em; }}
.pday-status {{ font-size: 11px; color: #B0ABA3; }}
.pday-plan {{ font-size: 14px; font-weight: 600; margin-top: 6px; }}
.pday-real {{ font-size: 13px; color: #6E6A64; margin-top: 3px;
              font-variant-numeric: tabular-nums; }}
.sess {{ display: flex; justify-content: space-between; padding: 4px 0 0;
         font-size: 12.5px; color: #4B5563; }}
.sess-t {{ font-weight: 500; }}
.sess-v {{ font-variant-numeric: tabular-nums; color: #6E6A64; }}
footer {{ text-align: center; color: #C9C4BC; font-size: 12px; margin-top: 40px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Plan <span class="accent">vs</span> Real</h1>
    <p class="sub">8 semanas · carrera 10K el 28/nov · generado el {datetime.now():%d/%m/%Y %H:%M}</p>
    <div class="header-line"></div>
  </header>
  {reciente_html}
  {semanas_html}
  <footer>FitClub · python scripts/plan_vs_real.py</footer>
</div>
</body>
</html>
"""

    with open(os.path.join(WEB_DIR, "plan_vs_real.html"), "w", encoding="utf-8") as f:
        f.write(html)

    # --- consola ---
    hechas = sum(1 for s in sesiones if s["status"] == "done")
    perdidas = sum(1 for s in sesiones if s["status"] == "missed")
    print(f"\n✅ {os.path.join(WEB_DIR, 'plan_vs_real.html')}")
    print(f"  Sesiones: {len(sesiones)} | ✅ hechas: {hechas} | ❌ perdidas: {perdidas}")
    for s in sesiones:
        if s["status"] in ("done", "missed", "today"):
            icono = STATUS[s["status"]][0]
            print(f"  {icono} {s['dia']}: {s['sesion']}")


if __name__ == "__main__":
    main()
