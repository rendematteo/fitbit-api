#!/usr/bin/env python3
"""
make_dashboard.py — Genera `web/estadisticas.html`: web ESTÁTICA (sin Docker,
sin servidor) con estadísticas de los JSON en `data/descargas_google_health/`.

La parte de abajo (Top 3 + tabla) es dinámica: se ordena con un click
en los títulos de las columnas y el Top 3 cambia de métrica con el
selector — todo en JavaScript del lado del navegador.

Uso:
    python make_dashboard.py          -> crea web/estadisticas.html
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.helpers import (num, num_or_none, parse_ts, parse_off, parse_dur_s,
                         to_local, esc, pace_str, fmt_date, civil_key, load_local)
from src.paths import DATA_DIR, WEB_DIR

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ---------------- cargar ----------------
exercise = load_local(DATA_DIR, "exercise")
sleep = load_local(DATA_DIR, "sleep")
weight = load_local(DATA_DIR, "weight")
steps_raw = load_local(DATA_DIR, "steps")
distance_raw = load_local(DATA_DIR, "distance")
hr_samples = load_local(DATA_DIR, "heart-rate")
resting_raw = load_local(DATA_DIR, "daily-resting-heart-rate")
vo2_raw = load_local(DATA_DIR, "daily-vo2-max")
cal_raw = load_local(DATA_DIR, "total-calories")

# ---------------- actividades ----------------
acts = []
for dp in exercise:
    ex = dp.get("exercise") or {}
    iv = ex.get("interval") or {}
    ms = ex.get("metricsSummary") or {}
    start = to_local(parse_ts(iv.get("startTime")), parse_off(iv.get("startUtcOffset")))
    end = to_local(parse_ts(iv.get("endTime")), parse_off(iv.get("endUtcOffset")))
    if not start or not end:
        continue
    dur_s = parse_dur_s(ex.get("activeDuration"))
    if dur_s is None:
        dur_s = max(0.0, (end - start).total_seconds())
    if dur_s <= 0:
        continue
    pace = num_or_none(ms.get("averagePaceSecondsPerMeter"))
    acts.append({
        "type": esc((ex.get("exerciseType") or "OTRO").replace("_", " ").title()),
        "start": start,
        "dur_min": dur_s / 60.0,
        "km": num(ms.get("distanceMillimeters")) / 1e6,
        "kcal": num(ms.get("caloriesKcal")),
        "steps": num(ms.get("steps")),
        "hr": num_or_none(ms.get("averageHeartRateBeatsPerMinute")),
        "pace": pace * 1000.0 / 60.0 if pace and pace > 0 else None,
        "splits": ex.get("splits") or [],
    })
acts.sort(key=lambda a: a["start"])

# ---------------- sueño ----------------
nights = []
for dp in sleep:
    sl = dp.get("sleep") or {}
    iv = sl.get("interval") or {}
    end = to_local(parse_ts(iv.get("endTime")), parse_off(iv.get("endUtcOffset")))
    if not end:
        continue
    stage_min = defaultdict(float)
    for st in sl.get("stages") or []:
        s = to_local(parse_ts(st.get("startTime")), parse_off(st.get("startUtcOffset")))
        e = to_local(parse_ts(st.get("endTime")), parse_off(st.get("endUtcOffset")))
        if not s or not e:
            continue
        stage_min[st.get("type", "OTHER").upper()] += (e - s).total_seconds() / 60.0
    asleep = sum(v for k, v in stage_min.items() if k != "AWAKE")
    nights.append({
        "date": end.date(),
        "asleep_h": asleep / 60.0,
        "deep_h": stage_min.get("DEEP", 0.0) / 60.0,
        "rem_h": stage_min.get("REM", 0.0) / 60.0,
        "light_h": stage_min.get("LIGHT", 0.0) / 60.0,
        "awake_h": stage_min.get("AWAKE", 0.0) / 60.0,
    })
nights.sort(key=lambda n: n["date"])

# ---------------- peso ----------------
weights = []
for dp in weight:
    w = dp.get("weight") or {}
    st = w.get("sampleTime")
    if isinstance(st, dict):
        ts = parse_ts(st.get("physicalTime"))
        off = parse_off(st.get("utcOffset"))
    else:
        ts, off = parse_ts(st), timedelta(0)
    local = to_local(ts, off)
    kg = num(w.get("weightGrams")) / 1000.0
    if local and kg > 0:
        weights.append({"date": local.date(), "kg": kg})
weights.sort(key=lambda x: x["date"])

# ---------------- FC muestras ----------------
hr_pts = []
for dp in hr_samples:
    h = dp.get("heartRate") or {}
    bpm = num_or_none(h.get("beatsPerMinute"))
    st = h.get("sampleTime")
    if isinstance(st, dict):
        ts = parse_ts(st.get("physicalTime") or st.get("time"))
    else:
        ts = parse_ts(st)
    if bpm is not None and ts:
        hr_pts.append((ts, bpm))
hr_pts.sort()

# ---------------- FC reposo (diaria) ----------------
resting = []
for dp in resting_raw:
    d = dp.get("dailyRestingHeartRate") or {}
    bpm = num_or_none(d.get("beatsPerMinute"))
    key = d.get("date")
    key = civil_key(key) if isinstance(key, dict) else (str(key) if key else None)
    if key and bpm is not None:
        try:
            resting.append({"date": datetime.strptime(key, "%Y-%m-%d").date(), "bpm": bpm})
        except ValueError:
            pass
resting.sort(key=lambda x: x["date"])

# ---------------- VO2max (diario) ----------------
vo2 = []
for dp in vo2_raw:
    d = dp.get("dailyVo2Max") or {}
    val = num_or_none(d.get("vo2Max"))
    key = d.get("date")
    key = civil_key(key) if isinstance(key, dict) else (str(key) if key else None)
    if key and val is not None:
        try:
            vo2.append({"date": datetime.strptime(key, "%Y-%m-%d").date(), "val": val})
        except ValueError:
            pass
vo2.sort(key=lambda x: x["date"])

# ---------------- pasos y distancia por día ----------------
steps_by_day = defaultdict(float)
dist_mm_by_day = defaultdict(float)
for dp in steps_raw:
    st = dp.get("steps") or {}
    key = civil_key((st.get("interval") or {}).get("civilStartTime"))
    if key:
        steps_by_day[key] += num(dp.get("count"))
for dp in distance_raw:
    di = dp.get("distance") or {}
    key = civil_key((di.get("interval") or {}).get("civilStartTime"))
    if key:
        dist_mm_by_day[key] += num(dp.get("millimeters"))

# ---------------- stats ----------------
tot_km = sum(a["km"] for a in acts)
tot_min = sum(a["dur_min"] for a in acts)
tot_kcal = sum(a["kcal"] for a in acts)
tot_steps = sum(a["steps"] for a in acts)

by_type = defaultdict(lambda: {"n": 0, "min": 0.0, "km": 0.0})
for a in acts:
    t = by_type[a["type"]]
    t["n"] += 1
    t["min"] += a["dur_min"]
    t["km"] += a["km"]

today = datetime.now().date()
last7 = []
for d in range(6, -1, -1):
    day = today - timedelta(days=d)
    last7.append((fmt_date(day), sum(a["dur_min"] for a in acts if a["start"].date() == day)))

last14 = [today - timedelta(days=d) for d in range(13, -1, -1)]
steps_chart = [(dt.strftime("%d/%m"), steps_by_day.get(dt.isoformat(), 0.0)) for dt in last14]
dist_chart = [(dt.strftime("%d/%m"), dist_mm_by_day.get(dt.isoformat(), 0.0) / 1e6) for dt in last14]

run = next((a for a in reversed(acts) if a["splits"]), None)
splits = []
if run:
    for sp in run["splits"]:
        ms = sp.get("metricsSummary") or {}
        km = num(ms.get("distanceMillimeters")) / 1e6
        pace = num_or_none(ms.get("averagePaceSecondsPerMeter"))
        if km > 0 and pace and pace > 0:
            splits.append({"km": km, "min_km": pace * 1000.0 / 60.0})

last_nights = nights[-14:]

# ---------------- gráficos ----------------

def bars(items, color="#6366f1", val_fmt="{:.0f}"):
    mx = max((v for _, v in items), default=0) or 0
    out = ['<div class="bars">']
    for label, val in items:
        h = (val / mx * 100) if mx > 0 else 0
        out.append(
            f'<div class="bar-wrap" title="{esc(label)}: {val_fmt.format(val)}">'
            f'<div class="bar" style="height:{h:.1f}%;background:{color}"></div>'
            f'<span class="bar-lbl">{esc(label)}</span></div>'
        )
    out.append("</div>")
    return "".join(out)


def line_svg(values, labels, color="#10b981", unit="", zero=True):
    if not values:
        return '<p class="muted">sin datos</p>'
    n = len(values)
    vmax = max(values)
    vmin = 0.0 if zero else min(values)
    rng = (vmax - vmin) or 1.0
    W, H = 720, 160
    pts = []
    for i, v in enumerate(values):
        x = 24 + i * (W - 48) / max(1, n - 1)
        y = H - 24 - (v - vmin) / rng * (H - 48)
        pts.append(f"{x:.1f},{y:.1f}")
    grid = "".join(
        f'<line x1="24" y1="{H - 24 - (i / 3) * (H - 48):.0f}" x2="{W - 24}" '
        f'y2="{H - 24 - (i / 3) * (H - 48):.0f}" stroke="#eef0f6"/>'
        for i in range(4)
    )
    return (
        f'<svg viewBox="0 0 {W} {H}" class="chart">{grid}'
        f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" '
        f'stroke-width="2.5" stroke-linejoin="round"/>'
        f'</svg>'
        f'<p class="muted">{esc(labels)} · mín {min(values):.1f}{unit} · '
        f'máx {max(values):.1f}{unit}</p>'
    )


# ---------------- datos para JS ----------------
acts_js = [{
    "fechaTs": a["start"].isoformat(),
    "fechaLbl": a["start"].strftime("%d/%m %H:%M"),
    "tipo": a["type"],
    "durMin": round(a["dur_min"], 1),
    "km": round(a["km"], 3),
    "kcal": round(a["kcal"]),
    "pasos": round(a["steps"]),
    "hr": round(a["hr"]) if a["hr"] else None,
    "pace": round(a["pace"], 2) if a["pace"] else None,
} for a in acts]

# ---------------- JS ----------------
JS = r"""
const ACTIVIDADES = __ACTIVIDADES__;
const METRICAS = {
  km:    {lbl: "Distancia", fmt: v => v.toFixed(2) + " km",   mejor: "max"},
  pace:  {lbl: "Ritmo",     fmt: v => paceStr(v),              mejor: "min"},
  kcal:  {lbl: "Calorías",  fmt: v => Math.round(v) + " kcal", mejor: "max"},
  dur:   {lbl: "Duración",  fmt: v => Math.round(v) + " min",  mejor: "max"},
  pasos: {lbl: "Pasos",     fmt: v => Math.round(v).toLocaleString("es-AR"), mejor: "max"},
};
let claveOrden = "fechaTs", dirOrden = -1;

