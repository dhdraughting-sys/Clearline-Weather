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
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

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
# current hour's `hourly` value instead. temperature_2m is also pulled
# hourly (in addition to the `current` block's own reading) purely so we
# have a short run of upcoming hours to scan for overnight frost risk.
HOURLY_EXTRA_VARS = ["uv_index", "visibility", "temperature_2m"]

CSV_FIELDS = [
    "captured_at", "api_time", "temp_c", "apparent_c", "dew_point_c",
    "humidity_pct", "pressure_msl_hpa", "surface_pressure_hpa", "wind_kph",
    "wind_dir_deg", "gusts_kph", "precip_mm", "rain_mm", "snowfall_cm",
    "cloud_pct", "uv_index", "visibility_m", "weather_code", "is_day",
    "sunrise", "sunset", "aqi", "pm2_5", "pm10",
]

# Fields returned by fetch_current()/fetch_air_quality() that are useful for
# the dashboard right now but deliberately NOT stored in the CSV log - things
# derived from a forecast (like frost risk) rather than a measurement, so
# logging them wouldn't mean anything looking back at old rows.
_NON_CSV_READING_KEYS = {"frost_risk"}

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
        "daily": "sunrise,sunset",
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

    # Sunrise/sunset for today, e.g. "2026-08-07T05:32" - trimmed to just
    # "05:32" for display. Requested with timezone=Europe/London above, so
    # these already come back as UK wall-clock time, no conversion needed.
    daily = data.get("daily", {})
    sunrise_list = daily.get("sunrise", [])
    sunset_list = daily.get("sunset", [])
    sunrise = sunrise_list[0][-5:] if sunrise_list else None
    sunset = sunset_list[0][-5:] if sunset_list else None

    frost = _frost_risk_from_hourly(hourly_times, hourly.get("temperature_2m", []), api_time)

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
        "sunrise": sunrise,
        "sunset": sunset,
        "frost_risk": frost,
    }


FROST_RISK_THRESHOLD_C = 2.0  # ground frost is a real risk even when the
# air temperature a couple of metres up (what this measures) is still just
# above freezing - 2C is the usual rule-of-thumb gardeners use.


def _frost_risk_from_hourly(hourly_times, hourly_temps, api_time, hours_ahead=24):
    """Scan the next `hours_ahead` hours of forecast temperature for a
    ground-frost risk. Returns None if there isn't enough data to check,
    otherwise a dict with whether there's a risk and when/how cold."""
    if not hourly_times or not hourly_temps or not api_time:
        return None
    try:
        now_dt = datetime.datetime.fromisoformat(api_time)
    except ValueError:
        return None
    cutoff = now_dt + datetime.timedelta(hours=hours_ahead)

    coldest_temp, coldest_time = None, None
    for t, temp in zip(hourly_times, hourly_temps):
        if temp is None:
            continue
        try:
            t_dt = datetime.datetime.fromisoformat(t)
        except ValueError:
            continue
        if now_dt <= t_dt <= cutoff:
            if coldest_temp is None or temp < coldest_temp:
                coldest_temp, coldest_time = temp, t_dt

    if coldest_temp is None:
        return None
    return {
        "at_risk": coldest_temp <= FROST_RISK_THRESHOLD_C,
        "min_temp_c": coldest_temp,
        "min_temp_time": coldest_time.strftime("%a %H:%M") if coldest_time else None,
    }


def fetch_air_quality(lat, lon, timeout=20):
    """Call Open-Meteo's separate free Air Quality API for the same spot.
    Returns a dict with a couple of the most useful figures - the European
    Air Quality Index (0-100+, higher is worse) plus the two pollutant
    readings people most often care about (fine particulates)."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "european_aqi,pm2_5,pm10",
        "timezone": "Europe/London",
    }
    url = "{}?{}".format(AIR_QUALITY_URL, urllib.parse.urlencode(params))
    req = urllib.request.Request(url, headers={"User-Agent": "clearline-weather-app/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError):
        # Air quality is a nice-to-have, not core to the site - if this one
        # call fails, carry on without it rather than failing the whole run.
        return {"aqi": None, "pm2_5": None, "pm10": None}

    cur = data.get("current", {})
    return {
        "aqi": cur.get("european_aqi"),
        "pm2_5": cur.get("pm2_5"),
        "pm10": cur.get("pm10"),
    }


AQI_BANDS = [
    (20, "Good", "#4CAF50"), (40, "Fair", "#8BC34A"), (60, "Moderate", "#FFC107"),
    (80, "Poor", "#FF7043"), (100, "Very Poor", "#E53935"), (None, "Extremely Poor", "#7B1FA2"),
]


def aqi_label(aqi):
    """European AQI (0-100+) -> (label, colour), per the EU's own bands."""
    if aqi is None or aqi == "":
        return None, None
    try:
        aqi = float(aqi)
    except (TypeError, ValueError):
        return None, None
    for threshold, label, colour in AQI_BANDS:
        if threshold is None or aqi <= threshold:
            return label, colour
    return "Extremely Poor", "#7B1FA2"


