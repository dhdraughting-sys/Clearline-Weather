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
            "dew_point_2m": temp - 5.0,
            "apparent_temperature": temp - 1.2,
            "precipitation": 0.0,
            "rain": 0.0,
            "snowfall": 0.0,
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
        self.assertTrue(os.path.exists("history.html"), "should also write the full-history page at repo root")
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


class TestLocationPaths(unittest.TestCase):
    def test_default_flagged_location_gets_index_html(self):
        locations = [
            {"slug": "meriden", "name": "Meriden", "default": True},
            {"slug": "heathrow", "name": "Heathrow"},
        ]
        paths = capture.location_paths(locations)
        self.assertEqual(paths["meriden"], {"dashboard": "index.html", "history": "history.html", "reports": "reports.html"})
        self.assertEqual(paths["heathrow"], {
            "dashboard": "dashboard_heathrow.html", "history": "history_heathrow.html", "reports": "reports_heathrow.html",
        })

    def test_no_default_flag_falls_back_to_first_location(self):
        locations = [{"slug": "a", "name": "A"}, {"slug": "b", "name": "B"}]
        paths = capture.location_paths(locations)
        self.assertEqual(paths["a"]["dashboard"], "index.html")
        self.assertEqual(paths["b"]["dashboard"], "dashboard_b.html")

    def test_single_location_always_gets_index_html(self):
        paths = capture.location_paths([{"slug": "meriden", "name": "Meriden"}])
        self.assertEqual(paths["meriden"], {"dashboard": "index.html", "history": "history.html", "reports": "reports.html"})


class TestMultiLocationCapture(unittest.TestCase):
    def setUp(self):
        self.tmpdir = "test_tmp_multi_location"
        os.makedirs(self.tmpdir, exist_ok=True)
        locations = [
            {"slug": "meriden", "name": "Meriden, CV7 7HT", "lat": 52.427, "lon": -1.660, "default": True},
            {"slug": "heathrow", "name": "London Heathrow", "lat": 51.47, "lon": -0.4543},
            {"slug": "la-rochelle", "name": "La Rochelle, France", "lat": 46.1603, "lon": -1.1511},
        ]
        with open(os.path.join(self.tmpdir, "locations.json"), "w", encoding="utf-8") as f:
            json.dump(locations, f)
        self.cwd = os.getcwd()
        os.chdir(self.tmpdir)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_default_location_writes_index_others_get_own_pages(self):
        with unittest.mock.patch("urllib.request.urlopen", return_value=make_mock_response()):
            capture.main()

        self.assertTrue(os.path.exists("index.html"))
        self.assertTrue(os.path.exists("history.html"))
        self.assertTrue(os.path.exists("reports.html"))
        self.assertTrue(os.path.exists("dashboard_heathrow.html"))
        self.assertTrue(os.path.exists("history_heathrow.html"))
        self.assertTrue(os.path.exists("reports_heathrow.html"))
        self.assertTrue(os.path.exists("dashboard_la-rochelle.html"))
        self.assertTrue(os.path.exists("history_la-rochelle.html"))
        self.assertTrue(os.path.exists("reports_la-rochelle.html"))
        self.assertTrue(os.path.exists("globe.html"))
        self.assertTrue(os.path.exists("clouds.html"))
        self.assertTrue(os.path.exists(os.path.join("data", "meriden.csv")))
        self.assertTrue(os.path.exists(os.path.join("data", "heathrow.csv")))
        self.assertTrue(os.path.exists(os.path.join("data", "la-rochelle.csv")))

    def test_every_page_links_to_every_other_location(self):
        with unittest.mock.patch("urllib.request.urlopen", return_value=make_mock_response()):
            capture.main()

        with open("index.html", encoding="utf-8") as f:
            index_content = f.read()
        self.assertIn("dashboard_heathrow.html", index_content)
        self.assertIn("dashboard_la-rochelle.html", index_content)
        self.assertIn("London Heathrow", index_content)
        self.assertIn("La Rochelle, France", index_content)
        self.assertIn("clouds.html", index_content)

        with open("clouds.html", encoding="utf-8") as f:
            clouds_content = f.read()
        self.assertIn("Meriden, CV7 7HT", clouds_content)
        self.assertIn("London Heathrow", clouds_content)
        self.assertIn("La Rochelle, France", clouds_content)

        with open("dashboard_heathrow.html", encoding="utf-8") as f:
            heathrow_content = f.read()
        self.assertIn('value="index.html"', heathrow_content)
        self.assertIn("Meriden, CV7 7HT", heathrow_content)

        with open("history_heathrow.html", encoding="utf-8") as f:
            heathrow_history_content = f.read()
        self.assertIn('value="history.html"', heathrow_history_content)
        self.assertIn('href="dashboard_heathrow.html"', heathrow_history_content, "history page's back-link should return to its own dashboard")


if __name__ == "__main__":
    unittest.main(verbosity=2)