function paceStr(mink) {
  if (mink == null) return "-";
  const m = Math.floor(mink), s = Math.round((mink - m) * 60);
  return m + ":" + String(s).padStart(2, "0");
}

function renderTop3(metrica) {
  const m = METRICAS[metrica];
  const validos = ACTIVIDADES.filter(a => a[metrica] != null);
  const orden = (m.mejor === "min")
    ? [...validos].sort((a, b) => a[metrica] - b[metrica])
    : [...validos].sort((a, b) => b[metrica] - a[metrica]);
  const medallas = ["🥇", "🥈", "🥉"];
  document.getElementById("top3").innerHTML = orden.slice(0, 3).map((a, i) =>
    `<div class="podium">
       <div class="pod-medalla">${medallas[i]}</div>
       <div class="pod-tipo">${a.tipo}</div>
       <div class="pod-fecha">${a.fechaLbl}</div>
       <div class="pod-val">${m.fmt(a[metrica])}</div>
     </div>`).join("");
}

function ordenarPor(clave) {
  if (claveOrden === clave) dirOrden *= -1;
  else { claveOrden = clave; dirOrden = -1; }
  renderTabla();
}

function renderTabla() {
  const filas = [...ACTIVIDADES].sort((a, b) => {
    const va = a[claveOrden], vb = b[claveOrden];
    if (va == null) return 1;
    if (vb == null) return -1;
    const cmp = (typeof va === "string") ? (va > vb ? 1 : va < vb ? -1 : 0) : (va - vb);
    return cmp * dirOrden;
  });
  document.getElementById("tbody").innerHTML = filas.map(f =>
    `<tr><td>${f.fechaLbl}</td><td>${f.tipo}</td>` +
    `<td>${Math.round(f.durMin)}</td><td>${f.km.toFixed(2)}</td>` +
    `<td>${Math.round(f.kcal)}</td><td>${Math.round(f.pasos).toLocaleString("es-AR")}</td>` +
    `<td>${f.hr == null ? "-" : Math.round(f.hr)}</td>` +
    `<td>${paceStr(f.pace)}</td></tr>`).join("");
  document.querySelectorAll("th[data-k]").forEach(th => {
    const k = th.getAttribute("data-k");
    th.classList.toggle("ord", k === claveOrden);
    const arr = th.querySelector(".arr");
    if (arr) arr.textContent = (k === claveOrden) ? (dirOrden === 1 ? "▲" : "▼") : "";
  });
}

