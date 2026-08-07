"""
Shared logic for the Clearline Weather personal capture tool.

Pulls near-real-time current conditions from Open-Meteo's Forecast API
(api.open-meteo.com) — no API key needed for free non-commercial use, no
60-minute caching restriction like WeatherAPI.com (this just logs a
snapshot every run, it doesn't cache/replay a single response).

This is entirely local: nothing here talks to GitHub, D3D, Clearline Web,
or any hosting platform. It reads/writes files on this PC only.

Docs: https://open-meteo.com/en/docs
"""

import csv
import datetime
import json
import os
import urllib.request
import urllib.error
import urllib.parse
from zoneinfo import ZoneInfo

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

UK_TZ = ZoneInfo("Europe/London")


def now_local():
    """UK wall-clock time (correctly handling the BST/GMT switch), as a
    naive datetime with no tzinfo attached - so it stays directly
    comparable with the plain timestamps already stored in the CSV log.

    This matters because this script runs on a GitHub Actions runner,
    which defaults to UTC - datetime.datetime.now() alone would silently
    log everything an hour behind during British Summer Time."""
    return datetime.datetime.now(UK_TZ).replace(tzinfo=None)

CURRENT_VARS = [
    "temperature_2m", "relative_humidity_2m", "dew_point_2m",
    "apparent_temperature", "precipitation", "rain", "snowfall",
    "weather_code", "pressure_msl", "surface_pressure", "wind_speed_10m",
    "wind_direction_10m", "wind_gusts_10m", "cloud_cover", "is_day",
]
# uv_index and visibility aren't in the `current` block - pulled from the
# current hour's `hourly` value instead.
HOURLY_EXTRA_VARS = ["uv_index", "visibility"]

CSV_FIELDS = [
    "captured_at", "api_time", "temp_c", "apparent_c", "dew_point_c",
    "humidity_pct", "pressure_msl_hpa", "surface_pressure_hpa", "wind_kph",
    "wind_dir_deg", "gusts_kph", "precip_mm", "rain_mm", "snowfall_cm",
    "cloud_pct", "uv_index", "visibility_m", "weather_code", "is_day",
]

# Rough mapping of Open-Meteo's WMO weather_code to a short label + emoji,
# just for the dashboard - not exhaustive, falls back to the raw code.
WEATHER_CODE_LABELS = {
    0: ("Clear sky", "☀️"), 1: ("Mainly clear", "\U0001F324️"),
    2: ("Partly cloudy", "⛅"), 3: ("Overcast", "☁️"),
    45: ("Fog", "\U0001F32B️"), 48: ("Depositing rime fog", "\U0001F32B️"),
    51: ("Light drizzle", "\U0001F327️"), 53: ("Drizzle", "\U0001F327️"),
    55: ("Dense drizzle", "\U0001F327️"),
    61: ("Slight rain", "\U0001F327️"), 63: ("Rain", "\U0001F327️"),
    65: ("Heavy rain", "\U0001F327️"),
    71: ("Slight snow", "\U0001F328️"), 73: ("Snow", "\U0001F328️"),
    75: ("Heavy snow", "\U0001F328️"),
    80: ("Rain showers", "\U0001F326️"), 81: ("Rain showers", "\U0001F326️"),
    82: ("Violent rain showers", "⛈️"),
    95: ("Thunderstorm", "⛈️"), 96: ("Thunderstorm + hail", "⛈️"),
    99: ("Thunderstorm + heavy hail", "⛈️"),
}


