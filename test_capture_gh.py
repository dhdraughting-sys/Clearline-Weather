"""
Tests for the GitHub-Actions version of capture.py, mocking the Open-Meteo
HTTP call (this sandbox can't reach the internet). Runs capture.main() in a
temporary working directory so it doesn't touch the real data/ or
index.html, then checks it wrote what a real GitHub Actions run would
commit and push.
"""

import json
import os
import shutil
import sys
import unittest
import unittest.mock

sys.path.insert(0, os.path.dirname(__file__))
import capture  # noqa: E402


def make_mock_response(temp=15.0, pressure=1013.0, api_time="2026-08-06T10:30"):
    payload = {
        "current": {
            "time": api_time,
            "temperature_2m": temp,
            "relative_humidity_2m": 65,
            "apparent_temperature": temp - 1.2,
            "precipitation": 0.0,
            "rain": 0.0,
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
    }
    body = json.dumps(payload).encode("utf-8")

    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return body

    return FakeResp()


class TestCaptureGitHubActions(unittest.TestCase):
    def setUp(self):
        self.tmpdir = "test_tmp_capture_gh"
        os.makedirs(self.tmpdir, exist_ok=True)
        # capture.py reads locations.json and writes data/, index.html
        # relative to the current working directory - exactly how it runs
        # inside GitHub Actions after a checkout.
        shutil.copy("locations.json", os.path.join(self.tmpdir, "locations.json"))
        self.cwd = os.getcwd()
        os.chdir(self.tmpdir)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_writes_index_html_and_csv_at_repo_root(self):
        with unittest.mock.patch("urllib.request.urlopen", return_value=make_mock_response()):
            capture.main()

        self.assertTrue(os.path.exists("index.html"), "should write index.html directly at repo root for GitHub Pages")
        self.assertTrue(os.path.exists(os.path.join("data", "meriden.csv")))

        with open("index.html", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("15.0", content)
        self.assertIn("Meriden", content)

        with open(os.path.join("data", "meriden.csv"), encoding="utf-8") as f:
            rows = f.read().strip().splitlines()
        self.assertEqual(len(rows), 2, "header + 1 data row")

    def test_second_run_same_api_time_does_not_duplicate(self):
        with unittest.mock.patch("urllib.request.urlopen", return_value=make_mock_response(api_time="2026-08-06T10:30")):
            capture.main()
        with unittest.mock.patch("urllib.request.urlopen", return_value=make_mock_response(api_time="2026-08-06T10:30")):
            capture.main()

        with open(os.path.join("data", "meriden.csv"), encoding="utf-8") as f:
            rows = f.read().strip().splitlines()
        self.assertEqual(len(rows), 2, "second run with identical api_time should be a no-op, not a duplicate row")

    def test_new_reading_appends_a_second_row(self):
        with unittest.mock.patch("urllib.request.urlopen", return_value=make_mock_response(api_time="2026-08-06T10:30", temp=15.0)):
            capture.main()
        with unittest.mock.patch("urllib.request.urlopen", return_value=make_mock_response(api_time="2026-08-06T10:45", temp=15.4)):
            capture.main()

        with open(os.path.join("data", "meriden.csv"), encoding="utf-8") as f:
            rows = f.read().strip().splitlines()
        self.assertEqual(len(rows), 3, "header + 2 distinct readings")


if __name__ == "__main__":
    unittest.main(verbosity=2)