renderTop3("km");
renderTabla();
"""

# ---------------- CSS ----------------
CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
       background: #f4f5fb; color: #1e2235; padding: 24px; }
.wrap { max-width: 1080px; margin: 0 auto; }
h1 { font-size: 26px; }
.sub { color: #6b7280; font-size: 13px; margin-top: 4px; }
.kpis { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 22px; }
.kpi { flex: 1; min-width: 140px; background: #fff; border-radius: 14px;
       padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.kpi .num { font-size: 27px; font-weight: 700; color: #4f46e5; }
.kpi .lbl { font-size: 11.5px; color: #6b7280; text-transform: uppercase;
            letter-spacing: .04em; margin-top: 2px; }
.card { background: #fff; border-radius: 14px; padding: 18px; margin-bottom: 18px;
        box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.card h2 { font-size: 16px; margin-bottom: 12px; }
.bars { display: flex; align-items: flex-end; gap: 6px; height: 170px; }
.bar-wrap { flex: 1; display: flex; flex-direction: column; align-items: center;
            justify-content: flex-end; height: 100%; min-width: 0; }
.bar { width: 100%; max-width: 44px; border-radius: 6px 6px 0 0; min-height: 2px; }
.bar-lbl { font-size: 10.5px; color: #6b7280; margin-top: 5px; white-space: nowrap; }
.chart { width: 100%; height: auto; }
.muted { color: #9ca3af; font-size: 13px; margin-top: 6px; }
table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #eef0f6; }
th { color: #6b7280; font-size: 11.5px; text-transform: uppercase; letter-spacing: .04em; }
th[data-k] { cursor: pointer; user-select: none; white-space: nowrap; }
th[data-k]:hover { color: #4f46e5; }
th.ord { color: #4f46e5; }
tr:hover td { background: #f8f9ff; }
.stack { display: flex; height: 26px; border-radius: 8px; overflow: hidden; }
.stack div { height: 100%; }
.legend { display: flex; gap: 14px; font-size: 12px; color: #6b7280; margin-top: 8px; flex-wrap: wrap; }
.legend span::before { content: ""; display: inline-block; width: 10px; height: 10px;
       border-radius: 3px; margin-right: 5px; background: var(--c); }
select { padding: 5px 10px; border-radius: 8px; border: 1px solid #d1d5db;
         font-size: 13px; font-weight: 600; color: #1e2235; }
.podium-row { display: flex; gap: 12px; }
.podium { flex: 1; background: #f8f9ff; border: 2px solid #e0e4ff; border-radius: 12px;
          padding: 14px 10px; text-align: center; }
.pod-medalla { font-size: 30px; }
.pod-tipo { font-weight: 700; margin-top: 4px; }
.pod-fecha { font-size: 12px; color: #6b7280; }
.pod-val { font-size: 20px; font-weight: 700; color: #4f46e5; margin-top: 4px; }
footer { text-align: center; color: #9ca3af; font-size: 12px; margin-top: 26px; }
"""