def heat_index_c(temp_c, humidity_pct):
    """US NWS heat index (Rothfusz regression), converted to Celsius.
    Only really means anything above about 27C with decent humidity - below
    that it just returns the plain temperature unchanged, same as the NWS
    formula's own valid range."""
    if temp_c is None or humidity_pct is None:
        return None
    if temp_c < 26.7:  # ~80F - below this the formula isn't meaningful
        return temp_c
    t_f = temp_c * 9 / 5 + 32
    r = humidity_pct
    hi_f = (
        -42.379 + 2.04901523 * t_f + 10.14333127 * r - 0.22475541 * t_f * r
        - 0.00683783 * t_f * t_f - 0.05481717 * r * r + 0.00122874 * t_f * t_f * r
        + 0.00085282 * t_f * r * r - 0.00000199 * t_f * t_f * r * r
    )
    return round((hi_f - 32) * 5 / 9, 1)


def wind_chill_c(temp_c, wind_kph):
    """JAG/TI wind chill formula (the one the UK Met Office/most of Europe
    uses), which is only valid/meaningful below about 10C with a bit of
    wind - outside that range it just returns the plain temperature."""
    if temp_c is None or wind_kph is None:
        return None
    if temp_c > 10.0 or wind_kph < 4.8:
        return temp_c
    v_pow = wind_kph ** 0.16
    wc = 13.12 + 0.6215 * temp_c - 11.37 * v_pow + 0.3965 * temp_c * v_pow
    return round(wc, 1)


def feels_like_calculated(temp_c, humidity_pct, wind_kph):
    """Our own 'feels like', calculated directly from this station's own
    temperature/humidity/wind rather than taken from Open-Meteo's own
    apparent_temperature figure - heat index when it's warm and humid,
    wind chill when it's cold and breezy, otherwise just the plain
    temperature (neither effect is significant)."""
    try:
        temp_c = float(temp_c) if temp_c not in (None, "") else None
        humidity_pct = float(humidity_pct) if humidity_pct not in (None, "") else None
        wind_kph = float(wind_kph) if wind_kph not in (None, "") else None
    except (TypeError, ValueError):
        return None
    if temp_c is None:
        return None
    if temp_c >= 26.7 and humidity_pct is not None:
        return heat_index_c(temp_c, humidity_pct)
    if temp_c <= 10.0 and wind_kph is not None:
        return wind_chill_c(temp_c, wind_kph)
    return round(temp_c, 1)


_SYNODIC_MONTH_DAYS = 29.530588861
_KNOWN_NEW_MOON = datetime.datetime(2000, 1, 6, 18, 14)  # a well-known reference new moon (UTC)

MOON_PHASES = [
    (0.02, "New Moon", "🌑"), (0.25, "Waxing Crescent", "🌒"),
    (0.27, "First Quarter", "🌓"), (0.48, "Waxing Gibbous", "🌔"),
    (0.52, "Full Moon", "🌕"), (0.73, "Waning Gibbous", "🌖"),
    (0.77, "Last Quarter", "🌗"), (0.98, "Waning Crescent", "🌘"),
    (1.01, "New Moon", "🌑"),
]


def moon_phase(date=None):
    """Which phase the moon is in on a given date - pure calculation, no
    API call needed. Good enough for a casual dashboard reading (accurate
    to well within a day), not precision astronomy."""
    if date is None:
        date = now_local().date()
    if isinstance(date, datetime.datetime):
        date = date.date()
    days_since = (datetime.datetime(date.year, date.month, date.day, 12) - _KNOWN_NEW_MOON).total_seconds() / 86400
    phase_fraction = (days_since % _SYNODIC_MONTH_DAYS) / _SYNODIC_MONTH_DAYS
    for threshold, name, emoji in MOON_PHASES:
        if phase_fraction <= threshold:
            return name, emoji
    return "New Moon", "🌑"  # pragma: no cover - unreachable, thresholds cover 0-1.01


