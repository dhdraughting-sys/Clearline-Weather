"""
Tests for weather_lib.py, focused on the two riskiest pieces: parsing the
new dew point / snowfall fields from Open-Meteo, and the automatic CSV
header migration (which rewrites the live log file in place - a bug here
could corrupt real logged history, so it's covered carefully).
"""

import csv
import json
import os
import shutil
import sys
import unittest
import unittest.mock

sys.path.insert(0, os.path.dirname(__file__))
import weather_lib  # noqa: E402


def make_mock_current_response(temp=15.0, pressure=1013.0, dew_point=10.0,
                                snowfall=0.0, api_time="2026-08-05T14:30",
                                sunrise="2026-08-05T05:32", sunset="2026-08-05T20:47"):
    payload = {
        "current": {
            "time": api_time,
            "temperature_2m": temp,
            "relative_humidity_2m": 65,
            "dew_point_2m": dew_point,
            "apparent_temperature": temp - 1.2,
            "precipitation": 0.0,
            "rain": 0.0,
            "snowfall": snowfall,
            "weather_code": 2,
            "pressure_msl": pressure,
            "surface_pressure": pressure - 15,
            "wind_speed_10m": 12.5,
            "wind_direction_10m": 225,
            "wind_gusts_10m": 21.0,
            "cloud_cover": 40,
            "is_day": 1,
        },
        "hourly": {
            "time": [api_time[:13] + ":00"],
            "uv_index": [3.2],
            "visibility": [24000],
        },
        "daily": {
            "sunrise": [sunrise],
            "sunset": [sunset],
        },
    }
    body = json.dumps(payload).encode("utf-8")

    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return body

    return FakeResp()


class TestFetchCurrentNewFields(unittest.TestCase):
    def test_parses_dew_point_and_snowfall(self):
        with unittest.mock.patch("urllib.request.urlopen",
                                  return_value=make_mock_current_response(dew_point=8.4, snowfall=1.5)):
            reading = weather_lib.fetch_current(52.427, -1.660)
        self.assertEqual(reading["dew_point_c"], 8.4)
        self.assertEqual(reading["snowfall_cm"], 1.5)

    def test_dew_point_and_snowfall_are_csv_fields(self):
        self.assertIn("dew_point_c", weather_lib.CSV_FIELDS)
        self.assertIn("snowfall_cm", weather_lib.CSV_FIELDS)


class TestFetchCurrentSunriseSunset(unittest.TestCase):
    def test_parses_sunrise_and_sunset_as_hhmm(self):
        with unittest.mock.patch(
            "urllib.request.urlopen",
            return_value=make_mock_current_response(sunrise="2026-08-05T05:32", sunset="2026-08-05T20:47"),
        ):
            reading = weather_lib.fetch_current(52.427, -1.660)
        self.assertEqual(reading["sunrise"], "05:32")
        self.assertEqual(reading["sunset"], "20:47")

    def test_missing_daily_block_gives_none_not_a_crash(self):
        with unittest.mock.patch("urllib.request.urlopen") as mock_urlopen:
            resp = make_mock_current_response()
            # Simulate an older/degraded API response with no "daily" block.
            import json as _json
            payload = _json.loads(resp.read())
            del payload["daily"]
            body = _json.dumps(payload).encode("utf-8")

            class FakeResp:
                def __enter__(self): return self
                def __exit__(self, *a): return False
                def read(self): return body

            mock_urlopen.return_value = FakeResp()
            reading = weather_lib.fetch_current(52.427, -1.660)
        self.assertIsNone(reading["sunrise"])
        self.assertIsNone(reading["sunset"])

    def test_sunrise_and_sunset_are_csv_fields(self):
        self.assertIn("sunrise", weather_lib.CSV_FIELDS)
        self.assertIn("sunset", weather_lib.CSV_FIELDS)


