"""
Builds reports.html - a printable summary report (Yesterday / Last 7 days
/ Last 30 days / Last 12 months / All time / a custom date range), with
both charts and a data table for whatever period you pick, and a "Save
as PDF" button that just uses the browser's own Print dialog - no PDF
library needed, works offline, and every browser already knows how to
save a print job as a PDF.

One page per location, same paths pattern as dashboard.py/history.py.

The day-by-day numbers (reusing history.daily_summary()) are computed
once here and embedded directly in the page as a small JSON array - the
period picker then filters/aggregates that array and redraws the charts
entirely client-side, so switching between "last week" and "last month"
is instant and doesn't need a page reload or a server.
"""

import json

from dashboard import location_switcher_html
from history import daily_summary, _day_label


def _summaries_json(rows):
    summaries = daily_summary(rows)
    compact = []
    for d in summaries:
        compact.append({
            "date": d["date"],
            "label": _day_label(d["date"]),
            "temp_min": d["temp_min"], "temp_max": d["temp_max"], "temp_avg": d["temp_avg"],
            "rain_total": d["rain_total"], "gust_max": d["gust_max"], "wind_avg": d["wind_avg"],
            "humidity_avg": d["humidity_avg"],
            "pressure_min": d["pressure_min"], "pressure_max": d["pressure_max"],
        })
    return json.dumps(compact)


