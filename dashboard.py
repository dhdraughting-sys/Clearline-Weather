"""
Builds a single self-contained dashboard.html from the latest reading +
recent history. No external CSS/JS/CDN — it has to keep working even when
opened straight from a phone's file browser with no internet connection.
"""

import datetime

from weather_lib import WEATHER_CODE_LABELS, pressure_trend, now_local

COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def compass_dir(deg):
    if deg is None or deg == "":
        return "—"
    idx = int((float(deg) / 22.5) + 0.5) % 16
    return COMPASS[idx]


def weather_label(code):
    try:
        code = int(float(code))
    except (TypeError, ValueError):
        return "—", ""
    return WEATHER_CODE_LABELS.get(code, ("Weather code {}".format(code), ""))


def fnum(val, decimals=1, suffix=""):
    if val is None or val == "":
        return "—"
    try:
        return "{:.{d}f}{}".format(float(val), suffix, d=decimals)
    except (TypeError, ValueError):
        return str(val)


def svg_sparkline(rows, key, width=560, height=120, pad=10, colour="#1F3864", unit=""):
    """A tiny hand-rolled SVG line chart - no chart library, no CDN."""
    points = []
    for row in rows:
        val = row.get(key)
        if val in (None, ""):
            continue
        try:
            points.append((row["captured_at"], float(val)))
        except (ValueError, KeyError):
            continue

    if len(points) < 2:
        return '<div class="no-data">Not enough data yet for a chart — check back after a few readings.</div>'

    values = [p[1] for p in points]
    vmin, vmax = min(values), max(values)
    if vmax == vmin:
        vmax = vmin + 1  # avoid a divide-by-zero flat line

    n = len(points)
    coords = []
    for i, (_, v) in enumerate(points):
        x = pad + (i / (n - 1)) * (width - 2 * pad)
        y = height - pad - ((v - vmin) / (vmax - vmin)) * (height - 2 * pad)
        coords.append("{:.1f},{:.1f}".format(x, y))
    polyline = " ".join(coords)

    last_x, last_y = coords[-1].split(",")

    return '''<svg viewBox="0 0 {w} {h}" class="sparkline" preserveAspectRatio="none">
      <polyline fill="none" stroke="{colour}" stroke-width="2" points="{polyline}" />
      <circle cx="{lx}" cy="{ly}" r="3.5" fill="{colour}" />
      <text x="{pad}" y="14" class="chart-label">{vmax}{unit}</text>
      <text x="{pad}" y="{h_minus}" class="chart-label">{vmin}{unit}</text>
    </svg>'''.format(
        w=width, h=height, polyline=polyline, colour=colour,
        lx=last_x, ly=last_y, pad=pad, vmax=round(vmax, 1), vmin=round(vmin, 1),
        unit=unit, h_minus=height - 2,
    )


def history_table(rows, limit=24):
    """Small table of the most recent readings, newest first. Capped at
    `limit` rows so the page stays a reasonable size - the full log keeps
    growing forever in data/<slug>.csv even though the page only shows a
    recent slice of it."""
    if not rows:
        return '<div class="no-data">No readings logged yet.</div>'

    recent = list(reversed(rows[-limit:]))
    body_rows = []
    for row in recent:
        try:
            ts = datetime.datetime.fromisoformat(row["captured_at"])
            time_label = ts.strftime("%a %H:%M")
        except (ValueError, KeyError):
            time_label = row.get("captured_at", "—")
        cond_label, cond_emoji = weather_label(row.get("weather_code"))
        body_rows.append(
            '<tr><td>{time}</td><td>{emoji} {temp}°C</td>'
            '<td>{dew}°C</td>'
            '<td>{pressure} hPa</td><td>{humidity}%</td>'
            '<td>{wind} km/h {wind_dir}</td><td>{rain} mm</td>'
            '<td>{snow} cm</td></tr>'.format(
                time=time_label,
                emoji=cond_emoji,
                temp=fnum(row.get("temp_c"), 1),
                dew=fnum(row.get("dew_point_c"), 1),
                pressure=fnum(row.get("pressure_msl_hpa"), 1),
                humidity=fnum(row.get("humidity_pct"), 0),
                wind=fnum(row.get("wind_kph"), 1),
                wind_dir=compass_dir(row.get("wind_dir_deg")),
                rain=fnum(row.get("rain_mm"), 1),
                snow=fnum(row.get("snowfall_cm"), 1),
            )
        )

    return '''<table class="history">
      <thead><tr><th>Time</th><th>Temp</th><th>Dew Pt</th><th>Pressure</th><th>Humidity</th><th>Wind</th><th>Rain</th><th>Snow</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>'''.format(rows="".join(body_rows))


