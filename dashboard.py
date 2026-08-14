"""
Builds a single self-contained dashboard.html from the latest reading +
recent history. No external CSS/JS/CDN — it has to keep working even when
opened straight from a phone's file browser with no internet connection.
"""

import datetime
import math

from weather_lib import (
    WEATHER_CODE_LABELS, pressure_trend, barometric_outlook, now_local,
    feels_like_calculated, aqi_label, moon_phase, rainfall_totals, wind_rose_data,
)

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


def _nice_axis_step(value_range, target_ticks=4):
    """Round a raw axis step up to a 'nice' number (1/2/5 x a power of ten)
    so gridlines land on round values like 10/20/30 rather than
    13.7/27.4/41.1 - the same trick real charting libraries use."""
    if value_range <= 0:
        return 1.0
    raw_step = value_range / target_ticks
    magnitude = 10 ** math.floor(math.log10(raw_step))
    for m in (1, 2, 5, 10):
        step = m * magnitude
        if step >= raw_step:
            return step
    return 10 * magnitude


def svg_sparkline(rows, key, width=640, height=220, colour="#1F3864", unit="", decimals=1, fill=True):
    """A hand-rolled SVG line chart - no chart library, no CDN - with
    enough on it to actually read trends off, not just glance at a
    squiggle: horizontal gridlines with value labels, a few time labels
    along the bottom, a dashed average line, and a min/avg/max/now stat
    strip above the chart."""
    points = []
    for row in rows:
        val = row.get(key)
        if val in (None, ""):
            continue
        try:
            ts = datetime.datetime.fromisoformat(row["captured_at"])
            points.append((ts, float(val)))
        except (ValueError, KeyError, TypeError):
            continue

    if len(points) < 2:
        return '<div class="no-data">Not enough data yet for a chart — check back after a few readings.</div>'

    values = [p[1] for p in points]
    raw_min, raw_max = min(values), max(values)
    avg = sum(values) / len(values)
    current = values[-1]
    if raw_max == raw_min:
        raw_max = raw_min + 1  # avoid a divide-by-zero flat line

    step = _nice_axis_step(raw_max - raw_min)
    grid_min = math.floor(raw_min / step) * step
    grid_max = math.ceil(raw_max / step) * step
    if grid_max == grid_min:
        grid_max = grid_min + step

    pad_left, pad_right, pad_top, pad_bottom = 58, 14, 16, 26
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom
    n = len(points)

    def x_for(i):
        return pad_left + (i / (n - 1)) * plot_w

    def y_for(v):
        return pad_top + plot_h - ((v - grid_min) / (grid_max - grid_min)) * plot_h

    coords = ["{:.1f},{:.1f}".format(x_for(i), y_for(v)) for i, (_, v) in enumerate(points)]
    polyline = " ".join(coords)
    last_x, last_y = coords[-1].split(",")

    fill_html = ""
    if fill:
        baseline = pad_top + plot_h
        fill_points = "{} {:.1f},{:.1f} {:.1f},{:.1f}".format(
            polyline, x_for(n - 1), baseline, x_for(0), baseline,
        )
        fill_html = '<polygon points="{}" fill="{}" opacity=".10" />'.format(fill_points, colour)

    # Horizontal gridlines + value labels, at "nice" steps.
    grid_html = []
    n_ticks = int(round((grid_max - grid_min) / step)) + 1
    for t in range(n_ticks):
        val = grid_min + t * step
        y = y_for(val)
        label = "{:.0f}".format(val) if (decimals == 0 or float(val).is_integer()) else "{:.{d}f}".format(val, d=decimals)
        grid_html.append(
            '<line x1="{pl}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" stroke="#E7EEF6" stroke-width="1" />'
            '<text x="{lx}" y="{ly:.1f}" class="chart-axis-label" text-anchor="end">{label}{unit}</text>'.format(
                pl=pad_left, right=width - pad_right, y=y,
                lx=pad_left - 8, ly=y + 3, label=label, unit=unit,
            )
        )

    # A handful of evenly-spaced time labels along the bottom.
    x_label_html = []
    label_count = min(4, n)
    for k in range(label_count):
        idx = int(round(k * (n - 1) / (label_count - 1))) if label_count > 1 else 0
        ts, _ = points[idx]
        x_label_html.append(
            '<text x="{x:.1f}" y="{y}" class="chart-axis-label" text-anchor="middle">{label}</text>'.format(
                x=x_for(idx), y=height - 6, label=ts.strftime("%a %H:%M"),
            )
        )

    avg_y = y_for(avg)
    avg_line_html = (
        '<line x1="{pl}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" stroke="{colour}" '
        'stroke-width="1.2" stroke-dasharray="4,3" opacity=".55" />'.format(
            pl=pad_left, right=width - pad_right, y=avg_y, colour=colour,
        )
    )

    def fmt(v):
        return "{:.{d}f}".format(v, d=decimals)

    stats_html = (
        '<div class="chart-stats">'
        '<span>Min <strong>{vmin}{unit}</strong></span>'
        '<span>Avg <strong>{vavg}{unit}</strong></span>'
        '<span>Max <strong>{vmax}{unit}</strong></span>'
        '<span>Now <strong>{vcur}{unit}</strong></span>'
        '</div>'
    ).format(vmin=fmt(raw_min), vavg=fmt(avg), vmax=fmt(raw_max), vcur=fmt(current), unit=unit)

    svg_html = '''<svg viewBox="0 0 {w} {h}" class="sparkline" preserveAspectRatio="xMidYMid meet">
      {fill_html}
      {grid_html}
      {avg_line_html}
      <polyline fill="none" stroke="{colour}" stroke-width="2.2" points="{polyline}" />
      <circle cx="{lx}" cy="{ly}" r="4" fill="{colour}" />
      {x_label_html}
    </svg>'''.format(
        w=width, h=height, fill_html=fill_html, grid_html="".join(grid_html),
        avg_line_html=avg_line_html, colour=colour, polyline=polyline,
        lx=last_x, ly=last_y, x_label_html="".join(x_label_html),
    )

    return stats_html + svg_html


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


