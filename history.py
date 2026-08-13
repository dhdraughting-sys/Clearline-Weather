"""
Builds history.html - a daily-summary view of the whole weather log, so
you can look back over days/weeks/months rather than just the last 48
hours shown on the main dashboard. Reads every row ever logged (no time
cutoff) and groups it by calendar day.
"""

import datetime

from dashboard import fnum, location_switcher_html, find_location_path


def _floats(rows, key):
    out = []
    for row in rows:
        val = row.get(key)
        if val in (None, ""):
            continue
        try:
            out.append(float(val))
        except (TypeError, ValueError):
            continue
    return out


def daily_summary(rows):
    """Group rows by calendar date (from captured_at) and compute simple
    min/max/avg stats for each day. Returns a list of dicts, oldest day
    first."""
    days = {}
    for row in rows:
        ts_raw = row.get("captured_at")
        if not ts_raw or len(ts_raw) < 10:
            continue
        date_key = ts_raw[:10]  # "2026-08-06"
        days.setdefault(date_key, []).append(row)

    summaries = []
    for date_key in sorted(days.keys()):
        day_rows = days[date_key]
        temps = _floats(day_rows, "temp_c")
        dew_points = _floats(day_rows, "dew_point_c")
        pressures = _floats(day_rows, "pressure_msl_hpa")
        winds = _floats(day_rows, "wind_kph")
        gusts = _floats(day_rows, "gusts_kph")
        rains = _floats(day_rows, "rain_mm")
        snow = _floats(day_rows, "snowfall_cm")
        humidities = _floats(day_rows, "humidity_pct")

        summaries.append({
            "date": date_key,
            "readings": len(day_rows),
            "temp_min": min(temps) if temps else None,
            "temp_max": max(temps) if temps else None,
            "temp_avg": (sum(temps) / len(temps)) if temps else None,
            "dew_point_avg": (sum(dew_points) / len(dew_points)) if dew_points else None,
            "pressure_min": min(pressures) if pressures else None,
            "pressure_max": max(pressures) if pressures else None,
            "wind_avg": (sum(winds) / len(winds)) if winds else None,
            "gust_max": max(gusts) if gusts else None,
            "rain_max": max(rains) if rains else None,
            "rain_total": round(sum(rains), 1) if rains else 0.0,
            "rain_seen": any(r > 0 for r in rains),
            "snow_max": max(snow) if snow else None,
            "snow_seen": any(s > 0 for s in snow),
            "humidity_avg": (sum(humidities) / len(humidities)) if humidities else None,
        })
    return summaries


def all_time_records(summaries):
    """The headline extremes across the whole log so far - hottest/coldest
    reading, wettest day, windiest gust, each with the day it happened.
    Returns None until there's at least one day of data."""
    if not summaries:
        return None

    with_temp_max = [d for d in summaries if d["temp_max"] is not None]
    with_temp_min = [d for d in summaries if d["temp_min"] is not None]
    with_rain = [d for d in summaries if d.get("rain_total")]
    with_gust = [d for d in summaries if d["gust_max"] is not None]

    return {
        "hottest": max(with_temp_max, key=lambda d: d["temp_max"]) if with_temp_max else None,
        "coldest": min(with_temp_min, key=lambda d: d["temp_min"]) if with_temp_min else None,
        "wettest": max(with_rain, key=lambda d: d["rain_total"]) if with_rain else None,
        "windiest": max(with_gust, key=lambda d: d["gust_max"]) if with_gust else None,
    }