class TestHeaderMigration(unittest.TestCase):
    def setUp(self):
        self.tmpdir = "test_tmp_migration"
        os.makedirs(self.tmpdir, exist_ok=True)
        self.csv_path = os.path.join(self.tmpdir, "meriden.csv")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_old_format_csv(self):
        # Mimics a real log file written before dew_point_c/snowfall_cm
        # existed - exactly what's sitting in the live GitHub repo right now.
        old_fields = [
            "captured_at", "api_time", "temp_c", "apparent_c", "humidity_pct",
            "pressure_msl_hpa", "surface_pressure_hpa", "wind_kph", "wind_dir_deg",
            "gusts_kph", "precip_mm", "rain_mm", "cloud_pct", "uv_index",
            "visibility_m", "weather_code", "is_day",
        ]
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=old_fields)
            writer.writeheader()
            writer.writerow({
                "captured_at": "2026-08-06T01:17:59", "api_time": "2026-08-06T01:15",
                "temp_c": "15.1", "apparent_c": "13.2", "humidity_pct": "67",
                "pressure_msl_hpa": "1019.0", "surface_pressure_hpa": "1007.0",
                "wind_kph": "11.5", "wind_dir_deg": "275", "gusts_kph": "20.9",
                "precip_mm": "0.0", "rain_mm": "0.0", "cloud_pct": "34",
                "uv_index": "0.0", "visibility_m": "29860.0", "weather_code": "1",
                "is_day": "0",
            })
            writer.writerow({
                "captured_at": "2026-08-06T01:31:47", "api_time": "2026-08-06T01:30",
                "temp_c": "14.3", "apparent_c": "12.5", "humidity_pct": "71",
                "pressure_msl_hpa": "1019.0", "surface_pressure_hpa": "1007.0",
                "wind_kph": "10.8", "wind_dir_deg": "266", "gusts_kph": "20.2",
                "precip_mm": "0.0", "rain_mm": "0.0", "cloud_pct": "1",
                "uv_index": "0.0", "visibility_m": "29700.0", "weather_code": "0",
                "is_day": "0",
            })

    def test_old_rows_survive_migration_with_blank_new_columns(self):
        self._write_old_format_csv()
        weather_lib._migrate_header_if_needed(self.csv_path)

        with open(self.csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            self.assertEqual(reader.fieldnames, weather_lib.CSV_FIELDS)
            rows = list(reader)

        self.assertEqual(len(rows), 2, "no rows should be lost during migration")
        self.assertEqual(rows[0]["temp_c"], "15.1", "old data must be preserved exactly")
        self.assertEqual(rows[0]["dew_point_c"], "", "new column should be blank for old rows")
        self.assertEqual(rows[0]["snowfall_cm"], "")
        self.assertEqual(rows[1]["temp_c"], "14.3")

    def test_already_current_header_is_left_untouched(self):
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=weather_lib.CSV_FIELDS)
            writer.writeheader()
            writer.writerow({k: "" for k in weather_lib.CSV_FIELDS})
        with open(self.csv_path, encoding="utf-8") as f:
            before = f.read()
        weather_lib._migrate_header_if_needed(self.csv_path)
        with open(self.csv_path, encoding="utf-8") as f:
            after = f.read()
        self.assertEqual(before, after, "migration should be a no-op when the header already matches")

    def test_append_reading_triggers_migration_then_appends_new_row(self):
        self._write_old_format_csv()
        new_reading = {k: None for k in weather_lib.CSV_FIELDS}
        new_reading.update({
            "captured_at": "2026-08-06T02:00:00", "api_time": "2026-08-06T02:00",
            "temp_c": 13.9, "dew_point_c": 9.1, "snowfall_cm": 0.0,
            "pressure_msl_hpa": 1019.0,
        })
        added = weather_lib.append_reading(self.csv_path, new_reading)
        self.assertTrue(added)

        rows = weather_lib.load_all(self.csv_path)
        self.assertEqual(len(rows), 3, "2 migrated old rows + 1 new row")
        self.assertEqual(rows[0]["dew_point_c"], "", "migrated old row stays blank")
        self.assertEqual(rows[-1]["dew_point_c"], "9.1", "new row carries the new field")


if __name__ == "__main__":
    unittest.main(verbosity=2)
