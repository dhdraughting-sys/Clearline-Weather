"""
Builds history.html - a daily-summary view of the whole weather log, so
you can look back over days/weeks/months rather than just the last 48
hours shown on the main dashboard. Reads every row ever logged (no time
cutoff) and groups it by calendar day.
"""

import datetime

from dashboard import fnum


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
        pressures = _floats(day_rows, "pressure_msl_hpa")
        winds = _floats(day_rows, "wind_kph")
        gusts = _floats(day_rows, "gusts_kph")
        rains = _floats(day_rows, "rain_mm")
        humidities = _floats(day_rows, "humidity_pct")

        summaries.append({
            "date": date_key,
            "readings": len(day_rows),
            "temp_min": min(temps) if temps else None,
            "temp_max": max(temps) if temps else None,
            "temp_avg": (sum(temps) / len(temps)) if temps else None,
            "pressure_min": min(pressures) if pressures else None,
            "pressure_max": max(pressures) if pressures else None,
            "wind_avg": (sum(winds) / len(winds)) if winds else None,
            "gust_max": max(gusts) if gusts else None,
            "rain_max": max(rains) if rains else None,
            "rain_seen": any(r > 0 for r in rains),
            "humidity_avg": (sum(humidities) / len(humidities)) if humidities else None,
        })
    return summaries


def _day_label(date_key):
    try:
        d = datetime.datetime.strptime(date_key, "%Y-%m-%d")
        return d.strftime("%a %d %b %Y")
    except ValueError:
        return date_key


def render(location_name, rows, output_path, days_limit=180):
    """rows should be the FULL log (weather_lib.load_all), not a 48h slice."""
    summaries = daily_summary(rows)
    total_days = len(summaries)
    # Newest day first for display; cap so the page doesn't grow forever
    # once you've been logging for months.
    shown = list(reversed(summaries))[:days_limit]

    if not shown:
        body_rows = '<tr><td colspan="6" class="no-data">No readings logged yet - check back after a day or two.</td></tr>'
    else:
        row_html = []
        for day in shown:
            rain_text = (
                "Yes, up to {} mm".format(fnum(day["rain_max"], 1))
                if day["rain_seen"] else "None seen"
            )
            row_html.append(
                '<tr><td>{date}</td>'
                '<td>{tmin}&ndash;{tmax}&deg;C (avg {tavg}&deg;C)</td>'
                '<td>{pmin}&ndash;{pmax} hPa</td>'
                '<td>{wavg} km/h (gusts {gmax})</td>'
                '<td>{rain}</td>'
                '<td>{n}</td></tr>'.format(
                    date=_day_label(day["date"]),
                    tmin=fnum(day["temp_min"], 1), tmax=fnum(day["temp_max"], 1),
                    tavg=fnum(day["temp_avg"], 1),
                    pmin=fnum(day["pressure_min"], 0), pmax=fnum(day["pressure_max"], 0),
                    wavg=fnum(day["wind_avg"], 1), gmax=fnum(day["gust_max"], 1),
                    rain=rain_text,
                    n=day["readings"],
                )
            )
        body_rows = "".join(row_html)

    html = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{location_name} Weather History</title>
<style>
  :root{{ --navy:#1F3864; --navy-dark:#152747; --ink:#22303F; --muted:#5C6B7A; --bg:#FAFBFC; --white:#fff; --line:#DCE6F1; }}
  *{{box-sizing:border-box;margin:0;padding:0;}}
  body{{font-family:'Segoe UI',Arial,Helvetica,sans-serif;color:var(--ink);background:var(--bg);line-height:1.5;padding-bottom:40px;}}
  .wrap{{max-width:900px;margin:0 auto;padding:20px 16px;}}
  .eyebrow{{font-size:.72rem;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);}}
  h1{{font-size:1.5rem;color:var(--navy);margin:4px 0 8px;}}
  .updated{{font-size:.8rem;color:var(--muted);margin-bottom:14px;}}
  .back-link{{display:inline-block;font-size:.85rem;color:var(--navy);margin-bottom:18px;text-decoration:none;font-weight:600;}}
  .back-link:hover{{text-decoration:underline;}}

  .card{{background:var(--white);border:1px solid var(--line);border-radius:14px;padding:20px;margin-bottom:16px;overflow-x:auto;}}
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
  <h1>{location_name} &mdash; Full History</h1>
  <div class="updated">One row per day, newest first &middot; {total_days} day{plural} logged so far</div>
  <a class="back-link" href="index.html">&larr; Back to current conditions</a>

  <div class="card">
    <table class="days">
      <thead><tr><th>Date</th><th>Temp (min&ndash;max, avg)</th><th>Pressure (min&ndash;max)</th><th>Wind (avg, gusts)</th><th>Rain</th><th>Readings</th></tr></thead>
      <tbody>{body_rows}</tbody>
    </table>
  </div>

  <div class="footer-note">
    Data: Open-Meteo.com (CC-BY 4.0) &middot; showing the most recent {shown_days} of {total_days} logged day{plural}.
  </div>
</div>
</body>
</html>'''.format(
        location_name=location_name,
        total_days=total_days,
        plural="" if total_days == 1 else "s",
        body_rows=body_rows,
        shown_days=len(shown),
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
