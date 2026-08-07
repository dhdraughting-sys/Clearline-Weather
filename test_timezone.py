"""
Tests for the BST/GMT fix. The bug: GitHub Actions runners default to UTC,
so plain datetime.datetime.now() silently logged everything an hour behind
during British Summer Time (roughly late March - late October). now_local()
must always report real UK wall-clock time regardless of what timezone the
machine running the script happens to be in.
"""

import datetime
import unittest
import unittest.mock

import weather_lib


class TestNowLocal(unittest.TestCase):
    def test_matches_uk_wall_clock_during_bst(self):
        # A moment that is unambiguously BST (UTC+1): 6 Aug, noon UTC.
        fixed_utc = datetime.datetime(2026, 8, 6, 12, 0, 0, tzinfo=datetime.timezone.utc)
        with unittest.mock.patch("weather_lib.datetime.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_utc.astimezone(weather_lib.UK_TZ)
            mock_dt.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            result = weather_lib.now_local()
        self.assertEqual(result, datetime.datetime(2026, 8, 6, 13, 0, 0), "BST is UTC+1")
        self.assertIsNone(result.tzinfo, "must be naive so it compares cleanly with stored timestamps")

    def test_matches_uk_wall_clock_during_gmt(self):
        # A moment that is unambiguously GMT (UTC+0): 6 Jan, noon UTC.
        fixed_utc = datetime.datetime(2026, 1, 6, 12, 0, 0, tzinfo=datetime.timezone.utc)
        with unittest.mock.patch("weather_lib.datetime.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_utc.astimezone(weather_lib.UK_TZ)
            mock_dt.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            result = weather_lib.now_local()
        self.assertEqual(result, datetime.datetime(2026, 1, 6, 12, 0, 0), "GMT is UTC+0")

    def test_naive_utc_now_would_have_been_wrong_in_summer(self):
        """Documents exactly the bug that was reported: proves the old
        datetime.datetime.now() call (implicitly UTC on a GitHub Actions
        runner) really is an hour behind now_local() in August."""
        fixed_utc = datetime.datetime(2026, 8, 6, 12, 0, 0, tzinfo=datetime.timezone.utc)
        with unittest.mock.patch("weather_lib.datetime.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_utc.astimezone(weather_lib.UK_TZ)
            mock_dt.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            correct = weather_lib.now_local()
        naive_utc_bug = fixed_utc.replace(tzinfo=None)  # what the old buggy code produced
        self.assertEqual((correct - naive_utc_bug).total_seconds(), 3600,
                          "the old bug under-reported the time by exactly 1 hour in BST")


class TestFetchCurrentUsesLocalTime(unittest.TestCase):
    def test_captured_at_uses_now_local_not_raw_utc(self):
        payload = {
            "current": {
                "time": "2026-08-06T14:30", "temperature_2m": 18.0,
                "relative_humidity_2m": 60, "dew_point_2m": 10.0,
                "apparent_temperature": 17.0, "precipitation": 0.0, "rain": 0.0,
                "snowfall": 0.0, "weather_code": 1, "pressure_msl": 1015.0,
                "surface_pressure": 1000.0, "wind_speed_10m": 10.0,
                "wind_direction_10m": 180, "wind_gusts_10m": 15.0,
                "cloud_cover": 20, "is_day": 1,
            },
            "hourly": {"time": ["2026-08-06T14:00"], "uv_index": [4.0], "visibility": [20000]},
        }
        import json
        body = json.dumps(payload).encode("utf-8")

        class FakeResp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return body

        fixed_bst = datetime.datetime(2026, 8, 6, 15, 30, 0)  # what now_local() should return
        with unittest.mock.patch("urllib.request.urlopen", return_value=FakeResp()), \
             unittest.mock.patch("weather_lib.now_local", return_value=fixed_bst):
            reading = weather_lib.fetch_current(52.427, -1.660)
        self.assertEqual(reading["captured_at"], "2026-08-06T15:30:00")


if __name__ == "__main__":
    unittest.main(verbosity=2)