def load_locations(path="locations.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_current(lat, lon, timeout=20):
    """Call Open-Meteo for one location, return a flat reading dict."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ",".join(CURRENT_VARS),
        "hourly": ",".join(HOURLY_EXTRA_VARS),
        "forecast_days": 1,
        "timezone": "Europe/London",
    }
    url = "{}?{}".format(FORECAST_URL, urllib.parse.urlencode(params))
    req = urllib.request.Request(url, headers={"User-Agent": "clearline-weather-app/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError("Open-Meteo request failed ({}): {}".format(e.code, body)) from e
    except urllib.error.URLError as e:
        raise RuntimeError("Could not reach Open-Meteo: {}".format(e.reason)) from e

    cur = data.get("current")
    if not cur:
        raise RuntimeError("Unexpected response shape, no 'current' block: {}".format(data))

    # Pick the hourly value matching current's hour for uv_index/visibility.
    hourly = data.get("hourly", {})
    hourly_times = hourly.get("time", [])
    uv_index = visibility = None
    api_time = cur.get("time")  # e.g. "2026-08-05T23:45"
    if api_time and hourly_times:
        current_hour_key = api_time[:13]  # "2026-08-05T23"
        for i, t in enumerate(hourly_times):
            if t[:13] == current_hour_key:
                uv_list = hourly.get("uv_index", [])
                vis_list = hourly.get("visibility", [])
                uv_index = uv_list[i] if i < len(uv_list) else None
                visibility = vis_list[i] if i < len(vis_list) else None
                break

    captured_at_local = now_local().isoformat(timespec="seconds")

    return {
        "captured_at": captured_at_local,
        "api_time": api_time,
        "temp_c": cur.get("temperature_2m"),
        "apparent_c": cur.get("apparent_temperature"),
        "dew_point_c": cur.get("dew_point_2m"),
        "humidity_pct": cur.get("relative_humidity_2m"),
        "pressure_msl_hpa": cur.get("pressure_msl"),
        "surface_pressure_hpa": cur.get("surface_pressure"),
        "wind_kph": cur.get("wind_speed_10m"),
        "wind_dir_deg": cur.get("wind_direction_10m"),
        "gusts_kph": cur.get("wind_gusts_10m"),
        "precip_mm": cur.get("precipitation"),
        "rain_mm": cur.get("rain"),
        "snowfall_cm": cur.get("snowfall"),
        "cloud_pct": cur.get("cloud_cover"),
        "uv_index": uv_index,
        "visibility_m": visibility,
        "weather_code": cur.get("weather_code"),
        "is_day": cur.get("is_day"),
    }


def _migrate_header_if_needed(csv_path):
    """If the CSV's header doesn't match the current CSV_FIELDS (e.g. new
    columns like dew point / snowfall were added in a later version),
    rewrite the file with the new header - existing rows just get blank
    values for the new columns. Runs automatically so the log growing in
    the GitHub repo self-heals on the next capture rather than silently
    misaligning columns forever."""
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        first_line = f.readline()
    if not first_line:
        return  # empty file, nothing to migrate
    header = next(csv.reader([first_line]))
    if header == CSV_FIELDS:
        return

    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        existing_rows = list(csv.DictReader(f))

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in existing_rows:
            writer.writerow({k: row.get(k, "") for k in CSV_FIELDS})


def append_reading(csv_path, reading):
    """Append one reading to the CSV log. Skips it if the API's own
    api_time exactly matches the last logged row (guards against duplicate
    rows if the task happens to run twice back-to-back)."""
    os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
    file_exists = os.path.exists(csv_path)

    if file_exists:
        _migrate_header_if_needed(csv_path)
        last_row = None
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            for last_row in csv.DictReader(f):
                pass
        if last_row and last_row.get("api_time") == reading.get("api_time"):
            return False  # duplicate, nothing new since last run

    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow({k: ("" if v is None else v) for k, v in reading.items()})
    return True


def load_all(csv_path):
    """Load every row ever logged, oldest first - no time cutoff. Used for
    the long-term history page; load_recent() below is for the charts/table
    that only care about the last N hours."""
    if not os.path.exists(csv_path):
        return []
    rows = []
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    rows.sort(key=lambda r: r.get("captured_at", ""))
    return rows


def load_recent(csv_path, hours=48):
    """Load rows from the last `hours` hours (by captured_at), oldest first."""
    if not os.path.exists(csv_path):
        return []
    cutoff = now_local() - datetime.timedelta(hours=hours)
    rows = []
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                ts = datetime.datetime.fromisoformat(row["captured_at"])
            except (ValueError, KeyError):
                continue
            if ts >= cutoff:
                rows.append(row)
    rows.sort(key=lambda r: r["captured_at"])
    return rows


def pressure_trend(rows, hours=3):
    """Rising / Falling / Steady, comparing the latest reading to the
    reading closest to `hours` ago - the classic barometer trend signal."""
    if len(rows) < 2:
        return None, None
    latest = rows[-1]
    try:
        latest_p = float(latest["pressure_msl_hpa"])
        latest_t = datetime.datetime.fromisoformat(latest["captured_at"])
    except (ValueError, KeyError):
        return None, None

    target_t = latest_t - datetime.timedelta(hours=hours)
    best_row, best_diff = None, None
    for row in rows[:-1]:
        try:
            t = datetime.datetime.fromisoformat(row["captured_at"])
            p = float(row["pressure_msl_hpa"])
        except (ValueError, KeyError):
            continue
        diff = abs((t - target_t).total_seconds())
        if best_diff is None or diff < best_diff:
            best_diff, best_row, best_p = diff, row, p

    if best_row is None:
        return None, None

    delta = round(latest_p - best_p, 1)
    if delta >= 1.0:
        return "Rising", delta
    if delta <= -1.0:
        return "Falling", delta
    return "Steady", delta
