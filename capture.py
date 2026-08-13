#!/usr/bin/env python3
"""
Runs automatically every 15 minutes via GitHub Actions - see
.github/workflows/capture-weather.yml. No PC required; this keeps working
even when your computer is off, asleep, or nowhere near you.

Each run:
  1. Fetches current conditions for every location in locations.json from
     Open-Meteo (no API key needed).
  2. Appends a row to data/<slug>.csv - the permanent log. This now lives
     inside this GitHub repo rather than only on your PC (see README.md
     for what that means).
  3. Regenerates index.html from the log - GitHub Pages serves this
     directly at your github.io URL, so the dashboard on your phone/PC
     updates automatically, no extra publish step needed.

The GitHub Actions workflow commits and pushes whatever this script
changes on disk - this script itself never touches git.
"""

import sys

from weather_lib import (
    load_locations, fetch_current, fetch_air_quality, append_reading, load_recent, load_all,
)
import dashboard
import history
import globe
from earth_texture import update_earth_texture_if_stale

HISTORY_HOURS = 48


def location_paths(locations):
    """Work out each location's dashboard/history filenames. Whichever one
    is flagged "default" in locations.json (or the first one, if none is)
    becomes the site's landing page at index.html/history.html - what
    GitHub Pages serves at the repo's root URL and what your home-screen
    icon opens. Everyone else gets their own dashboard_<slug>.html /
    history_<slug>.html, reachable via the location switcher dropdown on
    every page."""
    default_slug = next((loc["slug"] for loc in locations if loc.get("default")), locations[0]["slug"])
    paths = {}
    for loc in locations:
        slug = loc["slug"]
        if slug == default_slug:
            paths[slug] = {"dashboard": "index.html", "history": "history.html"}
        else:
            paths[slug] = {"dashboard": "dashboard_{}.html".format(slug), "history": "history_{}.html".format(slug)}
    return paths


def main():
    locations = load_locations()
    any_errors = False
    paths = location_paths(locations)
    # Passed to every page so it can render a "jump to another location"
    # dropdown - a flat list is all dashboard.py/history.py need, no
    # need for them to know about locations.json's shape.
    nav_locations = [
        {
            "slug": loc["slug"],
            "name": loc["name"],
            "lat": loc["lat"],
            "lon": loc["lon"],
            "dashboard_path": paths[loc["slug"]]["dashboard"],
            "history_path": paths[loc["slug"]]["history"],
        }
        for loc in locations
    ]

    for loc in locations:
        slug = loc["slug"]
        csv_path = "data/{}.csv".format(slug)
        output_path = paths[slug]["dashboard"]
        history_path = paths[slug]["history"]

        print("[{}] fetching current conditions...".format(slug))
        try:
            reading = fetch_current(loc["lat"], loc["lon"])
        except Exception as e:
            print("[{}] ERROR: {}".format(slug, e), file=sys.stderr)
            any_errors = True
            continue

        # Air quality is a separate API call and a nice-to-have - if it
        # fails for any reason, fetch_air_quality() itself already returns
        # all-None rather than raising, so this never blocks a capture run.
        try:
            aqi_reading = fetch_air_quality(loc["lat"], loc["lon"])
        except Exception as e:
            print("[{}] air quality fetch failed (non-fatal): {}".format(slug, e), file=sys.stderr)
            aqi_reading = {"aqi": None, "pm2_5": None, "pm10": None}
        reading.update(aqi_reading)

        added = append_reading(csv_path, reading)
        print("[{}] {} (temp {}C, pressure {}hPa)".format(
            slug, "logged new reading" if added else "no new data since last run",
            reading.get("temp_c"), reading.get("pressure_msl_hpa"),
        ))

        rows = load_recent(csv_path, hours=HISTORY_HOURS)
        all_rows = load_all(csv_path)
        dashboard.render(
            loc["name"], reading, rows, output_path, lat=loc["lat"], lon=loc["lon"], all_rows=all_rows,
            locations=nav_locations, current_slug=slug, history_path=history_path,
        )
        print("[{}] dashboard updated -> {}".format(slug, output_path))

        history.render(
            loc["name"], all_rows, history_path,
            locations=nav_locations, current_slug=slug, dashboard_path=output_path,
        )
        print("[{}] history page updated -> {}".format(slug, history_path))

    # One shared globe page, not per-location - updated every run, but
    # the satellite image behind it only actually refreshes once a day
    # (see earth_texture.py).
    try:
        texture_meta = update_earth_texture_if_stale()
    except Exception as e:
        print("[globe] earth texture update failed (non-fatal): {}".format(e), file=sys.stderr)
        from earth_texture import read_texture_meta
        texture_meta = read_texture_meta()
    globe.render(nav_locations, texture_meta=texture_meta)
    print("[globe] globe page updated -> globe.html (imagery date: {})".format(texture_meta.get("image_date")))

    if any_errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
