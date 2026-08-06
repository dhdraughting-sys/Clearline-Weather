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

from weather_lib import load_locations, fetch_current, append_reading, load_recent
import dashboard

HISTORY_HOURS = 48


def main():
    locations = load_locations()
    any_errors = False

    for loc in locations:
        slug = loc["slug"]
        csv_path = "data/{}.csv".format(slug)
        # Single location -> index.html directly, which is what GitHub
        # Pages serves at the repo's root URL. If you ever add a second
        # location and want it on its own page, tell me and I'll extend
        # this rather than you guessing at the layout.
        output_path = "index.html" if len(locations) == 1 else "dashboard_{}.html".format(slug)

        print("[{}] fetching current conditions...".format(slug))
        try:
            reading = fetch_current(loc["lat"], loc["lon"])
        except Exception as e:
            print("[{}] ERROR: {}".format(slug, e), file=sys.stderr)
            any_errors = True
            continue

        added = append_reading(csv_path, reading)
        print("[{}] {} (temp {}C, pressure {}hPa)".format(
            slug, "logged new reading" if added else "no new data since last run",
            reading.get("temp_c"), reading.get("pressure_msl_hpa"),
        ))

        rows = load_recent(csv_path, hours=HISTORY_HOURS)
        dashboard.render(loc["name"], reading, rows, output_path)
        print("[{}] dashboard updated -> {}".format(slug, output_path))

    if any_errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
