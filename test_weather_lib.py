"""
Tests for weather_lib.py, focused on the two riskiest pieces: parsing the
new dew point / snowfall fields from Open-Meteo, and the automatic CSV
header migration (which rewrites the live log file in place - a bug here
could corrupt real logged history, so it's covered carefully).
"""

import csv
import datetime
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


class TestBarometricOutlook(unittest.TestCase):
    def _rows(self, pressures):
        """pressures: list of (hours_ago, pressure_hpa), newest last."""
        base = "2026-08-08T15:00:00"
        base_dt = __import__("datetime").datetime.fromisoformat(base)
        rows = []
        for hours_ago, p in pressures:
            t = base_dt - __import__("datetime").timedelta(hours=hours_ago)
            rows.append({"captured_at": t.isoformat(timespec="seconds"), "pressure_msl_hpa": str(p)})
        return rows

    def test_no_rows_returns_none(self):
        self.assertIsNone(weather_lib.barometric_outlook([]))

    def test_single_row_returns_none(self):
        rows = self._rows([(0, 1015.0)])
        self.assertIsNone(weather_lib.barometric_outlook(rows))

    def test_rapid_fall_flags_unsettled_soon(self):
        rows = self._rows([(3, 1018.0), (0, 1013.5)])  # -4.5 hPa / 3h
        outlook = weather_lib.barometric_outlook(rows)
        self.assertEqual(outlook["trend_rate"], "rapid fall")
        self.assertIn("Unsettled", outlook["headline"])

    def test_steady_high_pressure_is_fair(self):
        rows = self._rows([(3, 1032.0), (0, 1032.2)])  # steady, very high
        outlook = weather_lib.barometric_outlook(rows)
        self.assertEqual(outlook["trend_rate"], "steady")
        self.assertEqual(outlook["pressure_level"], "very high")
        self.assertIn("Fair", outlook["headline"])

    def test_rapid_rise_flags_clearing(self):
        rows = self._rows([(3, 1005.0), (0, 1009.5)])  # +4.5 hPa / 3h
        outlook = weather_lib.barometric_outlook(rows)
        self.assertEqual(outlook["trend_rate"], "rapid rise")
        self.assertIn("Clearing", outlook["headline"])

    def test_steady_low_pressure_stays_unsettled(self):
        rows = self._rows([(3, 998.0), (0, 998.3)])  # steady, very low
        outlook = weather_lib.barometric_outlook(rows)
        self.assertEqual(outlook["pressure_level"], "very low")
        self.assertIn("Unsettled", outlook["headline"])


class TestFrostRisk(unittest.TestCase):
    def test_no_frost_risk_when_warm(self):
        times = ["2026-01-05T14:00", "2026-01-05T15:00", "2026-01-05T16:00"]
        temps = [10.0, 11.0, 9.5]
        risk = weather_lib._frost_risk_from_hourly(times, temps, "2026-01-05T14:00")
        self.assertFalse(risk["at_risk"])

    def test_frost_risk_when_cold_ahead(self):
        times = ["2026-01-05T14:00", "2026-01-05T20:00", "2026-01-06T04:00"]
        temps = [8.0, 3.0, 0.5]
        risk = weather_lib._frost_risk_from_hourly(times, temps, "2026-01-05T14:00")
        self.assertTrue(risk["at_risk"])
        self.assertEqual(risk["min_temp_c"], 0.5)

    def test_no_data_returns_none(self):
        self.assertIsNone(weather_lib._frost_risk_from_hourly([], [], "2026-01-05T14:00"))
        self.assertIsNone(weather_lib._frost_risk_from_hourly(["x"], [1.0], None))


class TestAirQuality(unittest.TestCase):
    def _mock_response(self, aqi=35, pm2_5=8.0, pm10=15.0):
        payload = {"current": {"european_aqi": aqi, "pm2_5": pm2_5, "pm10": pm10}}
        body = json.dumps(payload).encode("utf-8")

        class FakeResp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return body

        return FakeResp()

    def test_parses_air_quality_fields(self):
        with unittest.mock.patch("urllib.request.urlopen", return_value=self._mock_response()):
            result = weather_lib.fetch_air_quality(52.427, -1.660)
        self.assertEqual(result["aqi"], 35)
        self.assertEqual(result["pm2_5"], 8.0)
        self.assertEqual(result["pm10"], 15.0)

    def test_network_failure_returns_all_none_not_a_crash(self):
        with unittest.mock.patch("urllib.request.urlopen", side_effect=weather_lib.urllib.error.URLError("no net")):
            result = weather_lib.fetch_air_quality(52.427, -1.660)
        self.assertEqual(result, {"aqi": None, "pm2_5": None, "pm10": None})


class TestAqiLabel(unittest.TestCase):
    def test_good_band(self):
        label, colour = weather_lib.aqi_label(10)
        self.assertEqual(label, "Good")

    def test_extremely_poor_band(self):
        label, colour = weather_lib.aqi_label(150)
        self.assertEqual(label, "Extremely Poor")

    def test_none_returns_none(self):
        self.assertEqual(weather_lib.aqi_label(None), (None, None))
        self.assertEqual(weather_lib.aqi_label(""), (None, None))