# ---------------- secciones ----------------

kpis = f"""
<div class="kpis">
  <div class="kpi"><div class="num">{len(acts)}</div><div class="lbl">Actividades</div></div>
  <div class="kpi"><div class="num">{tot_km:.1f}</div><div class="lbl">Km totales</div></div>
  <div class="kpi"><div class="num">{tot_min/60:.1f}</div><div class="lbl">Horas</div></div>
  <div class="kpi"><div class="num">{tot_kcal:.0f}</div><div class="lbl">Calorías</div></div>
  <div class="kpi"><div class="num">{tot_steps:,.0f}</div><div class="lbl">Pasos (entrenamientos)</div></div>
</div>
"""

steps_card = f"""
<div class="card">
  <h2>👣 Pasos por día — últimas 2 semanas</h2>
  {bars(steps_chart, "#10b981", "{:,.0f}")}
</div>
<div class="card">
  <h2>🛣️ Km por día — últimas 2 semanas (todos los movimientos)</h2>
  {bars(dist_chart, "#0ea5e9", "{:.2f} km")}
</div>
"""

sleep_card = ""
if nights:
    n = nights[-1]
    total = n["light_h"] + n["deep_h"] + n["rem_h"] + n["awake_h"]
    def seg(v, c):
        return f'<div style="width:{v/total*100:.1f}%;background:{c}"></div>' if v > 0 else ""
    stack = (seg(n["light_h"], "#93c5fd") + seg(n["deep_h"], "#1e40af")
             + seg(n["rem_h"], "#c4b5fd") + seg(n["awake_h"], "#e5e7eb"))
    sleep_card = f"""
<div class="card">
  <h2>😴 Sueño — últimas 2 semanas</h2>
  {line_svg([n2["asleep_h"] for n2 in last_nights],
            f"{len(last_nights)} noches ({fmt_date(last_nights[0]['date'])} → {fmt_date(last_nights[-1]['date'])})" if last_nights else "",
            "#10b981", " h")}
  <h2 style="margin-top:18px">Última noche ({fmt_date(n['date'])}) — {n['asleep_h']:.1f} h dormido</h2>
  <div class="stack">{stack}</div>
  <div class="legend">
    <span style="--c:#93c5fd">Light {n['light_h']:.1f} h</span>
    <span style="--c:#1e40af">Deep {n['deep_h']:.1f} h</span>
    <span style="--c:#c4b5fd">REM {n['rem_h']:.1f} h</span>
    <span style="--c:#e5e7eb">Despierto {n['awake_h']:.1f} h</span>
  </div>
</div>
"""