def render(location_name, latest, rows, output_path):
    trend_label, trend_delta = pressure_trend(rows)
    cond_label, cond_emoji = weather_label(latest.get("weather_code"))
    generated_at = now_local().strftime("%a %d %b %Y, %H:%M")

    trend_arrow = {"Rising": "▲", "Falling": "▼", "Steady": "▶"}.get(trend_label, "")
    trend_text = (
        "{} {} ({:+.1f} hPa / 3h)".format(trend_arrow, trend_label, trend_delta)
        if trend_label else "Not enough history yet"
    )

    temp_chart = svg_sparkline(rows, "temp_c", colour="#C0392B", unit="°C")
    pressure_chart = svg_sparkline(rows, "pressure_msl_hpa", colour="#1F3864", unit=" hPa")
    wind_chart = svg_sparkline(rows, "wind_kph", colour="#3E6FA6", unit=" km/h")

    html = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{location_name} Weather</title>
<link rel="manifest" href="manifest.json">
<link rel="icon" href="icon-192.png">
<link rel="apple-touch-icon" href="icon-192.png">
<meta name="theme-color" content="#1F3864">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Weather">
<style>
  :root{{ --navy:#1F3864; --navy-dark:#152747; --accent:#C0392B; --ink:#22303F; --muted:#5C6B7A; --bg:#FAFBFC; --white:#fff; --line:#DCE6F1; }}
  *{{box-sizing:border-box;margin:0;padding:0;}}
  body{{font-family:'Segoe UI',Arial,Helvetica,sans-serif;color:var(--ink);background:var(--bg);line-height:1.5;padding-bottom:40px;}}
  .wrap{{max-width:900px;margin:0 auto;padding:20px 16px;}}
  .eyebrow{{font-size:.72rem;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);}}
  h1{{font-size:1.5rem;color:var(--navy);margin:4px 0 2px;}}
  .updated{{font-size:.8rem;color:var(--muted);margin-bottom:18px;}}
  .updated a{{color:var(--navy);font-weight:600;text-decoration:none;}}
  .updated a:hover{{text-decoration:underline;}}

  .now-card{{background:linear-gradient(135deg,var(--navy),var(--navy-dark));color:#fff;border-radius:16px;padding:26px;margin-bottom:16px;}}
  .now-top{{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;}}
  .now-temp{{font-size:3rem;font-weight:800;}}
  .now-cond{{font-size:1rem;opacity:.9;}}
  .now-emoji{{font-size:2.2rem;}}
  .now-sub{{font-size:.85rem;opacity:.8;margin-top:4px;}}

  .grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:20px;}}
  .stat{{background:rgba(255,255,255,.08);border-radius:10px;padding:10px 12px;}}
  .stat .label{{font-size:.68rem;text-transform:uppercase;letter-spacing:.04em;opacity:.7;}}
  .stat .val{{font-size:1.05rem;font-weight:700;margin-top:2px;}}
  @media (min-width:640px){{ .grid{{grid-template-columns:repeat(4,1fr);}} }}

  .card{{background:var(--white);border:1px solid var(--line);border-radius:14px;padding:20px;margin-bottom:16px;}}
  .card h2{{font-size:.95rem;color:var(--navy);margin-bottom:10px;}}
  .sparkline{{width:100%;height:auto;}}
  .chart-label{{font-size:9px;fill:var(--muted);}}
  .no-data{{font-size:.85rem;color:var(--muted);padding:20px 0;text-align:center;}}

  table.history{{width:100%;border-collapse:collapse;font-size:.82rem;}}
  table.history th{{text-align:left;color:var(--navy);font-size:.68rem;text-transform:uppercase;letter-spacing:.04em;padding:6px 8px;border-bottom:2px solid var(--line);}}
  table.history td{{padding:6px 8px;border-bottom:1px solid var(--line);white-space:nowrap;}}
  table.history tbody tr:nth-child(even){{background:var(--bg);}}
  .table-wrap{{overflow-x:auto;}}
  .table-note{{font-size:.72rem;color:var(--muted);margin-top:10px;}}

  .footer-note{{font-size:.75rem;color:var(--muted);text-align:center;margin-top:20px;}}
</style>
</head>
<body>
<div class="wrap">
  <span class="eyebrow">Personal Weather Log</span>
  <h1>{location_name}</h1>
  <div class="updated">Last updated {generated_at} &middot; <a href="history.html">View full history &rarr;</a></div>

  <div class="now-card">
    <div class="now-top">
      <div>
        <div class="now-temp">{temp}°C</div>
        <div class="now-cond">{cond_emoji} {cond_label} &middot; feels like {apparent}°C</div>
      </div>
      <div class="now-emoji">{cond_emoji}</div>
    </div>
    <div class="now-sub">Pressure trend: {trend_text}</div>
    <div class="grid">
      <div class="stat"><div class="label">Pressure</div><div class="val">{pressure} hPa</div></div>
      <div class="stat"><div class="label">Humidity</div><div class="val">{humidity}%</div></div>
      <div class="stat"><div class="label">Dew point</div><div class="val">{dew_point}°C</div></div>
      <div class="stat"><div class="label">Wind</div><div class="val">{wind} km/h {wind_dir}</div></div>
      <div class="stat"><div class="label">Gusts</div><div class="val">{gusts} km/h</div></div>
      <div class="stat"><div class="label">Rain</div><div class="val">{rain} mm</div></div>
      <div class="stat"><div class="label">Snowfall</div><div class="val">{snowfall} cm</div></div>
      <div class="stat"><div class="label">Cloud cover</div><div class="val">{cloud}%</div></div>
      <div class="stat"><div class="label">UV index</div><div class="val">{uv}</div></div>
      <div class="stat"><div class="label">Visibility</div><div class="val">{visibility} km</div></div>
      <div class="stat"><div class="label">Sunrise</div><div class="val">🌅 {sunrise}</div></div>
      <div class="stat"><div class="label">Sunset</div><div class="val">🌇 {sunset}</div></div>
    </div>
  </div>

  <div class="card">
    <h2>Temperature — last {hours}h</h2>
    {temp_chart}
  </div>
  <div class="card">
    <h2>Pressure — last {hours}h</h2>
    {pressure_chart}
  </div>
  <div class="card">
    <h2>Wind speed — last {hours}h</h2>
    {wind_chart}
  </div>

  <div class="card">
    <h2>Recent readings</h2>
    <div class="table-wrap">
      {history_table}
    </div>
    <div class="table-note">Showing the most recent {table_rows} of {n} logged readings.</div>
  </div>

  <div class="footer-note">
    Data: Open-Meteo.com (CC-BY 4.0) &middot; {n} readings logged &middot; captured locally, not connected to any website or hosting platform.
  </div>
</div>
<script>
if ('serviceWorker' in navigator) {{
  window.addEventListener('load', function () {{
    navigator.serviceWorker.register('sw.js').catch(function (err) {{
      console.warn('Service worker registration failed:', err);
    }});
  }});
  var swRefreshing = false;
  navigator.serviceWorker.addEventListener('controllerchange', function () {{
    if (swRefreshing) return;
    swRefreshing = true;
    window.location.reload();
  }});
}}
</script>
</body>
</html>'''.format(
        location_name=location_name,
        generated_at=generated_at,
        temp=fnum(latest.get("temp_c"), 1),
        apparent=fnum(latest.get("apparent_c"), 1),
        cond_label=cond_label,
        cond_emoji=cond_emoji,
        trend_text=trend_text,
        pressure=fnum(latest.get("pressure_msl_hpa"), 1),
        humidity=fnum(latest.get("humidity_pct"), 0),
        dew_point=fnum(latest.get("dew_point_c"), 1),
        wind=fnum(latest.get("wind_kph"), 1),
        wind_dir=compass_dir(latest.get("wind_dir_deg")),
        gusts=fnum(latest.get("gusts_kph"), 1),
        rain=fnum(latest.get("rain_mm"), 1),
        snowfall=fnum(latest.get("snowfall_cm"), 1),
        cloud=fnum(latest.get("cloud_pct"), 0),
        uv=fnum(latest.get("uv_index"), 1),
        visibility=fnum(
            (float(latest["visibility_m"]) / 1000) if latest.get("visibility_m") not in (None, "") else None,
            1,
        ),
        sunrise=latest.get("sunrise") or "—",
        sunset=latest.get("sunset") or "—",
        temp_chart=temp_chart,
        pressure_chart=pressure_chart,
        wind_chart=wind_chart,
        history_table=history_table(rows),
        table_rows=min(len(rows), 24),
        hours=48,
        n=len(rows),
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
