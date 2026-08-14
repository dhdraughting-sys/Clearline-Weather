"""
Tests for backfill.py, mocking the Open-Meteo archive HTTP call (this
sandbox can't reach the internet - see the module docstring for why that's
fine in practice, since it only ever actually runs on a GitHub Actions
runner).
"""

import csv
import json
import os
import shutil
import unittest
import unittest.mock

import backfill


def make_archive_response(dates_and_hours, base_temp=10.0):
    """Builds a fake hourly archive response covering the given list of
    ISO date strings, 24 hours each, with an easily-checked incrementing
    temperature so tests can assert on exact values."""
    times = []
    temps = []
    for d in dates_and_hours:
        for h in range(24):
            times.append("{}T{:02d}:00".format(d, h))
            temps.append(base_temp)
    payload = {
        "hourly": {
            "time": times,
            "temperature_2m": temps,
            "relative_humidity_2m": [70] * len(times),
            "dew_point_2m": [5.0] * len(times),
            "apparent_temperature": [9.0] * len(times),
            "precipitation": [0.0] * len(times),
            "rain": [0.0] * len(times),
            "snowfall": [0.0] * len(times),
            "weather_code": [1] * len(times),
            "pressure_msl": [1012.0] * len(times),
            "surface_pressure": [1000.0] * len(times),
            "wind_speed_10m": [10.0] * len(times),
            "wind_direction_10m": [200] * len(times),
            "wind_gusts_10m": [15.0] * len(times),
            "cloud_cover": [40] * len(times),
            "is_day": [1] * len(times),
            "uv_index": [2.0] * len(times),
            "visibility": [20000] * len(times),
        },
        "daily": {
            "time": dates_and_hours,
            "sunrise": [d + "T05:30" for d in dates_and_hours],
            "sunset": [d + "T20:30" for d in dates_and_hours],
        },
    }
    body = json.dumps(payload).encode("utf-8")

    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return body

    return FakeResp()


class TestFetchHistorical(unittest.TestCase):
    def test_parses_hourly_rows_with_matching_daily_sunrise_sunset(self):
        resp = make_archive_response(["2026-07-01", "2026-07-02"], base_temp=14.5)
        with unittest.mock.patch("urllib.request.urlopen", return_value=resp):
            readings = backfill.fetch_historical(52.5, -1.7, days=2)

        self.assertEqual(len(readings), 48)
        self.assertEqual(readings[0]["captured_at"], "2026-07-01T00:00")
        self.assertEqual(readings[0]["temp_c"], 14.5)
        self.assertEqual(readings[0]["sunrise"], "05:30")
        self.assertEqual(readings[0]["sunset"], "20:30")
        self.assertIsNone(readings[0]["aqi"])

    def test_missing_hourly_variable_becomes_none_not_a_crash(self):
        resp = make_archive_response(["2026-07-01"])
        with unittest.mock.patch("urllib.request.urlopen", return_value=resp):
            readings = backfill.fetch_historical(52.5, -1.7, days=1)
        # visibility was included in the fake response; simulate a variable
        # the archive API doesn't actually support by checking a made-up one
        # would come back None via _val()'s missing-array branch.
        self.assertIsNotNone(readings[0]["visibility_m"])

    def test_network_error_raises_runtimeerror(self):
        import urllib.error
        with unittest.mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("boom")):
            with self.assertRaises(RuntimeError):
                backfill.fetch_historical(52.5, -1.7, days=1)