split_card = ""
if run and splits:
    split_card = f"""
<div class="card">
  <h2>🏃 Última carrera con GPS — ritmo por km ({run['start']:%d/%m} · {run['km']:.2f} km · ritmo avg {pace_str(run['pace'])})</h2>
  {bars([(f"km {i+1}", s['min_km']) for i, s in enumerate(splits)], "#f59e0b", "{:.1f} min/km")}
  <p class="muted">Menor = más rápido 🔥</p>
</div>
"""

resting_card = '<div class="card"><h2>❤️ FC en reposo (diaria)</h2><p class="muted">sin datos todavía</p></div>'
if resting:
    last_r = resting[-1]
    trend = line_svg([r["bpm"] for r in resting[-30:]],
                     f"últimos {min(30, len(resting))} días ({fmt_date(resting[0]['date'])} → {fmt_date(last_r['date'])})",
                     "#ef4444", " bpm", zero=False)
    resting_card = f"""
<div class="card">
  <h2>❤️ FC en reposo — última: {last_r['bpm']:.0f} bpm ({fmt_date(last_r['date'])})</h2>
  {trend}
</div>
"""

vo2_card = '<div class="card"><h2>🫁 VO2max (diario)</h2><p class="muted">sin datos todavía</p></div>'
if vo2:
    last_v = vo2[-1]
    trend = line_svg([v["val"] for v in vo2[-30:]],
                     f"últimos {min(30, len(vo2))} días",
                     "#8b5cf6", " ml/kg/min", zero=False)
    vo2_card = f"""
<div class="card">
  <h2>🫁 VO2max — último: {last_v['val']:.1f} ml/kg/min ({fmt_date(last_v['date'])})</h2>
  {trend}
</div>
"""