class TestFeelsLike(unittest.TestCase):
    def test_heat_index_applies_when_hot_and_humid(self):
        hi = weather_lib.heat_index_c(32.0, 70)
        self.assertGreater(hi, 32.0, "heat index should push the 'feels like' above actual temp in humid heat")

    def test_heat_index_below_threshold_returns_plain_temp(self):
        self.assertEqual(weather_lib.heat_index_c(20.0, 70), 20.0)

    def test_wind_chill_applies_when_cold_and_windy(self):
        wc = weather_lib.wind_chill_c(2.0, 30.0)
        self.assertLess(wc, 2.0, "wind chill should push 'feels like' below actual temp in cold wind")

    def test_wind_chill_ignored_when_light_wind(self):
        self.assertEqual(weather_lib.wind_chill_c(2.0, 2.0), 2.0)

    def test_feels_like_calculated_picks_heat_index(self):
        result = weather_lib.feels_like_calculated(30.0, 80, 5.0)
        self.assertEqual(result, weather_lib.heat_index_c(30.0, 80))

    def test_feels_like_calculated_picks_wind_chill(self):
        result = weather_lib.feels_like_calculated(3.0, 60, 25.0)
        self.assertEqual(result, weather_lib.wind_chill_c(3.0, 25.0))

    def test_feels_like_calculated_mild_returns_plain_temp(self):
        self.assertEqual(weather_lib.feels_like_calculated(15.0, 60, 10.0), 15.0)

    def test_feels_like_calculated_handles_missing_temp(self):
        self.assertIsNone(weather_lib.feels_like_calculated(None, 60, 10.0))


class TestMoonPhase(unittest.TestCase):
    def test_known_new_moon_date(self):
        name, emoji = weather_lib.moon_phase(datetime.date(2000, 1, 6))
        self.assertEqual(name, "New Moon")

    def test_returns_a_valid_phase_name(self):
        valid_names = {name for _, name, _ in weather_lib.MOON_PHASES}
        name, emoji = weather_lib.moon_phase(datetime.date(2026, 8, 13))
        self.assertIn(name, valid_names)


class TestRainfallTotals(unittest.TestCase):
    def test_sums_by_period(self):
        today = weather_lib.now_local().date()
        rows = [
            {"captured_at": datetime.datetime.combine(today, datetime.time(9, 0)).isoformat(), "rain_mm": "1.5"},
            {"captured_at": datetime.datetime.combine(today, datetime.time(12, 0)).isoformat(), "rain_mm": "2.0"},
            {"captured_at": (datetime.datetime.combine(today, datetime.time(9, 0)) - datetime.timedelta(days=3)).isoformat(), "rain_mm": "4.0"},
        ]
        totals = weather_lib.rainfall_totals(rows)
        self.assertEqual(totals["today"], 3.5)
        self.assertEqual(totals["week"], 7.5)

    def test_empty_rows_returns_zeros(self):
        totals = weather_lib.rainfall_totals([])
        self.assertEqual(totals, {"today": 0.0, "week": 0.0, "month": 0.0, "year": 0.0})


class TestWindRoseData(unittest.TestCase):
    def test_buckets_into_compass_sectors(self):
        rows = [
            {"wind_dir_deg": "0"}, {"wind_dir_deg": "0"}, {"wind_dir_deg": "90"},
        ]
        data = weather_lib.wind_rose_data(rows)
        self.assertEqual(data["total"], 3)
        self.assertEqual(data["counts"][0], 2, "two N readings")
        self.assertEqual(data["counts"][4], 1, "one E reading")

    def test_no_data_returns_none(self):
        self.assertIsNone(weather_lib.wind_rose_data([]))
        self.assertIsNone(weather_lib.wind_rose_data([{"wind_dir_deg": ""}]))


class TestAppendReadingWithFrostRisk(unittest.TestCase):
    """Regression test for the bug where fetch_current()'s frost_risk key
    (not a CSV column) crashed csv.DictWriter's fieldnames check."""

    def setUp(self):
        self.tmpdir = "test_tmp_frost_append"
        os.makedirs(self.tmpdir, exist_ok=True)
        self.csv_path = os.path.join(self.tmpdir, "meriden.csv")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_reading_with_frost_risk_key_does_not_crash(self):
        reading = {k: None for k in weather_lib.CSV_FIELDS}
        reading.update({
            "captured_at": "2026-01-05T14:00:00", "api_time": "2026-01-05T14:00",
            "temp_c": 1.0, "frost_risk": {"at_risk": True, "min_temp_c": -1.0, "min_temp_time": "Mon 04:00"},
        })
        added = weather_lib.append_reading(self.csv_path, reading)
        self.assertTrue(added)
        rows = weather_lib.load_all(self.csv_path)
        self.assertEqual(len(rows), 1)
        self.assertNotIn("frost_risk", rows[0], "non-CSV key should not leak into the CSV header/row")


if __name__ == "__main__":
    unittest.main(verbosity=2)
