"""
One-time historical backfill for a brand-new location, so its History and
Reports pages aren't empty for the first month after being added.

This sandbox can't reach the internet to run this itself (see the other
test files' notes about that) - but capture.py runs on a GitHub Actions
runner, which has completely normal internet access, so this fires there
automatically on the next scheduled run after a new location is added.

Uses Open-Meteo's free Historical Weather API (https://open-meteo.com/en/docs/historical-weather-api)
- ERA5 reanalysis data blended with recent forecast-model data for the
  last few days, same no-API-key, no-cost model as the live forecast
  calls capture.py already makes. Air quality isn't backfilled (that API
  doesn't offer the same historical depth) - aqi/pm2_5/pm10 are left
  blank on backfilled rows, same as they already are on any live reading
  where the AQ fetch happened to fail.

Tracked with a small marker file (data/<slug>.backfilled) rather than by
guessing from the CSV's row count - a location can easily rack up 20+
live rows before this code even gets deployed and first runs (exactly
what happened to Kingshurst: added, then several unrelated fixes shipped
before this went live, by which point normal 15-minute captures had
already logged more rows than a naive "looks new" threshold would allow,
permanently skipping it). The marker means backfill runs exactly once
per location, whenever it first gets the chance to, regardless of
timing - not "once, but only if it's fast enough".
"""

import csv
import datetime
import json
import os
import urllib.request
import urllib.error
import urllib.parse

from weather_lib import CSV_FIELDS, now_local

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

ARCHIVE_HOURLY_VARS = [
    "temperature_2m", "relative_humidity_2m", "dew_point_2m",
    "apparent_temperature", "precipitation", "rain", "snowfall",
    "weather_code", "pressure_msl", "surface_pressure", "wind_speed_10m",
    "wind_direction_10m", "wind_gusts_10m", "cloud_cover", "is_day",
    "uv_index", "visibility",
]

BACKFILL_DAYS = 30


def _marker_path(csv_path):
    return csv_path + ".backfilled"


def _existing_rows(csv_path):
    if not os.path.exists(csv_path):
        return []
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fetch_historical(lat, lon, days=BACKFILL_DAYS, timeout=30):
    """One reading per hour for the last `days` days, up to and including
    yesterday (today is deliberately skipped - the archive API's most
    recent day is sometimes still incomplete; the regular live capture
    fills today in properly anyway). Returns a list of reading dicts
    shaped like weather_lib.fetch_current()'s, oldest first."""
    end = (now_local() - datetime.timedelta(days=1)).date()
    start = end - datetime.timedelta(days=days - 1)

    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": ",".join(ARCHIVE_HOURLY_VARS),
        "daily": "sunrise,sunset",
        "timezone": "Europe/London",
    }
    url = "{}?{}".format(ARCHIVE_URL, urllib.parse.urlencode(params))
    req = urllib.request.Request(url, headers={"User-Agent": "clearline-weather-app/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError("Open-Meteo archive request failed ({}): {}".format(e.code, body)) from e
    except urllib.error.URLError as e:
        raise RuntimeError("Could not reach Open-Meteo archive: {}".format(e.reason)) from e

    hourly = data.get("hourly", {})
    times = hourly.get("time", [])

    daily = data.get("daily", {})
    daily_dates = daily.get("time", [])
    sunrise_list = daily.get("sunrise", [])
    sunset_list = daily.get("sunset", [])
    sun_by_date = {}
    for i, d in enumerate(daily_dates):
        sunrise = sunrise_list[i][-5:] if i < len(sunrise_list) and sunrise_list[i] else None
        sunset = sunset_list[i][-5:] if i < len(sunset_list) and sunset_list[i] else None
        sun_by_date[d] = (sunrise, sunset)

    def _val(var, i):
        arr = hourly.get(var)
        if not arr or i >= len(arr):
            return None
        return arr[i]

    readings = []
    for i, t in enumerate(times):
        sunrise, sunset = sun_by_date.get(t[:10], (None, None))
        readings.append({
            "captured_at": t if len(t) > 13 else t + ":00",  # "...T13:00"
            "api_time": t,
            "temp_c": _val("temperature_2m", i),
            "apparent_c": _val("apparent_temperature", i),
            "dew_point_c": _val("dew_point_2m", i),
            "humidity_pct": _val("relative_humidity_2m", i),
            "pressure_msl_hpa": _val("pressure_msl", i),
            "surface_pressure_hpa": _val("surface_pressure", i),
            "wind_kph": _val("wind_speed_10m", i),
            "wind_dir_deg": _val("wind_direction_10m", i),
            "gusts_kph": _val("wind_gusts_10m", i),
            "precip_mm": _val("precipitation", i),
            "rain_mm": _val("rain", i),
            "snowfall_cm": _val("snowfall", i),
            "cloud_pct": _val("cloud_cover", i),
            "uv_index": _val("uv_index", i),
            "visibility_m": _val("visibility", i),
            "weather_code": _val("weather_code", i),
            "is_day": _val("is_day", i),
            "sunrise": sunrise,
            "sunset": sunset,
            "aqi": None, "pm2_5": None, "pm10": None,
        })
    return readings


def backfill_if_needed(csv_path, lat, lon, days=BACKFILL_DAYS):
    """Backfills this location exactly once, whenever it first gets the
    chance to run - tracked via a marker file, not the CSV's current row
    count (see the module docstring for why that matters). Any
    already-logged row wins over a historical one on a matching
    timestamp, so this never overwrites real captured data. Returns how
    many historical rows were added (0 if already done, or nothing came
    back from the API)."""
    marker = _marker_path(csv_path)
    if os.path.exists(marker):
        return 0

    # Deliberately not caught here - if this raises (network hiccup etc),
    # capture.py's caller catches it and logs a non-fatal warning, and the
    # marker below never gets written, so the next run just tries again.
    historical = fetch_historical(lat, lon, days=days)

    existing = _existing_rows(csv_path)
    by_captured_at = {r["captured_at"]: r for r in historical}
    for row in existing:
        by_captured_at[row.get("captured_at")] = row  # real logged data always wins

    merged = sorted(by_captured_at.values(), key=lambda r: r.get("captured_at", ""))

    os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
    if merged:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for row in merged:
                writer.writerow({k: ("" if row.get(k) in (None, "") else row.get(k)) for k in CSV_FIELDS})

    with open(marker, "w", encoding="utf-8") as f:
        f.write("Backfilled {} historical rows.\n".format(len(historical)))

    return len(historical)
