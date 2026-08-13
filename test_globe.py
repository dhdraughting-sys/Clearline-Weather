"""
Tests for globe.py - mostly checking the generated HTML actually contains
what it's supposed to (every location as a clickable pin/legend entry,
the right "back" link, a sensible caption), since there's no browser here
to actually run the three.js scene.
"""

import os
import shutil
import unittest

import globe


LOCATIONS = [
    {"slug": "meriden", "name": "Meriden, CV7 7HT", "lat": 52.427, "lon": -1.660, "dashboard_path": "index.html"},
    {"slug": "heathrow", "name": "London Heathrow", "lat": 51.47, "lon": -0.4543, "dashboard_path": "dashboard_heathrow.html"},
    {"slug": "la-rochelle", "name": "La Rochelle, France", "lat": 46.1603, "lon": -1.1511, "dashboard_path": "dashboard_la-rochelle.html"},
]


class TestGlobeRender(unittest.TestCase):
    def setUp(self):
        self.tmpdir = "test_tmp_globe"
        os.makedirs(self.tmpdir, exist_ok=True)
        self.out_path = os.path.join(self.tmpdir, "globe.html")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_every_location_appears_as_a_pin_and_legend_entry(self):
        globe.render(LOCATIONS, output_path=self.out_path, texture_meta={"image_date": "2026-08-12"})
        with open(self.out_path, encoding="utf-8") as f:
            content = f.read()
        for loc in LOCATIONS:
            self.assertIn(loc["name"], content)
            self.assertIn(str(loc["lat"]), content)
            self.assertIn(str(loc["lon"]), content)
            self.assertIn(loc["dashboard_path"], content)

    def test_back_link_points_at_default_location(self):
        globe.render(LOCATIONS, output_path=self.out_path)
        with open(self.out_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn('href="index.html"', content)

    def test_caption_shows_imagery_date_when_available(self):
        globe.render(LOCATIONS, output_path=self.out_path, texture_meta={"image_date": "2026-08-12"})
        with open(self.out_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("12 Aug 2026", content)

    def test_caption_has_friendly_placeholder_when_no_imagery_yet(self):
        globe.render(LOCATIONS, output_path=self.out_path, texture_meta=None)
        with open(self.out_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Waiting for the first satellite image", content)

    def test_handles_empty_locations_without_crashing(self):
        globe.render([], output_path=self.out_path)
        with open(self.out_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("No locations configured yet", content)

    def test_location_name_with_apostrophe_does_not_break_js(self):
        tricky = [{"slug": "x", "name": "Mum's House", "lat": 51.0, "lon": -1.0, "dashboard_path": "dashboard_x.html"}]
        globe.render(tricky, output_path=self.out_path)
        with open(self.out_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Mum\\'s House", content, "apostrophe should be escaped inside the JS string literal")

    def test_three_js_is_loaded_as_a_module(self):
        globe.render(LOCATIONS, output_path=self.out_path)
        with open(self.out_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn('type="module"', content)
        self.assertIn("cdnjs.cloudflare.com/ajax/libs/three.js", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