weight_card = '<div class="card"><h2>⚖️ Peso</h2><p class="muted">sin datos</p></div>'
if weights:
    last_w = weights[-1]
    trend = ""
    if len(weights) > 1:
        trend = line_svg([w["kg"] for w in weights],
                         f"{len(weights)} medidas ({fmt_date(weights[0]['date'])} → {fmt_date(weights[-1]['date'])})",
                         "#8b5cf6", " kg", zero=False)
    weight_card = f"""
<div class="card">
  <h2>⚖️ Peso — último: {last_w['kg']:.1f} kg ({fmt_date(last_w['date'])})</h2>
  {trend or '<p class="muted">solo hay una medida</p>'}
</div>
"""

hr_card = '<div class="card"><h2>❤️ FC — última muestra</h2><p class="muted">sin datos</p></div>'
if hr_pts:
    ts, bpm = hr_pts[-1]
    avg = sum(b for _, b in hr_pts) / len(hr_pts)
    hr_card = f"""
<div class="card">
  <h2>❤️ Frecuencia cardíaca (muestras)</h2>
  <div class="kpis" style="margin-bottom:0">
    <div class="kpi"><div class="num">{bpm:.0f}</div><div class="lbl">bpm última muestra ({ts:%d/%m %H:%M})</div></div>
    <div class="kpi"><div class="num">{avg:.0f}</div><div class="lbl">bpm promedio ({len(hr_pts):,} muestras)</div></div>
  </div>
</div>
"""

type_rows = ""
for t, v in sorted(by_type.items(), key=lambda kv: -kv[1]["min"]):
    type_rows += (
        f"<tr><td>{t}</td><td>{v['n']}</td>"
        f"<td>{v['min']/60:.1f} h</td><td>{v['km']:.1f}</td>"
        f"<td>{v['km']/max(1,v['n']):.2f}</td></tr>"
    )

