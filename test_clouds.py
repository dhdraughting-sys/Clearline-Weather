"""
Tests for clouds.py - the cloud learning portal. Covers the
classify_conditions() heuristic (pure function, easy to pin down exact
cases), the daily spotlight rotation, and that the generated page actually
contains what it should (every cloud type, live guesses, the checklist
wiring, localStorage saving).
"""

import datetime
import os
import shutil
import unittest

import clouds


LOCATIONS = [
    {
        "slug": "meriden", "name": "Meriden, CV7 7HT", "lat": 52.427, "lon": -1.660,
        "dashboard_path": "index.html", "weather_code": 3, "cloud_pct": 97,
    },
    {
        "slug": "heathrow", "name": "London Heathrow", "lat": 51.47, "lon": -0.4543,
        "dashboard_path": "dashboard_heathrow.html", "weather_code": 1, "cloud_pct": 5,
    },
]


class TestClassifyConditions(unittest.TestCase):
    def test_clear_sky_returns_no_cloud_type(self):
        cloud_id, note = clouds.classify_conditions(0, 0)
        self.assertIsNone(cloud_id)
        self.assertIn("Clear", note)

    def test_thunderstorm_code_returns_cumulonimbus(self):
        cloud_id, note = clouds.classify_conditions(95, 80)
        self.assertEqual(cloud_id, "cumulonimbus")

    def test_heavy_rain_returns_nimbostratus(self):
        cloud_id, note = clouds.classify_conditions(65, 90)
        self.assertEqual(cloud_id, "nimbostratus")

    def test_light_drizzle_low_cover_returns_stratus(self):
        cloud_id, note = clouds.classify_conditions(51, 40)
        self.assertEqual(cloud_id, "stratus")

    def test_fog_code_returns_stratus(self):
        cloud_id, note = clouds.classify_conditions(45, 100)
        self.assertEqual(cloud_id, "stratus")

    def test_overcast_lumpy_returns_stratocumulus(self):
        cloud_id, note = clouds.classify_conditions(3, 80)
        self.assertEqual(cloud_id, "stratocumulus")

    def test_overcast_solid_returns_stratus(self):
        cloud_id, note = clouds.classify_conditions(3, 98)
        self.assertEqual(cloud_id, "stratus")

    def test_partly_cloudy_high_cover_returns_altocumulus(self):
        cloud_id, note = clouds.classify_conditions(2, 60)
        self.assertEqual(cloud_id, "altocumulus")

    def test_partly_cloudy_low_cover_returns_cumulus(self):
        cloud_id, note = clouds.classify_conditions(2, 20)
        self.assertEqual(cloud_id, "cumulus")

    def test_mainly_clear_with_some_cover_returns_cirrus(self):
        cloud_id, note = clouds.classify_conditions(1, 20)
        self.assertEqual(cloud_id, "cirrus")

    def test_mainly_clear_almost_no_cover_returns_none(self):
        cloud_id, note = clouds.classify_conditions(1, 2)
        self.assertIsNone(cloud_id)

    def test_none_weather_code_handled_gracefully(self):
        cloud_id, note = clouds.classify_conditions(None, None)
        self.assertIsNone(cloud_id)
        self.assertIn("No live reading", note)

    def test_every_returned_id_is_a_real_cloud_type(self):
        for code in (0, 1, 2, 3, 45, 48, 51, 53, 55, 61, 63, 65, 71, 73, 75, 80, 81, 82, 85, 86, 95, 96, 99):
            for pct in (0, 30, 60, 90, 100):
                cloud_id, note = clouds.classify_conditions(code, pct)
                if cloud_id is not None:
                    self.assertIn(cloud_id, clouds._BY_ID, "code={} pct={} returned unknown id {}".format(code, pct, cloud_id))


class TestSpotlight(unittest.TestCase):
    def test_same_day_gives_same_spotlight(self):
        d = datetime.datetime(2026, 8, 13, tzinfo=datetime.timezone.utc)
        a = clouds._spotlight(d)
        b = clouds._spotlight(d)
        self.assertEqual(a["id"], b["id"])

    def test_different_days_can_give_different_spotlight(self):
        seen = set()
        for day in range(1, 366, 17):
            d = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc) + datetime.timedelta(days=day - 1)
            seen.add(clouds._spotlight(d)["id"])
        self.assertGreater(len(seen), 1, "spotlight should rotate across the year, not stay fixed")


class TestCloudsRender(unittest.TestCase):
    def setUp(self):
        self.tmpdir = "test_tmp_clouds"
        os.makedirs(self.tmpdir, exist_ok=True)
        self.out_path = os.path.join(self.tmpdir, "clouds.html")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_every_cloud_type_appears_with_its_own_anchor(self):
        clouds.render(LOCATIONS, output_path=self.out_path)
        with open(self.out_path, encoding="utf-8") as f:
            content = f.read()
        for c in clouds.CLOUD_TYPES:
            self.assertIn(c["name"], content)
            self.assertIn('id="cloud-{}"'.format(c["id"]), content)

    def test_live_strip_shows_each_location_and_a_guess(self):
        clouds.render(LOCATIONS, output_path=self.out_path)
        with open(self.out_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Meriden, CV7 7HT", content)
        self.assertIn("London Heathrow", content)
        # Meriden: code 3, 97% cover -> stratus; Heathrow: code 1, 5% -> no guess
        self.assertIn("#cloud-stratus", content)

    def test_back_link_points_at_default_location(self):
        clouds.render(LOCATIONS, output_path=self.out_path)
        with open(self.out_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn('href="index.html"', content)

    def test_checklist_js_and_localstorage_wiring_present(self):
        clouds.render(LOCATIONS, output_path=self.out_path)
        with open(self.out_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("localStorage", content)
        self.assertIn("learn-toggle", content)
        self.assertIn("progress-bar", content)

    def test_handles_empty_locations_without_crashing(self):
        clouds.render([], output_path=self.out_path)
        with open(self.out_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("No live readings yet", content)
        self.assertIn('href="index.html"', content)

    def test_handles_missing_live_readings_gracefully(self):
        no_reading = [{"slug": "x", "name": "Nowhere", "dashboard_path": "dashboard_x.html"}]
        clouds.render(no_reading, output_path=self.out_path)
        with open(self.out_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Nowhere", content)
        self.assertIn("No live reading yet", content)

    def test_spotlight_section_present(self):
        clouds.render(LOCATIONS, output_path=self.out_path, today=datetime.datetime(2026, 8, 13, tzinfo=datetime.timezone.utc))
        with open(self.out_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Cloud of the day", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