def records_card_html(summaries):
    records = all_time_records(summaries)
    if not records:
        return '''<div class="card">
      <h2>All-time records</h2>
      <div class="no-data">Not enough data yet - check back after a day or two.</div>
    </div>'''

    def tile(label, day, value_text):
        if day is None:
            return '<div class="stat"><div class="label">{}</div><div class="val">Not enough data yet</div></div>'.format(label)
        return '<div class="stat"><div class="label">{label}</div><div class="val">{value}</div><div class="rec-date">{date}</div></div>'.format(
            label=label, value=value_text, date=_day_label(day["date"]),
        )

    hottest, coldest, wettest, windiest = (
        records["hottest"], records["coldest"], records["wettest"], records["windiest"],
    )
    tiles = "".join([
        tile("Hottest", hottest, "{}&deg;C".format(fnum(hottest["temp_max"], 1)) if hottest else ""),
        tile("Coldest", coldest, "{}&deg;C".format(fnum(coldest["temp_min"], 1)) if coldest else ""),
        tile("Wettest day", wettest, "{} mm".format(fnum(wettest["rain_total"], 1)) if wettest else ""),
        tile("Windiest gust", windiest, "{} km/h".format(fnum(windiest["gust_max"], 1)) if windiest else ""),
    ])

    return '''<div class="card">
      <h2>All-time records</h2>
      <div class="grid records-grid">{tiles}</div>
    </div>'''.format(tiles=tiles)


def _day_label(date_key):
    try:
        d = datetime.datetime.strptime(date_key, "%Y-%m-%d")
        return d.strftime("%a %d %b %Y")
    except ValueError:
        return date_key


def render(location_name, rows, output_path, days_limit=180,
           locations=None, current_slug=None, dashboard_path="index.html"):
    """rows should be the FULL log (weather_lib.load_all), not a 48h slice."""
    summaries = daily_summary(rows)
    total_days = len(summaries)
    # Newest day first for display; cap so the page doesn't grow forever
    # once you've been logging for months.
    shown = list(reversed(summaries))[:days_limit]

    if not shown:
        body_rows = '<tr><td colspan="8" class="no-data">No readings logged yet - check back after a day or two.</td></tr>'
    else:
        row_html = []
        for day in shown:
            rain_text = (
                "Yes, up to {} mm".format(fnum(day["rain_max"], 1))
                if day["rain_seen"] else "None seen"
            )
            snow_text = (
                "Yes, up to {} cm".format(fnum(day["snow_max"], 1))
                if day["snow_seen"] else "None seen"
            )
            row_html.append(
                '<tr><td>{date}</td>'
                '<td>{tmin}&ndash;{tmax}&deg;C (avg {tavg}&deg;C)</td>'
                '<td>{dew}&deg;C</td>'
                '<td>{pmin}&ndash;{pmax} hPa</td>'
                '<td>{wavg} km/h (gusts {gmax})</td>'
                '<td>{rain}</td>'
                '<td>{snow}</td>'
                '<td>{n}</td></tr>'.format(
                    date=_day_label(day["date"]),
                    tmin=fnum(day["temp_min"], 1), tmax=fnum(day["temp_max"], 1),
                    tavg=fnum(day["temp_avg"], 1),
                    dew=fnum(day["dew_point_avg"], 1),
                    pmin=fnum(day["pressure_min"], 0), pmax=fnum(day["pressure_max"], 0),
                    wavg=fnum(day["wind_avg"], 1), gmax=fnum(day["gust_max"], 1),
                    rain=rain_text,
                    snow=snow_text,
                    n=day["readings"],
                )
            )
        body_rows = "".join(row_html)

    records_html = records_card_html(summaries)
    loc_switcher_html = location_switcher_html(locations, current_slug, view="history")
    reports_path = find_location_path(locations, current_slug, "reports_path", "reports.html")

    html = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{location_name} Weather History</title>