# ---------------- HTML ----------------
html_base = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FitClub — Estadísticas</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>🏃 FitClub — Mis estadísticas</h1>
    <p class="sub">Generado el {datetime.now():%d/%m/%Y %H:%M} · Datos: Google Health API
    (carpeta data/descargas_google_health/) · Web estática — sin Docker, sin servidor</p>
  </header>

  {kpis}

  <div class="card">
    <h2>📅 Últimos 7 días — minutos de actividad</h2>
    {bars(last7, "#6366f1", "{:.0f} min")}
  </div>

  {steps_card}

  {split_card}

  {sleep_card}

  <div class="card">
    <h2>🏷️ Actividades por tipo</h2>
    {bars([(t, v["min"]) for t, v in sorted(by_type.items(), key=lambda kv: -kv[1]["min"])], "#ec4899", "{:.0f} min")}
    <table style="margin-top:14px">
      <tr><th>Tipo</th><th>N</th><th>Tiempo</th><th>Km</th><th>Km/media</th></tr>
      {type_rows}
    </table>
  </div>

  {resting_card}

  {vo2_card}

  {weight_card}

  {hr_card}

  <div class="card">
    <h2>🏆 Top 3 entrenamientos —
      <select id="metrica" onchange="renderTop3(this.value)">
        <option value="km">📏 Distancia</option>
        <option value="pace">⚡ Ritmo (más rápido)</option>
        <option value="kcal">🔥 Calorías</option>
        <option value="dur">⏱️ Duración</option>
        <option value="pasos">👣 Pasos</option>
      </select>
    </h2>
    <div class="podium-row" id="top3"></div>
  </div>

  <div class="card">
    <h2>📋 Todas las actividades <span class="muted">— apretá un título de columna para ordenar</span></h2>
    <table>
      <thead><tr>
        <th data-k="fechaTs" onclick="ordenarPor('fechaTs')">Fecha <span class="arr"></span></th>
        <th data-k="tipo" onclick="ordenarPor('tipo')">Tipo <span class="arr"></span></th>
        <th data-k="durMin" onclick="ordenarPor('durMin')">Duración <span class="arr"></span></th>
        <th data-k="km" onclick="ordenarPor('km')">Km <span class="arr"></span></th>
        <th data-k="kcal" onclick="ordenarPor('kcal')">Kcal <span class="arr"></span></th>
        <th data-k="pasos" onclick="ordenarPor('pasos')">Pasos <span class="arr"></span></th>
        <th data-k="hr" onclick="ordenarPor('hr')">FC <span class="arr"></span></th>
        <th data-k="pace" onclick="ordenarPor('pace')">Ritmo <span class="arr"></span></th>
      </tr></thead>
      <tbody id="tbody"></tbody>
    </table>
  </div>

  <footer>
    FitClub · datos vía Google Health API · re-corré <code>python scripts/make_dashboard.py</code> para refreshar
  </footer>
</div>
<script>__JS__</script>
</body>
</html>
"""

html = (html_base
        .replace("__ACTIVIDADES__", json.dumps(acts_js, ensure_ascii=False))
        .replace("__JS__", JS))

with open(os.path.join(WEB_DIR, "estadisticas.html"), "w", encoding="utf-8") as f:
    f.write(html)

# ---------------- resumen por consola ----------------
print(f"✅ {os.path.join(WEB_DIR, 'estadisticas.html')}")
if acts:
    print(f"   Actividades: {len(acts)} | {tot_km:.1f} km | {tot_min/60:.1f} h | "
          f"{tot_kcal:.0f} kcal | {tot_steps:,.0f} pasos")
    print(f"   Rango: {acts[0]['start']:%d/%m/%Y} → {acts[-1]['start']:%d/%m/%Y}")
else:
    print("   Sin actividades")
print(f"   Sueño: {len(nights)} noches | Peso: {len(weights)} medidas")
print(f"   Pasos/día: {len(steps_by_day)} días | Km/día: {len(dist_mm_by_day)} días")
print(f"   FC reposo: {len(resting)} días | VO2max: {len(vo2)} días | FC muestras: {len(hr_pts):,}")
print(f"   Calorías totales (API): {len(cal_raw)} puntos")
print(f"   Tipos: {', '.join(f'{t}={v['n']}' for t, v in sorted(by_type.items(), key=lambda kv: -kv[1]['min']))}")
