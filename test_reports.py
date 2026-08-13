"""
Tests for reports.py's server-side half - the embedded day-summary JSON
and page scaffolding. The period-picker/aggregation/charting logic itself
lives in JavaScript inside the generated page (no Python equivalent to
unit test directly), so these tests focus on what Python controls: the
data actually being there, correctly, and the page wiring (back link,
location switcher, print button) being correct.
"""

import json
import os
import shutil
import unittest

import reports


def make_row(captured_at, temp, pressure, wind=10.0, gusts=15.0, rain=0.0, humidity=70):
    return {
        "captured_at": captured_at,
        "temp_c": str(temp),
        "pressure_msl_hpa": str(pressure),
        "wind_kph": str(wind),
        "gusts_kph": str(gusts),
        "rain_mm": str(rain),
        "humidity_pct": str(humidity),
    }


LOCATIONS = [
    {"slug": "meriden", "name": "Meriden, CV7 7HT", "dashboard_path": "index.html", "reports_path": "reports.html"},
    {"slug": "heathrow", "name": "London Heathrow", "dashboard_path": "dashboard_heathrow.html", "reports_path": "reports_heathrow.html"},
]


class TestReportsRender(unittest.TestCase):
    def setUp(self):
        self.tmpdir = "test_tmp_reports"
        os.makedirs(self.tmpdir, exist_ok=True)
        self.out_path = os.path.join(self.tmpdir, "reports.html")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_embeds_valid_json_with_one_entry_per_day(self):
        rows = [
            make_row("2026-08-05T10:00:00", 10.0, 1010.0, rain=1.0),
            make_row("2026-08-05T14:00:00", 16.0, 1012.0, rain=2.0),
            make_row("2026-08-06T09:00:00", 12.0, 1015.0),
        ]
        reports.render("Meriden, CV7 7HT", rows, output_path=self.out_path)
        with open(self.out_path, encoding="utf-8") as f:
            content = f.read()

        start = content.index("var DAYS = ") + len("var DAYS = ")
        end = content.index(";\n", start)
        days = json.loads(content[start:end])
        self.assertEqual(len(days), 2)
        self.assertEqual(days[0]["date"], "2026-08-05")
        self.assertAlmostEqual(days[0]["rain_total"], 3.0)
        self.assertEqual(days[1]["date"], "2026-08-06")

    def test_renders_with_no_data_without_crashing(self):
        reports.render("Meriden, CV7 7HT", [], output_path=self.out_path)
        with open(self.out_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("var DAYS = []", content)

    def test_back_link_and_print_button_present(self):
        reports.render(
            "London Heathrow", [make_row("2026-08-05T10:00:00", 10.0, 1010.0)],
            output_path=self.out_path, dashboard_path="dashboard_heathrow.html",
        )
        with open(self.out_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn('href="dashboard_heathrow.html"', content)
        self.assertIn('id="print-btn"', content)
        self.assertIn("window.print()", content)

    def test_location_switcher_included_when_multiple_locations(self):
        reports.render(
            "Meriden, CV7 7HT", [make_row("2026-08-05T10:00:00", 10.0, 1010.0)],
            output_path=self.out_path, locations=LOCATIONS, current_slug="meriden",
        )
        with open(self.out_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("London Heathrow", content)
        self.assertIn('value="dashboard_heathrow.html"', content)

    def test_period_buttons_present(self):
        reports.render("Meriden, CV7 7HT", [], output_path=self.out_path)
        with open(self.out_path, encoding="utf-8") as f:
            content = f.read()
        for period in ("yesterday", "7", "30", "365", "all", "custom"):
            self.assertIn('data-period="{}"'.format(period), content)

    def test_print_css_hides_controls_and_shows_print_header(self):
        reports.render("Meriden, CV7 7HT", [], output_path=self.out_path)
        with open(self.out_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("@media print", content)
        self.assertIn(".no-print{{display:none !important;}}".replace("{{", "{").replace("}}", "}"), content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
