"""
Fetches a real satellite photo of the whole Earth (true-colour, so real
clouds are visible exactly as they were that day) from NASA's GIBS
service, for the rotatable 3D globe on globe.html.

This is NASA's free public Global Imagery Browse Services - no API key,
no signup. It's a standard OGC WMS endpoint, the same kind of service
GIS software talks to. Docs: https://nasa-gibs.github.io/gibs-api-docs/

Deliberately NOT fetched every 15 minutes - the underlying imagery only
updates once a day, so update_earth_texture_if_stale() only hits the
network the first time it's called on a new UK calendar day, and is a
no-op (no network call at all) every other run.
"""

import datetime
import json
import os
import urllib.error
import urllib.parse
import urllib.request

GIBS_WMS_URL = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"

# VIIRS is the newer, higher-cadence satellite; MODIS Terra is the
# longer-running, more heavily-used fallback for days where VIIRS imagery
# isn't published yet (satellite processing can lag a few hours behind
# real time, especially earlier in the UK day).
TRUE_COLOUR_LAYERS = [
    "VIIRS_SNPP_CorrectedReflectance_TrueColor",
    "MODIS_Terra_CorrectedReflectance_TrueColor",
]

TEXTURE_WIDTH = 1600
TEXTURE_HEIGHT = 800

# A real whole-Earth JPEG at this size is comfortably six figures of
# bytes - anything smaller back from the API is almost certainly an
# error/placeholder tile rather than a real image, so treat it as a miss.
MIN_VALID_BYTES = 20_000


def _fetch_snapshot(layer, date_str, width=TEXTURE_WIDTH, height=TEXTURE_HEIGHT, timeout=30):
    """One GIBS WMS GetMap request for a whole-Earth image on a given
    date. Returns the JPEG bytes, or None if the request failed or came
    back too small to be a real image."""
    params = {
        "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap",
        "LAYERS": layer, "CRS": "EPSG:4326", "BBOX": "-180,-90,180,90",
        "WIDTH": width, "HEIGHT": height, "FORMAT": "image/jpeg", "TIME": date_str,
    }
    url = "{}?{}".format(GIBS_WMS_URL, urllib.parse.urlencode(params))
    req = urllib.request.Request(url, headers={"User-Agent": "clearline-weather-app/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        return None
    if len(data) < MIN_VALID_BYTES:
        return None
    return data


def fetch_earth_texture(dates_to_try, layers=None, width=TEXTURE_WIDTH, height=TEXTURE_HEIGHT, timeout=30):
    """Try each date (newest first) against each layer (most-preferred
    first) until one comes back with real image data. Returns
    (jpeg_bytes, date_used, layer_used), or (None, None, None) if nothing
    worked - which is the normal case in the first hour or two of a new
    UK day, before that day's satellite imagery has been published yet."""
    for date_str in dates_to_try:
        for layer in (layers or TRUE_COLOUR_LAYERS):
            data = _fetch_snapshot(layer, date_str, width=width, height=height, timeout=timeout)
            if data:
                return data, date_str, layer
    return None, None, None


def _read_marker(date_marker_path):
    if not os.path.exists(date_marker_path):
        return None
    try:
        with open(date_marker_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return None


def read_texture_meta(date_marker_path="data/earth_texture_meta.json"):
    """What globe.py needs to know to caption the globe - the date of the
    imagery actually showing (which may be a day or two old if today's
    hasn't been published), independent of whether a fetch happened on
    this particular run."""
    return _read_marker(date_marker_path) or {"checked_date": None, "image_date": None, "layer": None}


def update_earth_texture_if_stale(texture_path="data/earth_texture.jpg",
                                   date_marker_path="data/earth_texture_meta.json",
                                   today=None):
    """Refreshes the saved globe texture at most once per UK calendar
    day. Returns the same metadata dict read_texture_meta() would, so the
    caller always has something to pass to globe.py regardless of
    whether this particular run actually touched the network."""
    if today is None:
        from weather_lib import now_local
        today = now_local().date()

    marker = _read_marker(date_marker_path)
    if marker and marker.get("checked_date") == today.isoformat():
        return marker  # already checked today - skip the network call entirely

    dates_to_try = [(today - datetime.timedelta(days=d)).isoformat() for d in range(0, 4)]
    data, used_date, used_layer = fetch_earth_texture(dates_to_try)

    if not data:
        # Couldn't get anything new (e.g. too early in the day for any
        # imagery to be published yet) - record that today's been
        # checked, so this doesn't hit the network again for another 15
        # minutes, but leave any existing texture/metadata untouched.
        result = dict(marker) if marker else {"checked_date": None, "image_date": None, "layer": None}
        result["checked_date"] = today.isoformat()
        with open(date_marker_path, "w", encoding="utf-8") as f:
            json.dump(result, f)
        return result

    os.makedirs(os.path.dirname(texture_path) or ".", exist_ok=True)
    with open(texture_path, "wb") as f:
        f.write(data)

    result = {"checked_date": today.isoformat(), "image_date": used_date, "layer": used_layer}
    with open(date_marker_path, "w", encoding="utf-8") as f:
        json.dump(result, f)
    return result