def outlook_card_html(rows):
    """The 'next few hours' barometer-based outlook card, or a friendly
    placeholder until there's enough pressure history to say anything."""
    outlook = barometric_outlook(rows)
    if not outlook:
        return '''<div class="outlook-card">
      <span class="eyebrow-small">Next few hours</span>
      <h2>Not enough history yet</h2>
      <p>Check back in a few hours once there's a pressure trend to read.</p>
    </div>'''
    return '''<div class="outlook-card">
      <span class="eyebrow-small">Next few hours</span>
      <h2>{headline}</h2>
      <p>{detail}</p>
      <div class="outlook-note">Based on your own station's pressure trend ({delta:+.1f} hPa / 3h) — a short-range estimate, not a multi-day forecast.</div>
    </div>'''.format(
        headline=outlook["headline"],
        detail=outlook["detail"],
        delta=outlook["delta_3h"],
    )


def frost_banner_html(frost_risk):
    """A warning banner up top when there's ground frost risk in the next
    24h — the sort of thing that actually matters if you're a gardener.
    Returns an empty string (nothing rendered) when there's no risk."""
    if not frost_risk or not frost_risk.get("at_risk"):
        return ""
    return '''<div class="frost-banner">
      <span class="frost-icon">🥶</span>
      <div>
        <strong>Frost risk in the next 24 hours</strong>
        <div>Forecast low of {temp}°C around {time} — worth covering tender plants or bringing pots in tonight.</div>
      </div>
    </div>'''.format(
        temp=fnum(frost_risk.get("min_temp_c"), 1),
        time=frost_risk.get("min_temp_time") or "overnight",
    )