def rainfall_totals(rows):
    """Sum rain_mm over today / the last 7 days / this calendar month /
    this calendar year, from the full log (weather_lib.load_all)."""
    today = now_local().date()
    week_ago = today - datetime.timedelta(days=7)
    totals = {"today": 0.0, "week": 0.0, "month": 0.0, "year": 0.0}
    for row in rows:
        try:
            ts = datetime.datetime.fromisoformat(row["captured_at"])
            rain = float(row.get("rain_mm") or 0)
        except (ValueError, KeyError, TypeError):
            continue
        d = ts.date()
        if d.year == today.year:
            totals["year"] += rain
            if d.month == today.month:
                totals["month"] += rain
        if d >= week_ago:
            totals["week"] += rain
        if d == today:
            totals["today"] += rain
    return {k: round(v, 1) for k, v in totals.items()}


WIND_ROSE_COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                      "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def wind_rose_data(rows):
    """How often the wind's blown from each of 16 compass directions -
    the data behind a wind rose chart. Returns a list of 16 counts in
    WIND_ROSE_COMPASS order, or None if there's no wind direction data."""
    counts = [0] * 16
    total = 0
    for row in rows:
        deg = row.get("wind_dir_deg")
        if deg in (None, ""):
            continue
        try:
            idx = int((float(deg) / 22.5) + 0.5) % 16
        except (TypeError, ValueError):
            continue
        counts[idx] += 1
        total += 1
    if total == 0:
        return None
    return {"counts": counts, "total": total, "compass": WIND_ROSE_COMPASS}


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
        writer.writerow({k: ("" if reading.get(k) is None else reading.get(k)) for k in CSV_FIELDS})
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


def barometric_outlook(rows):
    """A short-range (next few hours, not days) outlook based on classic
    barometer-reading rules: how high the pressure currently is, and how
    fast it's moving. This is a genuinely old, well-established technique
    (the same basic idea printed on the face of a household barometer, and
    used by sailors long before satellite forecasts existed) - rapid falls
    tend to precede rain/wind within hours, a high steady reading tends to
    mean settled weather continuing, and so on.

    Deliberately NOT a multi-day forecast: a single station's own pressure
    reading can't see a system still hundreds of miles away, so this only
    speaks to the next few hours, where local pressure tendency is actually
    a reliable signal."""
    if not rows:
        return None
    _, delta = pressure_trend(rows, hours=3)
    if delta is None:
        return None
    try:
        pressure = float(rows[-1]["pressure_msl_hpa"])
    except (ValueError, KeyError, TypeError):
        return None

    if pressure >= 1030:
        level = "very high"
    elif pressure >= 1022:
        level = "high"
    elif pressure >= 1009:
        level = "normal"
    elif pressure >= 1000:
        level = "low"
    else:
        level = "very low"

    if delta <= -3.0:
        rate = "rapid fall"
    elif delta <= -1.0:
        rate = "falling"
    elif delta < 1.0:
        rate = "steady"
    elif delta < 3.0:
        rate = "rising"
    else:
        rate = "rapid rise"

    if rate == "rapid fall":
        headline = "Unsettled weather likely within a few hours"
        detail = "Pressure is falling quickly - rain and/or stronger winds often follow within 3-6 hours."
    elif rate == "falling":
        if level in ("low", "very low"):
            headline = "Unsettled conditions likely to continue"
            detail = "Pressure is low and still falling - little sign of improvement in the next few hours."
        else:
            headline = "Turning cloudier or showery"
            detail = "Pressure is easing - increasing cloud or a spell of rain is possible over the next few hours."
    elif rate == "rising":
        headline = "Improving conditions likely"
        detail = "Pressure is climbing - conditions should brighten or settle over the next few hours."
    elif rate == "rapid rise":
        headline = "Clearing quickly"
        detail = "Pressure is rising fast, often the sign of a brief clearance - drier, brighter weather likely soon, though rapid rises can also be short-lived."
    else:  # steady
        if level in ("high", "very high"):
            headline = "Fair weather set to continue"
            detail = "Pressure is high and steady - settled conditions likely for the next few hours."
        elif level in ("low", "very low"):
            headline = "Unsettled weather set to continue"
            detail = "Pressure is low and steady - no strong sign of change in the next few hours."
        else:
            headline = "Little change expected"
            detail = "Pressure is steady - conditions should stay much the same over the next few hours."

    return {
        "headline": headline,
        "detail": detail,
        "pressure_level": level,
        "trend_rate": rate,
        "delta_3h": delta,
    }