<link rel="manifest" href="manifest.json">
<link rel="icon" href="icon-192.png">
<link rel="apple-touch-icon" href="icon-192.png">
<meta name="theme-color" content="#1F3864">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Weather">
<style>
  :root{{ --navy:#1F3864; --navy-dark:#152747; --ink:#22303F; --muted:#5C6B7A; --bg:#FAFBFC; --white:#fff; --line:#DCE6F1; }}
  *{{box-sizing:border-box;margin:0;padding:0;}}
  body{{font-family:'Segoe UI',Arial,Helvetica,sans-serif;color:var(--ink);background:var(--bg);line-height:1.5;padding-bottom:40px;}}
  .wrap{{max-width:1300px;margin:0 auto;padding:20px 16px;}}
  .eyebrow{{font-size:.72rem;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);}}
  .title-row{{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;}}
  h1{{font-size:1.5rem;color:var(--navy);margin:4px 0 8px;}}
  .loc-switcher{{display:flex;align-items:center;gap:6px;background:var(--white);border:1px solid var(--line);border-radius:10px;padding:6px 10px;}}
  .loc-switcher-icon{{font-size:.9rem;}}
  .loc-switcher select{{border:0;background:transparent;font-family:inherit;font-size:.85rem;font-weight:600;color:var(--navy);padding:2px 4px;max-width:180px;}}
  .loc-switcher select:focus{{outline:2px solid var(--navy);outline-offset:2px;}}
  .updated{{font-size:.8rem;color:var(--muted);margin-bottom:14px;}}
  .updated a{{color:var(--navy);font-weight:600;text-decoration:none;}}
  .updated a:hover{{text-decoration:underline;}}
  .back-link{{display:inline-block;font-size:.85rem;color:var(--navy);margin-bottom:18px;text-decoration:none;font-weight:600;}}
  .back-link:hover{{text-decoration:underline;}}

  .card{{background:var(--white);border:1px solid var(--line);border-radius:14px;padding:20px;margin-bottom:16px;overflow-x:auto;}}
  .grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;}}
  .records-grid{{grid-template-columns:repeat(2,1fr);}}
  @media (min-width:640px){{ .records-grid{{grid-template-columns:repeat(4,1fr);}} }}
  .stat{{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:10px 12px;}}
  .stat .label{{font-size:.68rem;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);}}
  .stat .val{{font-size:1.05rem;font-weight:700;margin-top:2px;color:var(--navy);}}
  .stat .rec-date{{font-size:.72rem;color:var(--muted);margin-top:2px;}}
  table.days{{width:100%;border-collapse:collapse;font-size:.82rem;}}
  table.days th{{text-align:left;color:var(--navy);font-size:.68rem;text-transform:uppercase;letter-spacing:.04em;padding:8px;border-bottom:2px solid var(--line);white-space:nowrap;}}
  table.days td{{padding:8px;border-bottom:1px solid var(--line);white-space:nowrap;}}
  table.days tbody tr:nth-child(even){{background:var(--bg);}}
  .no-data{{color:var(--muted);text-align:center;padding:20px;white-space:normal;}}
  .footer-note{{font-size:.75rem;color:var(--muted);text-align:center;margin-top:20px;}}
</style>
</head>
<body>
<div class="wrap">
  <span class="eyebrow">Personal Weather Log</span>
  <div class="title-row">
    <h1>{location_name} &mdash; Full History</h1>
    {loc_switcher_html}
  </div>
  <div class="updated">One row per day, newest first &middot; {total_days} day{plural} logged so far &middot; <a href="{reports_path}">&#128196; Reports</a> &middot; <a href="globe.html">&#127760; Cloud Globe</a></div>
  <a class="back-link" href="{dashboard_path}">&larr; Back to current conditions</a>

  {records_html}

  <div class="card">
    <table class="days">
      <thead><tr><th>Date</th><th>Temp (min&ndash;max, avg)</th><th>Dew point (avg)</th><th>Pressure (min&ndash;max)</th><th>Wind (avg, gusts)</th><th>Rain</th><th>Snow</th><th>Readings</th></tr></thead>
      <tbody>{body_rows}</tbody>
    </table>
  </div>

  <div class="footer-note">
    Data: Open-Meteo.com (CC-BY 4.0) &middot; showing the most recent {shown_days} of {total_days} logged day{plural}.
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
        total_days=total_days,
        plural="" if total_days == 1 else "s",
        body_rows=body_rows,
        records_html=records_html,
        loc_switcher_html=loc_switcher_html,
        reports_path=reports_path,
        dashboard_path=dashboard_path,
        shown_days=len(shown),
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