def rain_forecast_svg(rain_forecast, width=640, height=190):
    """A hand-rolled SVG bar chart of the next few hours' forecast rain
    (mm per hour), with each bar's chance-of-rain percentage labelled
    above it - same house style as the sparklines, but bars rather than a
    line since this is a per-hour forecast rather than a continuous
    measured series."""
    hours = rain_forecast.get("hours") if rain_forecast else None
    if not hours:
        return '<div class="no-data">Not enough forecast data yet for an hourly rain chart.</div>'

    pad_left, pad_right, pad_top, pad_bottom = 40, 14, 22, 26
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom
    n = len(hours)

    max_mm = max((h["precip_mm"] for h in hours), default=0.0)
    axis_max = _nice_axis_step(max_mm) if max_mm > 0 else 1.0
    while axis_max < max_mm:
        axis_max += _nice_axis_step(max_mm)

    slot_w = plot_w / n
    bar_w = slot_w * 0.55

    def y_for(mm):
        return pad_top + plot_h - (mm / axis_max) * plot_h if axis_max else pad_top + plot_h

    bars_html = []
    labels_html = []
    for i, h in enumerate(hours):
        cx = pad_left + slot_w * (i + 0.5)
        mm = h["precip_mm"]
        bar_h = plot_h - (y_for(mm) - pad_top)
        bar_y = y_for(mm)
        colour = "#1F3864" if mm > 0 else "#DCE6F1"
        bars_html.append(
            '<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="3" fill="{colour}" />'.format(
                x=cx - bar_w / 2, y=bar_y, w=bar_w, h=max(bar_h, 0), colour=colour,
            )
        )
        if h.get("probability_pct") not in (None, ""):
            bars_html.append(
                '<text x="{x:.1f}" y="{y:.1f}" class="chart-axis-label" text-anchor="middle">{pct:.0f}%</text>'.format(
                    x=cx, y=max(bar_y - 6, pad_top - 4), pct=float(h["probability_pct"]),
                )
            )
        labels_html.append(
            '<text x="{x:.1f}" y="{y}" class="chart-axis-label" text-anchor="middle">{label}</text>'.format(
                x=cx, y=height - 6, label=h["time"],
            )
        )

    baseline_y = y_for(0)
    baseline_html = '<line x1="{pl}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" stroke="#DCE6F1" stroke-width="1" />'.format(
        pl=pad_left, right=width - pad_right, y=baseline_y,
    )

    return '''<svg viewBox="0 0 {w} {h}" class="sparkline" preserveAspectRatio="xMidYMid meet">
      {baseline_html}
      {bars_html}
      {labels_html}
    </svg>'''.format(
        w=width, h=height, baseline_html=baseline_html,
        bars_html="".join(bars_html), labels_html="".join(labels_html),
    )


def rain_forecast_card_html(rain_forecast):
    """Card wrapping the hourly rain forecast chart - a genuine short-range
    forecast built from Open-Meteo's own hourly precipitation/probability
    data, distinct from the Windy radar card which only shows near-real-time
    conditions rather than predicting ahead."""
    if not rain_forecast or not rain_forecast.get("hours"):
        note = "Hourly rain forecast will appear here once there's enough forecast data."
    elif rain_forecast.get("rain_expected"):
        note = "Rain expected from around {} — up to {} mm/h, {} chance at the wettest hour.".format(
            rain_forecast.get("next_wet_hour") or "soon",
            fnum(rain_forecast.get("max_precip_mm"), 1),
            "{:.0f}%".format(rain_forecast["max_probability_pct"]) if rain_forecast.get("max_probability_pct") is not None else "unknown",
        )
    else:
        note = "No rain expected over the next few hours."
    return '''<div class="card">
      <h2>Hourly rain forecast</h2>
      {svg}
      <div class="table-note">{note} Forecast from Open-Meteo's model, not your own logged readings.</div>
    </div>'''.format(svg=rain_forecast_svg(rain_forecast), note=note)


def rainfall_card_html(all_rows):
    """Rainfall totals card — today / last 7 days / this month / this year,
    summed from the *full* log (not just the last 48h chart window)."""
    totals = rainfall_totals(all_rows)
    return '''<div class="card">
      <h2>Rainfall totals</h2>
      <div class="grid stat-grid-4">
        <div class="stat light"><div class="label">Today</div><div class="val">{today} mm</div></div>
        <div class="stat light"><div class="label">Last 7 days</div><div class="val">{week} mm</div></div>
        <div class="stat light"><div class="label">This month</div><div class="val">{month} mm</div></div>
        <div class="stat light"><div class="label">This year</div><div class="val">{year} mm</div></div>
      </div>
    </div>'''.format(**totals)


