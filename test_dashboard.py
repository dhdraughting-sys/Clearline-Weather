"""
Tests for dashboard.py's small standalone helpers - focused on the
location switcher (new for the multi-location rollout), since a broken
link there would send you to the wrong page silently.
"""

import datetime
import unittest

import dashboard


LOCATIONS = [
    {"slug": "meriden", "name": "Meriden, CV7 7HT", "dashboard_path": "index.html", "history_path": "history.html"},
    {"slug": "heathrow", "name": "London Heathrow", "dashboard_path": "dashboard_heathrow.html", "history_path": "history_heathrow.html"},
    {"slug": "la-rochelle", "name": "La Rochelle, France", "dashboard_path": "dashboard_la-rochelle.html", "history_path": "history_la-rochelle.html"},
]


class TestLocationSwitcherHtml(unittest.TestCase):
    def test_empty_with_zero_or_one_locations(self):
        self.assertEqual(dashboard.location_switcher_html(None, "meriden"), "")
        self.assertEqual(dashboard.location_switcher_html([], "meriden"), "")
        self.assertEqual(dashboard.location_switcher_html(LOCATIONS[:1], "meriden"), "")

    def test_lists_every_location_by_name(self):
        html = dashboard.location_switcher_html(LOCATIONS, "meriden")
        for loc in LOCATIONS:
            self.assertIn(loc["name"], html)

    def test_dashboard_view_links_to_dashboard_paths(self):
        html = dashboard.location_switcher_html(LOCATIONS, "meriden", view="dashboard")
        self.assertIn('value="dashboard_heathrow.html"', html)
        self.assertIn('value="dashboard_la-rochelle.html"', html)
        self.assertNotIn('value="history_heathrow.html"', html)

    def test_history_view_links_to_history_paths(self):
        html = dashboard.location_switcher_html(LOCATIONS, "meriden", view="history")
        self.assertIn('value="history_heathrow.html"', html)
        self.assertIn('value="history_la-rochelle.html"', html)
        self.assertNotIn('value="dashboard_heathrow.html"', html)

    def test_current_location_is_marked_selected(self):
        html = dashboard.location_switcher_html(LOCATIONS, "heathrow", view="dashboard")
        self.assertIn('value="dashboard_heathrow.html" selected', html)
        self.assertNotIn('value="index.html" selected', html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