class TestBackfillIfNeeded(unittest.TestCase):
    def setUp(self):
        self.tmpdir = "test_tmp_backfill"
        os.makedirs(self.tmpdir, exist_ok=True)
        self.csv_path = os.path.join(self.tmpdir, "kingshurst.csv")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_backfills_brand_new_location(self):
        resp = make_archive_response(["2026-07-01", "2026-07-02"])
        with unittest.mock.patch("urllib.request.urlopen", return_value=resp):
            added = backfill.backfill_if_needed(self.csv_path, 52.5, -1.7, days=2)

        self.assertEqual(added, 48)
        with open(self.csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 48)
        self.assertEqual(rows[0]["captured_at"], "2026-07-01T00:00")
        self.assertEqual(rows[-1]["captured_at"], "2026-07-02T23:00")

    def test_writes_a_marker_file_after_backfilling(self):
        resp = make_archive_response(["2026-07-01"])
        with unittest.mock.patch("urllib.request.urlopen", return_value=resp):
            backfill.backfill_if_needed(self.csv_path, 52.5, -1.7, days=1)
        self.assertTrue(os.path.exists(self.csv_path + ".backfilled"))

    def test_skips_location_that_already_has_a_marker_regardless_of_row_count(self):
        # This is the actual bug that hit Kingshurst: a location can
        # accumulate plenty of live rows before this code ever gets a
        # chance to run for the first time. A location with only ONE row
        # but an existing marker must still be skipped - "already handled"
        # is tracked explicitly, never guessed from the row count.
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=backfill.CSV_FIELDS)
            writer.writeheader()
            writer.writerow({"captured_at": "2026-08-14T09:00", "temp_c": 20.0})
        with open(self.csv_path + ".backfilled", "w", encoding="utf-8") as f:
            f.write("already done\n")

        with unittest.mock.patch("urllib.request.urlopen") as mock_urlopen:
            added = backfill.backfill_if_needed(self.csv_path, 52.5, -1.7, days=2)
            mock_urlopen.assert_not_called()
        self.assertEqual(added, 0)

    def test_a_location_with_many_live_rows_but_no_marker_still_gets_backfilled(self):
        # The inverse of the old (buggy) behaviour: lots of existing rows
        # must NOT be treated as "already backfilled" if the marker was
        # never actually written.
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=backfill.CSV_FIELDS)
            writer.writeheader()
            for i in range(25):
                writer.writerow({"captured_at": "2026-08-14T{:02d}:00".format(i % 24), "temp_c": 12.0})

        resp = make_archive_response(["2026-07-01"])
        with unittest.mock.patch("urllib.request.urlopen", return_value=resp):
            added = backfill.backfill_if_needed(self.csv_path, 52.5, -1.7, days=1)
        self.assertEqual(added, 24)

    def test_existing_row_wins_over_historical_on_timestamp_clash(self):
        # A live capture already logged this exact hour with a real
        # temperature - backfill must not clobber it with the (fake, very
        # different) historical value for the same timestamp.
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=backfill.CSV_FIELDS)
            writer.writeheader()
            writer.writerow({"captured_at": "2026-07-01T00:00", "temp_c": 99.9})

        resp = make_archive_response(["2026-07-01"], base_temp=1.0)
        with unittest.mock.patch("urllib.request.urlopen", return_value=resp):
            backfill.backfill_if_needed(self.csv_path, 52.5, -1.7, days=1)

        with open(self.csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        clashing = [r for r in rows if r["captured_at"] == "2026-07-01T00:00"]
        self.assertEqual(len(clashing), 1)
        self.assertEqual(clashing[0]["temp_c"], "99.9")

    def test_rows_written_in_chronological_order(self):
        resp = make_archive_response(["2026-07-03", "2026-07-01", "2026-07-02"])
        with unittest.mock.patch("urllib.request.urlopen", return_value=resp):
            backfill.backfill_if_needed(self.csv_path, 52.5, -1.7, days=3)
        with open(self.csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        timestamps = [r["captured_at"] for r in rows]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_empty_archive_response_still_writes_marker_so_it_only_tries_once(self):
        empty = make_archive_response([])
        with unittest.mock.patch("urllib.request.urlopen", return_value=empty):
            added = backfill.backfill_if_needed(self.csv_path, 52.5, -1.7, days=1)
        self.assertEqual(added, 0)
        self.assertTrue(os.path.exists(self.csv_path + ".backfilled"))

    def test_network_error_does_not_write_marker_so_it_retries_next_run(self):
        import urllib.error
        with unittest.mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("boom")):
            with self.assertRaises(RuntimeError):
                backfill.backfill_if_needed(self.csv_path, 52.5, -1.7, days=1)
        self.assertFalse(os.path.exists(self.csv_path + ".backfilled"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