def moon_daylight_card_html(latest):
    """Moon phase (pure calculation) + how much daylight there is today,
    worked out from the sunrise/sunset already fetched from Open-Meteo."""
    name, emoji = moon_phase()
    sunrise = latest.get("sunrise")
    sunset = latest.get("sunset")
    daylight = "—"
    if sunrise and sunset:
        try:
            sr = datetime.datetime.strptime(sunrise, "%H:%M")
            ss = datetime.datetime.strptime(sunset, "%H:%M")
            mins = int((ss - sr).total_seconds() / 60)
            daylight = "{}h {:02d}m".format(mins // 60, mins % 60)
        except ValueError:
            daylight = "—"
    return '''<div class="card">
      <h2>Moon &amp; daylight</h2>
      <div class="grid stat-grid-2">
        <div class="stat light"><div class="label">Moon phase</div><div class="val">{emoji} {name}</div></div>
        <div class="stat light"><div class="label">Daylight today</div><div class="val">{daylight}</div></div>
      </div>
    </div>'''.format(emoji=emoji, name=name, daylight=daylight)


def wind_rose_svg(rows, size=240):
    """A hand-rolled SVG wind rose — how often the wind's blown from each
    of 16 compass directions, as a filled radar-style polygon. No chart
    library, same house style as the sparklines above."""
    data = wind_rose_data(rows)
    if not data:
        return '<div class="no-data">Not enough wind direction data yet for a wind rose.</div>'

    counts = data["counts"]
    n = len(counts)
    max_count = max(counts) or 1
    cx = cy = size / 2
    radius = size / 2 - 26

    poly_points = []
    for i, c in enumerate(counts):
        bearing = math.radians(i * (360 / n))
        r = (c / max_count) * radius
        x = cx + r * math.sin(bearing)
        y = cy - r * math.cos(bearing)
        poly_points.append("{:.1f},{:.1f}".format(x, y))
    polygon = " ".join(poly_points)

    labels = []
    for label, idx in (("N", 0), ("E", 4), ("S", 8), ("W", 12)):
        bearing = math.radians(idx * (360 / n))
        lx = cx + (radius + 14) * math.sin(bearing)
        ly = cy - (radius + 14) * math.cos(bearing) + 4
        labels.append('<text x="{:.1f}" y="{:.1f}" class="chart-label" text-anchor="middle">{}</text>'.format(lx, ly, label))

    return '''<svg viewBox="0 0 {size} {size}" class="windrose">
      <circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="#DCE6F1" stroke-width="1" />
      <circle cx="{cx}" cy="{cy}" r="{radius_half}" fill="none" stroke="#DCE6F1" stroke-width="1" />
      <polygon points="{polygon}" fill="rgba(31,56,100,.22)" stroke="#1F3864" stroke-width="2" />
      {labels}
    </svg>'''.format(
        size=size, cx=cx, cy=cy, radius=radius, radius_half=radius / 2,
        polygon=polygon, labels="".join(labels),
    )


def wind_rose_card_html(rows):
    data = wind_rose_data(rows)
    note = (
        "Based on {} readings over this period — direction the wind was blowing from.".format(data["total"])
        if data else "Direction the wind was blowing from, once there's enough logged data."
    )
    return '''<div class="card">
      <h2>Prevailing wind</h2>
      {svg}
      <div class="table-note">{note}</div>
    </div>'''.format(svg=wind_rose_svg(rows), note=note)


def location_switcher_html(locations, current_slug, view="dashboard"):
    """Dropdown for jumping straight to another monitored location without
    going back through a menu page - one tap switches the page underneath,
    staying on the same kind of view (current conditions vs. full history)
    you were already looking at. Renders nothing when there's only one
    location, since a dropdown with a single fixed option isn't useful."""
    if not locations or len(locations) < 2:
        return ""
    options = []
    for loc in locations:
        path = loc["history_path"] if view == "history" else loc["dashboard_path"]
        selected = " selected" if loc["slug"] == current_slug else ""
        options.append('<option value="{path}"{selected}>{name}</option>'.format(
            path=path, selected=selected, name=loc["name"],
        ))
    return '''<div class="loc-switcher">
      <span class="loc-switcher-icon">\U0001F4CD</span>
      <select onchange="if (this.value) window.location.href = this.value;" aria-label="Switch location">
        {options}
      </select>
    </div>'''.format(options="".join(options))


def find_location_path(locations, current_slug, key, default):
    """Look up this location's own path for a given page type (e.g.
    "reports_path") out of the shared locations nav list, so callers don't
    need yet another explicit parameter threaded through every render()."""
    for loc in (locations or []):
        if loc.get("slug") == current_slug:
            return loc.get(key, default)
    return default


def render(location_name, latest, rows, output_path, lat=None, lon=None, all_rows=None,
           locations=None, current_slug=None, history_path="history.html"):
    if all_rows is None:
        all_rows = rows  # falls back to the chart-window rows if the full log wasn't passed in

    trend_label, trend_delta = pressure_trend(rows)
    cond_label, cond_emoji = weather_label(latest.get("weather_code"))
    generated_at = now_local().strftime("%a %d %b %Y, %H:%M")
    outlook_html = outlook_card_html(rows)
    loc_switcher_html = location_switcher_html(locations, current_slug, view="dashboard")
    reports_path = find_location_path(locations, current_slug, "reports_path", "reports.html")
    frost_html = frost_banner_html(latest.get("frost_risk"))
    rain_forecast_html = rain_forecast_card_html(latest.get("rain_forecast"))
    rainfall_html = rainfall_card_html(all_rows)
    moon_daylight_html = moon_daylight_card_html(latest)
    wind_rose_html = wind_rose_card_html(rows)

    feels_like_calc = feels_like_calculated(
        latest.get("temp_c"), latest.get("humidity_pct"), latest.get("wind_kph"),
    )
    aqi_val = latest.get("aqi")
    aqi_text_label, aqi_colour = aqi_label(aqi_val)

    trend_arrow = {"Rising": "▲", "Falling": "▼", "Steady": "▶"}.get(trend_label, "")
    trend_text = (
        "{} {} ({:+.1f} hPa / 3h)".format(trend_arrow, trend_label, trend_delta)
        if trend_label else "Not enough history yet"
    )

    temp_chart = svg_sparkline(rows, "temp_c", colour="#C0392B", unit="°C", decimals=1)
    pressure_chart = svg_sparkline(rows, "pressure_msl_hpa", colour="#1F3864", unit=" hPa", decimals=0)
    wind_chart = svg_sparkline(rows, "wind_kph", colour="#3E6FA6", unit=" km/h", decimals=0)

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
  .title-row{{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;}}
  h1{{font-size:1.5rem;color:var(--navy);margin:4px 0 2px;}}
  .loc-switcher{{display:flex;align-items:center;gap:6px;background:var(--white);border:1px solid var(--line);border-radius:10px;padding:6px 10px;}}
  .loc-switcher-icon{{font-size:.9rem;}}
  .loc-switcher select{{border:0;background:transparent;font-family:inherit;font-size:.85rem;font-weight:600;color:var(--navy);padding:2px 4px;max-width:180px;}}
  .loc-switcher select:focus{{outline:2px solid var(--navy);outline-offset:2px;}}
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
  .frost-banner{{display:flex;align-items:flex-start;gap:12px;background:#EAF4FF;border:1px solid #BBDBFA;border-left:4px solid #2E6DA4;border-radius:14px;padding:16px 18px;margin-bottom:16px;font-size:.85rem;color:var(--ink);}}
  .frost-icon{{font-size:1.4rem;line-height:1;}}
  .stat.light{{background:var(--bg);border:1px solid var(--line);}}
  .stat.light .label{{color:var(--muted);opacity:1;}}
  .stat.light .val{{color:var(--ink);}}
  .stat-grid-4{{grid-template-columns:repeat(2,1fr);}}
  .stat-grid-2{{grid-template-columns:repeat(2,1fr);}}
  @media (min-width:640px){{ .stat-grid-4{{grid-template-columns:repeat(4,1fr);}} }}
  .windrose{{width:100%;max-width:280px;height:auto;display:block;margin:0 auto;}}
  .outlook-card{{background:var(--white);border:1px solid var(--line);border-left:4px solid var(--navy);border-radius:14px;padding:18px 20px;margin-bottom:16px;}}
  .outlook-card .eyebrow-small{{font-size:.68rem;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);}}
  .outlook-card h2{{font-size:1.15rem;color:var(--navy);margin:4px 0 6px;}}
  .outlook-card p{{font-size:.88rem;color:var(--ink);}}
  .outlook-card .outlook-note{{font-size:.72rem;color:var(--muted);margin-top:10px;}}
  .radar-frame{{width:100%;border:0;border-radius:10px;display:block;aspect-ratio:16/10;}}
  .sparkline{{width:100%;height:auto;}}
  .chart-label{{font-size:9px;fill:var(--muted);}}
  .chart-axis-label{{font-size:10px;fill:var(--muted);}}
  .chart-stats{{display:flex;flex-wrap:wrap;gap:14px;font-size:.75rem;color:var(--muted);margin-bottom:10px;}}
  .chart-stats strong{{color:var(--navy);font-size:.85rem;margin-left:3px;}}
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
  <div class="title-row">
    <h1>{location_name}</h1>
    {loc_switcher_html}
  </div>
  <div class="updated">Last updated {generated_at} &middot; <a href="{history_path}">View full history &rarr;</a> &middot; <a href="{reports_path}">&#128196; Reports</a> &middot; <a href="globe.html">&#127760; Cloud Globe</a> &middot; <a href="clouds.html">&#9729;&#65039; Cloud Guide</a></div>

  {frost_html}

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
      <div class="stat"><div class="label">Feels like (calc)</div><div class="val">{feels_like_calc}°C</div></div>
      <div class="stat"><div class="label">Wind</div><div class="val">{wind} km/h {wind_dir}</div></div>
      <div class="stat"><div class="label">Gusts</div><div class="val">{gusts} km/h</div></div>
      <div class="stat"><div class="label">Rain</div><div class="val">{rain} mm</div></div>
      <div class="stat"><div class="label">Snowfall</div><div class="val">{snowfall} cm</div></div>
      <div class="stat"><div class="label">Cloud cover</div><div class="val">{cloud}%</div></div>
      <div class="stat"><div class="label">UV index</div><div class="val">{uv}</div></div>
      <div class="stat"><div class="label">Visibility</div><div class="val">{visibility} km</div></div>
      <div class="stat"><div class="label">Sunrise</div><div class="val">🌅 {sunrise}</div></div>
      <div class="stat"><div class="label">Sunset</div><div class="val">🌇 {sunset}</div></div>
      <div class="stat"><div class="label">Air quality</div><div class="val"{aqi_style}>{aqi_val}{aqi_label_suffix}</div></div>
    </div>
  </div>

  {outlook_html}

  {rain_forecast_html}

  <div class="card">
    <h2>Rain forecast radar</h2>
    <iframe class="radar-frame" src="https://embed.windy.com/embed2.html?lat={lat}&lon={lon}&zoom=8&level=surface&overlay=rain&menu=&message=true&marker=true&calendar=now&pressure=&type=map&location=coordinates&detail=&metricWind=default&metricTemp=default&radarRange=-1" loading="lazy" title="Rain forecast radar"></iframe>
    <div class="table-note">Forecast precipitation map from Windy.com — use the timeline at the bottom of the map to scrub forward and see rain approaching over the next few hours.</div>
  </div>

  {rainfall_html}

  {moon_daylight_html}

  {wind_rose_html}

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
        outlook_html=outlook_html,
        loc_switcher_html=loc_switcher_html,
        history_path=history_path,
        reports_path=reports_path,
        frost_html=frost_html,
        rain_forecast_html=rain_forecast_html,
        rainfall_html=rainfall_html,
        moon_daylight_html=moon_daylight_html,
        wind_rose_html=wind_rose_html,
        feels_like_calc=fnum(feels_like_calc, 1),
        aqi_val=fnum(aqi_val, 0) if aqi_val not in (None, "") else "—",
        aqi_label_suffix=" · {}".format(aqi_text_label) if aqi_text_label else "",
        aqi_style=' style="color:{}"'.format(aqi_colour) if aqi_colour else "",
        lat=lat if lat is not None else 52.427,
        lon=lon if lon is not None else -1.660,
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
