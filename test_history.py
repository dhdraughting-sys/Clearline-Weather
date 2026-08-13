"""
Tests for history.py's daily-summary grouping and page rendering.
"""

import os
import shutil
import unittest

import history


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


class TestDailySummary(unittest.TestCase):
    def test_groups_by_calendar_day(self):
        rows = [
            make_row("2026-08-05T10:00:00", 10.0, 1010.0),
            make_row("2026-08-05T14:00:00", 16.0, 1012.0),
            make_row("2026-08-06T09:00:00", 12.0, 1015.0),
        ]
        summaries = history.daily_summary(rows)
        self.assertEqual(len(summaries), 2)
        self.assertEqual(summaries[0]["date"], "2026-08-05")
        self.assertEqual(summaries[0]["readings"], 2)
        self.assertEqual(summaries[0]["temp_min"], 10.0)
        self.assertEqual(summaries[0]["temp_max"], 16.0)
        self.assertAlmostEqual(summaries[0]["temp_avg"], 13.0)
        self.assertEqual(summaries[1]["date"], "2026-08-06")
        self.assertEqual(summaries[1]["readings"], 1)

    def test_detects_rain(self):
        rows = [
            make_row("2026-08-05T10:00:00", 10.0, 1010.0, rain=0.0),
            make_row("2026-08-05T14:00:00", 10.0, 1010.0, rain=2.4),
        ]
        summaries = history.daily_summary(rows)
        self.assertTrue(summaries[0]["rain_seen"])
        self.assertEqual(summaries[0]["rain_max"], 2.4)

    def test_no_rain_day(self):
        rows = [make_row("2026-08-05T10:00:00", 10.0, 1010.0, rain=0.0)]
        summaries = history.daily_summary(rows)
        self.assertFalse(summaries[0]["rain_seen"])

    def test_ignores_rows_with_bad_timestamps(self):
        rows = [make_row("", 10.0, 1010.0), make_row("2026-08-05T10:00:00", 12.0, 1010.0)]
        summaries = history.daily_summary(rows)
        self.assertEqual(len(summaries), 1)


class TestRender(unittest.TestCase):
    def setUp(self):
        self.tmpdir = "test_tmp_history"
        os.makedirs(self.tmpdir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_renders_empty_history(self):
        out_path = os.path.join(self.tmpdir, "history.html")
        history.render("Meriden, CV7 7HT", [], out_path)
        with open(out_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("No readings logged yet", content)
        self.assertIn("Meriden", content)

    def test_renders_multi_day_table_newest_first(self):
        rows = [
            make_row("2026-08-04T10:00:00", 8.0, 1005.0),
            make_row("2026-08-05T10:00:00", 10.0, 1010.0),
            make_row("2026-08-06T10:00:00", 12.0, 1015.0),
        ]
        out_path = os.path.join(self.tmpdir, "history.html")
        history.render("Meriden, CV7 7HT", rows, out_path)
        with open(out_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("3 days logged", content)
        # Newest day (06 Aug) should appear before the oldest (04 Aug) in the HTML.
        self.assertLess(content.index("06 Aug 2026"), content.index("04 Aug 2026"))
        self.assertIn('href="index.html"', content)

    def test_caps_days_shown(self):
        rows = [make_row("2026-01-{:02d}T10:00:00".format(d), 10.0, 1010.0) for d in range(1, 32)]
        out_path = os.path.join(self.tmpdir, "history.html")
        history.render("Meriden, CV7 7HT", rows, out_path, days_limit=10)
        with open(out_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("most recent 10 of 31 logged days", content)


class TestAllTimeRecords(unittest.TestCase):
    def setUp(self):
        self.tmpdir = "test_tmp_history_records"
        os.makedirs(self.tmpdir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_finds_hottest_coldest_wettest_windiest(self):
        rows = [
            make_row("2026-08-01T12:00:00", 28.0, 1015.0, gusts=20.0, rain=0.0),
            make_row("2026-08-02T04:00:00", -2.0, 1020.0, gusts=55.0, rain=0.0),
            make_row("2026-08-03T09:00:00", 10.0, 1010.0, gusts=10.0, rain=1.0),
            make_row("2026-08-03T15:00:00", 12.0, 1010.0, gusts=10.0, rain=1.5),
        ]
        summaries = history.daily_summary(rows)
        records = history.all_time_records(summaries)
        self.assertEqual(records["hottest"]["date"], "2026-08-01")
        self.assertEqual(records["coldest"]["date"], "2026-08-02")
        self.assertEqual(records["windiest"]["date"], "2026-08-02")
        self.assertEqual(records["wettest"]["date"], "2026-08-03")
        self.assertAlmostEqual(records["wettest"]["rain_total"], 2.5)

    def test_no_data_returns_none(self):
        self.assertIsNone(history.all_time_records([]))

    def test_records_card_renders_in_full_page(self):
        rows = [
            make_row("2026-08-01T12:00:00", 28.0, 1015.0, gusts=20.0, rain=0.0),
            make_row("2026-08-02T04:00:00", -2.0, 1020.0, gusts=55.0, rain=3.0),
        ]
        out_path = os.path.join(self.tmpdir, "history.html")
        history.render("Meriden, CV7 7HT", rows, out_path)
        with open(out_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("All-time records", content)
        self.assertIn("28.0", content)
        self.assertIn("-2.0", content)

    def test_records_card_placeholder_when_empty(self):
        out_path = os.path.join(self.tmpdir, "history.html")
        history.render("Meriden, CV7 7HT", [], out_path)
        with open(out_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Not enough data yet", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