def render(location_name, rows, output_path="reports.html",
           locations=None, current_slug=None, dashboard_path="index.html"):
    days_json = _summaries_json(rows)
    loc_switcher_html = location_switcher_html(locations, current_slug, view="dashboard")

    html = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{location_name} Weather Reports</title>
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
  .back-link{{display:inline-block;font-size:.85rem;color:var(--navy);margin:8px 0 18px;text-decoration:none;font-weight:600;}}
  .back-link:hover{{text-decoration:underline;}}

  .period-bar{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:16px;}}
  .period-btn{{background:var(--white);border:1px solid var(--line);border-radius:999px;padding:8px 14px;font-size:.82rem;font-weight:600;color:var(--navy);cursor:pointer;}}
  .period-btn.active{{background:var(--navy);color:#fff;border-color:var(--navy);}}
  .period-custom{{display:flex;flex-wrap:wrap;align-items:center;gap:6px;font-size:.82rem;color:var(--muted);}}
  .period-custom input{{font-family:inherit;font-size:.82rem;padding:6px 8px;border:1px solid var(--line);border-radius:8px;}}
  .print-btn{{margin-left:auto;background:var(--accent);color:#fff;border:0;border-radius:999px;padding:9px 18px;font-size:.82rem;font-weight:700;cursor:pointer;}}

  .print-only{{display:none;}}
  .card{{background:var(--white);border:1px solid var(--line);border-radius:14px;padding:20px;margin-bottom:16px;}}
  .card h2{{font-size:.95rem;color:var(--navy);margin-bottom:10px;}}
  .grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;}}
  @media (min-width:640px){{ .grid{{grid-template-columns:repeat(4,1fr);}} }}
  .stat{{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:10px 12px;}}
  .stat .label{{font-size:.68rem;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);}}
  .stat .val{{font-size:1.05rem;font-weight:700;margin-top:2px;color:var(--navy);}}
  .stat .rec-date{{font-size:.72rem;color:var(--muted);margin-top:2px;}}
  .chart-axis-label{{font-size:10px;fill:var(--muted);}}
  .chart-stats{{display:flex;flex-wrap:wrap;gap:14px;font-size:.75rem;color:var(--muted);margin-bottom:8px;}}
  .chart-stats strong{{color:var(--navy);font-size:.85rem;margin-left:3px;}}
  .sparkline{{width:100%;height:auto;}}
  .no-data{{font-size:.85rem;color:var(--muted);padding:16px 0;text-align:center;}}
  table.days{{width:100%;border-collapse:collapse;font-size:.8rem;}}
  table.days th{{text-align:left;color:var(--navy);font-size:.66rem;text-transform:uppercase;letter-spacing:.04em;padding:7px;border-bottom:2px solid var(--line);white-space:nowrap;}}
  table.days td{{padding:7px;border-bottom:1px solid var(--line);white-space:nowrap;}}
  table.days tbody tr:nth-child(even){{background:var(--bg);}}
  .table-wrap{{overflow-x:auto;}}
  .table-note{{font-size:.72rem;color:var(--muted);margin-top:10px;}}
  .footer-note{{font-size:.75rem;color:var(--muted);text-align:center;margin-top:20px;}}

  @page {{ size: A4; margin: 16mm; }}
  @media print {{
    body{{background:#fff;padding-bottom:0;}}
    .no-print{{display:none !important;}}
    .print-only{{display:block;}}
    .wrap{{max-width:100%;padding:0;}}
    .card{{border:1px solid #ccc;break-inside:avoid;}}
    a[href]{{color:inherit;text-decoration:none;}}
  }}
</style>
</head>
<body>
<div class="wrap">
  <div class="no-print">
    <span class="eyebrow">Personal Weather Log</span>
    <div class="title-row">
      <h1>Reports</h1>
      {loc_switcher_html}
    </div>
    <a class="back-link" href="{dashboard_path}">&larr; Back to current conditions</a>

    <div class="period-bar">
      <button class="period-btn" data-period="yesterday">Yesterday</button>
      <button class="period-btn" data-period="7">Last 7 days</button>
      <button class="period-btn" data-period="30">Last 30 days</button>
      <button class="period-btn" data-period="365">Last 12 months</button>
      <button class="period-btn" data-period="all">All time</button>
      <span class="period-custom">
        or <input type="date" id="custom-from"> to <input type="date" id="custom-to">
        <button class="period-btn" data-period="custom">Apply</button>
      </span>
      <button class="print-btn" id="print-btn">&#128424; Save as PDF</button>
    </div>
  </div>

  <div class="print-only" id="print-header">
    <span class="eyebrow">Personal Weather Log</span>
    <h1>{location_name} &mdash; <span id="print-period-label"></span></h1>
    <div class="table-note">Generated <span id="print-generated-at"></span> &middot; Data: Open-Meteo.com (CC-BY 4.0)</div>
  </div>

  <div id="report"></div>

  <div class="footer-note no-print">
    Pick a period above, then use <strong>Save as PDF</strong> - your browser's own Print dialog has a "Save as PDF" /
    "Microsoft Print to PDF" destination built in, no extra software needed.
  </div>
</div>
<script>
var DAYS = {days_json};

function fnum(v, d) {{
  if (v === null || v === undefined || v === '') return '\\u2014';
  var n = Number(v);
  if (isNaN(n)) return String(v);
  return n.toFixed(d === undefined ? 1 : d);
}}

function nowLabel() {{
  var d = new Date();
  var days = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  function pad(n) {{ return n < 10 ? '0' + n : n; }}
  return days[d.getDay()] + ' ' + pad(d.getDate()) + ' ' + months[d.getMonth()] + ' ' + d.getFullYear() +
    ', ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
}}

function selectPeriod(period, customFrom, customTo) {{
  if (!DAYS.length) return {{ days: [], label: 'No data yet' }};
  var sorted = DAYS.slice().sort(function (a, b) {{ return a.date < b.date ? -1 : 1; }});
  var last = sorted[sorted.length - 1];
  var days, label;
  if (period === 'yesterday') {{
    days = sorted.slice(-1);
    label = 'Most recent day (' + last.label + ')';
  }} else if (period === '7') {{
    days = sorted.slice(-7);
    label = 'Last 7 days';
  }} else if (period === '30') {{
    days = sorted.slice(-30);
    label = 'Last 30 days';
  }} else if (period === '365') {{
    days = sorted.slice(-365);
    label = 'Last 12 months';
  }} else if (period === 'custom' && customFrom && customTo) {{
    days = sorted.filter(function (d) {{ return d.date >= customFrom && d.date <= customTo; }});
    label = customFrom + ' to ' + customTo;
  }} else {{
    days = sorted;
    label = 'All time';
  }}
  return {{ days: days, label: label }};
}}

function aggregate(days) {{
  if (!days.length) return null;
  var tmins = days.map(function (d) {{ return d.temp_min; }}).filter(function (v) {{ return v !== null; }});
  var tmaxs = days.map(function (d) {{ return d.temp_max; }}).filter(function (v) {{ return v !== null; }});
  var tavgs = days.map(function (d) {{ return d.temp_avg; }}).filter(function (v) {{ return v !== null; }});
  var rains = days.map(function (d) {{ return d.rain_total || 0; }});
  var gusts = days.map(function (d) {{ return d.gust_max; }}).filter(function (v) {{ return v !== null; }});
  var winds = days.map(function (d) {{ return d.wind_avg; }}).filter(function (v) {{ return v !== null; }});
  var hums = days.map(function (d) {{ return d.humidity_avg; }}).filter(function (v) {{ return v !== null; }});
  var pmins = days.map(function (d) {{ return d.pressure_min; }}).filter(function (v) {{ return v !== null; }});
  var pmaxs = days.map(function (d) {{ return d.pressure_max; }}).filter(function (v) {{ return v !== null; }});
  function avg(a) {{ return a.length ? a.reduce(function (x, y) {{ return x + y; }}, 0) / a.length : null; }}
  function hottest() {{
    return days.reduce(function (best, d) {{
      return (d.temp_max !== null && (!best || d.temp_max > best.temp_max)) ? d : best;
    }}, null);
  }}
  function coldest() {{
    return days.reduce(function (best, d) {{
      return (d.temp_min !== null && (!best || d.temp_min < best.temp_min)) ? d : best;
    }}, null);
  }}
  function wettest() {{
    return days.reduce(function (best, d) {{
      return (d.rain_total && (!best || d.rain_total > best.rain_total)) ? d : best;
    }}, null);
  }}
  return {{
    n: days.length,
    temp_min: tmins.length ? Math.min.apply(null, tmins) : null,
    temp_max: tmaxs.length ? Math.max.apply(null, tmaxs) : null,
    temp_avg: avg(tavgs),
    rain_total: rains.reduce(function (x, y) {{ return x + y; }}, 0),
    gust_max: gusts.length ? Math.max.apply(null, gusts) : null,
    wind_avg: avg(winds),
    humidity_avg: avg(hums),
    pressure_min: pmins.length ? Math.min.apply(null, pmins) : null,
    pressure_max: pmaxs.length ? Math.max.apply(null, pmaxs) : null,
    hottest: hottest(), coldest: coldest(), wettest: wettest(),
  }};
}}

function niceStep(range, targetTicks) {{
  targetTicks = targetTicks || 4;
  if (range <= 0) return 1;
  var raw = range / targetTicks;
  var mag = Math.pow(10, Math.floor(Math.log10(raw)));
  var mults = [1, 2, 5, 10];
  for (var i = 0; i < mults.length; i++) {{
    if (mults[i] * mag >= raw) return mults[i] * mag;
  }}
  return 10 * mag;
}}

function lineChart(days, key, colour, unit, decimals) {{
  var pts = days.map(function (d) {{ return {{ label: d.label, value: d[key] }}; }})
    .filter(function (p) {{ return p.value !== null && p.value !== undefined; }});
  if (pts.length < 2) {{
    return '<div class="no-data">Not enough days in this period for a chart.</div>';
  }}
  var width = 640, height = 200, padLeft = 58, padRight = 14, padTop = 16, padBottom = 26;
  var values = pts.map(function (p) {{ return p.value; }});
  var rawMin = Math.min.apply(null, values), rawMax = Math.max.apply(null, values);
  var avgV = values.reduce(function (a, b) {{ return a + b; }}, 0) / values.length;
  var current = values[values.length - 1];
  if (rawMax === rawMin) rawMax = rawMin + 1;
  var step = niceStep(rawMax - rawMin);
  var gridMin = Math.floor(rawMin / step) * step, gridMax = Math.ceil(rawMax / step) * step;
  if (gridMax === gridMin) gridMax = gridMin + step;
  var plotW = width - padLeft - padRight, plotH = height - padTop - padBottom;
  var n = pts.length;
  function xFor(i) {{ return padLeft + (i / (n - 1)) * plotW; }}
  function yFor(v) {{ return padTop + plotH - ((v - gridMin) / (gridMax - gridMin)) * plotH; }}
  var coords = pts.map(function (p, i) {{ return xFor(i).toFixed(1) + ',' + yFor(p.value).toFixed(1); }});
  var polyline = coords.join(' ');
  var lastXY = coords[coords.length - 1].split(',');

  var baseline = padTop + plotH;
  var fillPoints = polyline + ' ' + xFor(n - 1).toFixed(1) + ',' + baseline.toFixed(1) + ' ' + xFor(0).toFixed(1) + ',' + baseline.toFixed(1);
  var fillHtml = '<polygon points="' + fillPoints + '" fill="' + colour + '" opacity=".10" />';

  var gridHtml = '';
  var nTicks = Math.round((gridMax - gridMin) / step) + 1;
  for (var t = 0; t < nTicks; t++) {{
    var val = gridMin + t * step;
    var y = yFor(val);
    var label = (decimals === 0 || Number.isInteger(val)) ? val.toFixed(0) : val.toFixed(decimals);
    gridHtml += '<line x1="' + padLeft + '" y1="' + y.toFixed(1) + '" x2="' + (width - padRight) + '" y2="' + y.toFixed(1) + '" stroke="#E7EEF6" stroke-width="1" />';
    gridHtml += '<text x="' + (padLeft - 8) + '" y="' + (y + 3).toFixed(1) + '" class="chart-axis-label" text-anchor="end">' + label + unit + '</text>';
  }}

  var xLabelHtml = '';
  var labelCount = Math.min(4, n);
  for (var k = 0; k < labelCount; k++) {{
    var idx = labelCount > 1 ? Math.round(k * (n - 1) / (labelCount - 1)) : 0;
    xLabelHtml += '<text x="' + xFor(idx).toFixed(1) + '" y="' + (height - 6) + '" class="chart-axis-label" text-anchor="middle">' + pts[idx].label.slice(4, 10) + '</text>';
  }}

  var avgY = yFor(avgV);
  var avgLineHtml = '<line x1="' + padLeft + '" y1="' + avgY.toFixed(1) + '" x2="' + (width - padRight) + '" y2="' + avgY.toFixed(1) + '" stroke="' + colour + '" stroke-width="1.2" stroke-dasharray="4,3" opacity=".55" />';

  var statsHtml = '<div class="chart-stats">' +
    '<span>Min <strong>' + rawMin.toFixed(decimals) + unit + '</strong></span>' +
    '<span>Avg <strong>' + avgV.toFixed(decimals) + unit + '</strong></span>' +
    '<span>Max <strong>' + rawMax.toFixed(decimals) + unit + '</strong></span>' +
    '<span>Latest <strong>' + current.toFixed(decimals) + unit + '</strong></span>' +
    '</div>';

  var svg = '<svg viewBox="0 0 ' + width + ' ' + height + '" class="sparkline" preserveAspectRatio="xMidYMid meet">' +
    fillHtml + gridHtml + avgLineHtml +
    '<polyline fill="none" stroke="' + colour + '" stroke-width="2.2" points="' + polyline + '" />' +
    '<circle cx="' + lastXY[0] + '" cy="' + lastXY[1] + '" r="4" fill="' + colour + '" />' +
    xLabelHtml + '</svg>';

  return statsHtml + svg;
}}

function daysTableHtml(days) {{
  if (!days.length) return '<div class="no-data">No days in this period.</div>';
  var limit = 400;
  var shown = days.slice().reverse().slice(0, limit);
  var rowsHtml = shown.map(function (d) {{
    return '<tr><td>' + d.label + '</td>' +
      '<td>' + fnum(d.temp_min, 1) + '&ndash;' + fnum(d.temp_max, 1) + '&deg;C (avg ' + fnum(d.temp_avg, 1) + '&deg;C)</td>' +
      '<td>' + fnum(d.pressure_min, 0) + '&ndash;' + fnum(d.pressure_max, 0) + ' hPa</td>' +
      '<td>' + fnum(d.wind_avg, 1) + ' km/h (gusts ' + fnum(d.gust_max, 1) + ')</td>' +
      '<td>' + fnum(d.rain_total, 1) + ' mm</td>' +
      '<td>' + fnum(d.humidity_avg, 0) + '%</td></tr>';
  }}).join('');
  var note = days.length > limit
    ? 'Showing the most recent ' + limit + ' of ' + days.length + ' days in this period.'
    : days.length + ' day' + (days.length === 1 ? '' : 's') + ' in this period.';
  return '<div class="table-wrap"><table class="days">' +
    '<thead><tr><th>Date</th><th>Temp (min&ndash;max, avg)</th><th>Pressure</th><th>Wind (avg, gusts)</th><th>Rain</th><th>Humidity</th></tr></thead>' +
    '<tbody>' + rowsHtml + '</tbody></table></div><div class="table-note">' + note + '</div>';
}}

function recordTile(label, day, valueText) {{
  if (!day) return '<div class="stat"><div class="label">' + label + '</div><div class="val">Not enough data</div></div>';
  return '<div class="stat"><div class="label">' + label + '</div><div class="val">' + valueText + '</div><div class="rec-date">' + day.label + '</div></div>';
}}

function renderReport(period, customFrom, customTo) {{
  var sel = selectPeriod(period, customFrom, customTo);
  var agg = aggregate(sel.days);
  document.getElementById('print-period-label').textContent = sel.label;
  document.getElementById('print-generated-at').textContent = nowLabel();

  if (!agg) {{
    document.getElementById('report').innerHTML = '<div class="card"><div class="no-data">No data logged for this period yet.</div></div>';
    return;
  }}

  var summaryHtml = '<div class="card"><h2>' + sel.label + ' &mdash; summary (' + agg.n + ' day' + (agg.n === 1 ? '' : 's') + ')</h2>' +
    '<div class="grid">' +
    '<div class="stat"><div class="label">Temp range</div><div class="val">' + fnum(agg.temp_min, 1) + '&ndash;' + fnum(agg.temp_max, 1) + '&deg;C</div></div>' +
    '<div class="stat"><div class="label">Avg temp</div><div class="val">' + fnum(agg.temp_avg, 1) + '&deg;C</div></div>' +
    '<div class="stat"><div class="label">Total rainfall</div><div class="val">' + fnum(agg.rain_total, 1) + ' mm</div></div>' +
    '<div class="stat"><div class="label">Max gust</div><div class="val">' + fnum(agg.gust_max, 1) + ' km/h</div></div>' +
    '<div class="stat"><div class="label">Avg wind</div><div class="val">' + fnum(agg.wind_avg, 1) + ' km/h</div></div>' +
    '<div class="stat"><div class="label">Avg humidity</div><div class="val">' + fnum(agg.humidity_avg, 0) + '%</div></div>' +
    '<div class="stat"><div class="label">Pressure range</div><div class="val">' + fnum(agg.pressure_min, 0) + '&ndash;' + fnum(agg.pressure_max, 0) + ' hPa</div></div>' +
    '</div></div>';

  var highlightsHtml = '<div class="card"><h2>Highlights</h2><div class="grid">' +
    recordTile('Hottest day', agg.hottest, agg.hottest ? fnum(agg.hottest.temp_max, 1) + '&deg;C' : '') +
    recordTile('Coldest day', agg.coldest, agg.coldest ? fnum(agg.coldest.temp_min, 1) + '&deg;C' : '') +
    recordTile('Wettest day', agg.wettest, agg.wettest ? fnum(agg.wettest.rain_total, 1) + ' mm' : '') +
    '</div></div>';

  var chartsHtml = '<div class="card"><h2>Temperature (daily avg)</h2>' + lineChart(sel.days, 'temp_avg', '#C0392B', '\\u00b0C', 1) + '</div>' +
    '<div class="card"><h2>Rainfall (daily total)</h2>' + lineChart(sel.days, 'rain_total', '#1F6FEB', ' mm', 1) + '</div>' +
    '<div class="card"><h2>Pressure (daily min)</h2>' + lineChart(sel.days, 'pressure_min', '#1F3864', ' hPa', 0) + '</div>';

  var tableHtml = '<div class="card"><h2>Day by day</h2>' + daysTableHtml(sel.days) + '</div>';

  document.getElementById('report').innerHTML = summaryHtml + highlightsHtml + chartsHtml + tableHtml;
}}

var buttons = document.querySelectorAll('.period-btn');
buttons.forEach(function (btn) {{
  btn.addEventListener('click', function () {{
    buttons.forEach(function (b) {{ b.classList.remove('active'); }});
    if (btn.dataset.period !== 'custom') btn.classList.add('active');
    var from = document.getElementById('custom-from').value;
    var to = document.getElementById('custom-to').value;
    renderReport(btn.dataset.period, from, to);
  }});
}});
document.getElementById('print-btn').addEventListener('click', function () {{ window.print(); }});

if (DAYS.length) {{
  var minDate = DAYS.reduce(function (m, d) {{ return d.date < m ? d.date : m; }}, DAYS[0].date);
  var maxDate = DAYS.reduce(function (m, d) {{ return d.date > m ? d.date : m; }}, DAYS[0].date);
  document.getElementById('custom-from').min = minDate;
  document.getElementById('custom-from').max = maxDate;
  document.getElementById('custom-to').min = minDate;
  document.getElementById('custom-to').max = maxDate;
}}

// Default view: last 7 days.
buttons[1].classList.add('active');
renderReport('7');
</script>
</body>
</html>'''.format(
        location_name=location_name,
        loc_switcher_html=loc_switcher_html,
        dashboard_path=dashboard_path,
        days_json=days_json,
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
