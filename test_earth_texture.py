"""
Tests for earth_texture.py - the daily satellite-image fetch behind the
rotatable globe. The riskiest part isn't the network call itself (that's
just a GET), it's the once-a-day caching logic: get this wrong and it
either hammers NASA's API every 15 minutes or never refreshes at all.
"""

import datetime
import json
import os
import shutil
import sys
import unittest
import unittest.mock

sys.path.insert(0, os.path.dirname(__file__))
import earth_texture  # noqa: E402


def make_fake_urlopen(good_dates=None, good_layers=None, body_size=50_000):
    """Simulates GIBS: returns a big enough "image" only for dates/layers
    marked as having real data, otherwise a tiny (too-small-to-count)
    response - the same shape a real "no imagery for this date yet"
    response takes."""
    good_dates = set(good_dates or [])
    good_layers = set(good_layers or earth_texture.TRUE_COLOUR_LAYERS)

    def fake_urlopen(req, timeout=30):
        url = req.full_url if hasattr(req, "full_url") else req
        is_good = any("TIME={}".format(d) in url for d in good_dates) and \
            any("LAYERS={}".format(layer) in url for layer in good_layers)
        body = b"x" * (body_size if is_good else 10)

        class FakeResp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return body

        return FakeResp()

    return fake_urlopen


class TestFetchSnapshot(unittest.TestCase):
    def test_returns_bytes_when_response_is_big_enough(self):
        with unittest.mock.patch("urllib.request.urlopen", make_fake_urlopen(good_dates=["2026-08-12"])):
            data = earth_texture._fetch_snapshot("VIIRS_SNPP_CorrectedReflectance_TrueColor", "2026-08-12")
        self.assertIsNotNone(data)
        self.assertGreaterEqual(len(data), earth_texture.MIN_VALID_BYTES)

    def test_returns_none_when_response_too_small(self):
        with unittest.mock.patch("urllib.request.urlopen", make_fake_urlopen(good_dates=[])):
            data = earth_texture._fetch_snapshot("VIIRS_SNPP_CorrectedReflectance_TrueColor", "2026-08-12")
        self.assertIsNone(data)

    def test_returns_none_on_network_error(self):
        import urllib.error
        with unittest.mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("no net")):
            data = earth_texture._fetch_snapshot("VIIRS_SNPP_CorrectedReflectance_TrueColor", "2026-08-12")
        self.assertIsNone(data)


class TestFetchEarthTexture(unittest.TestCase):
    def test_tries_dates_newest_first_and_stops_at_first_success(self):
        with unittest.mock.patch("urllib.request.urlopen", make_fake_urlopen(good_dates=["2026-08-10"])):
            data, used_date, used_layer = earth_texture.fetch_earth_texture(
                ["2026-08-12", "2026-08-11", "2026-08-10", "2026-08-09"],
            )
        self.assertIsNotNone(data)
        self.assertEqual(used_date, "2026-08-10")

    def test_falls_back_to_second_layer_when_first_has_no_data(self):
        with unittest.mock.patch(
            "urllib.request.urlopen",
            make_fake_urlopen(good_dates=["2026-08-12"], good_layers=["MODIS_Terra_CorrectedReflectance_TrueColor"]),
        ):
            data, used_date, used_layer = earth_texture.fetch_earth_texture(["2026-08-12"])
        self.assertIsNotNone(data)
        self.assertEqual(used_layer, "MODIS_Terra_CorrectedReflectance_TrueColor")

    def test_returns_none_triple_when_nothing_available(self):
        with unittest.mock.patch("urllib.request.urlopen", make_fake_urlopen(good_dates=[])):
            data, used_date, used_layer = earth_texture.fetch_earth_texture(["2026-08-12", "2026-08-11"])
        self.assertIsNone(data)
        self.assertIsNone(used_date)
        self.assertIsNone(used_layer)


class TestUpdateEarthTextureIfStale(unittest.TestCase):
    def setUp(self):
        self.tmpdir = "test_tmp_earth_texture"
        os.makedirs(self.tmpdir, exist_ok=True)
        self.texture_path = os.path.join(self.tmpdir, "earth_texture.jpg")
        self.marker_path = os.path.join(self.tmpdir, "earth_texture_meta.json")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_first_run_fetches_and_writes_texture(self):
        today = datetime.date(2026, 8, 12)
        with unittest.mock.patch("urllib.request.urlopen", make_fake_urlopen(good_dates=["2026-08-12"])):
            result = earth_texture.update_earth_texture_if_stale(self.texture_path, self.marker_path, today=today)
        self.assertTrue(os.path.exists(self.texture_path))
        self.assertEqual(result["image_date"], "2026-08-12")
        self.assertEqual(result["checked_date"], "2026-08-12")

    def test_second_run_same_day_does_not_hit_network(self):
        today = datetime.date(2026, 8, 12)
        with unittest.mock.patch("urllib.request.urlopen", make_fake_urlopen(good_dates=["2026-08-12"])):
            earth_texture.update_earth_texture_if_stale(self.texture_path, self.marker_path, today=today)

        with unittest.mock.patch("urllib.request.urlopen") as mock_urlopen:
            result = earth_texture.update_earth_texture_if_stale(self.texture_path, self.marker_path, today=today)
            mock_urlopen.assert_not_called()
        self.assertEqual(result["image_date"], "2026-08-12")

    def test_next_day_refetches(self):
        day1 = datetime.date(2026, 8, 12)
        day2 = datetime.date(2026, 8, 13)
        with unittest.mock.patch("urllib.request.urlopen", make_fake_urlopen(good_dates=["2026-08-12"])):
            earth_texture.update_earth_texture_if_stale(self.texture_path, self.marker_path, today=day1)
        with unittest.mock.patch("urllib.request.urlopen", make_fake_urlopen(good_dates=["2026-08-13"])):
            result = earth_texture.update_earth_texture_if_stale(self.texture_path, self.marker_path, today=day2)
        self.assertEqual(result["image_date"], "2026-08-13")

    def test_falls_back_to_earlier_date_when_todays_imagery_not_published_yet(self):
        today = datetime.date(2026, 8, 12)
        # Only yesterday's imagery is "available" - simulates running early
        # in the morning before today's satellite pass has been processed.
        with unittest.mock.patch("urllib.request.urlopen", make_fake_urlopen(good_dates=["2026-08-11"])):
            result = earth_texture.update_earth_texture_if_stale(self.texture_path, self.marker_path, today=today)
        self.assertEqual(result["image_date"], "2026-08-11")
        self.assertEqual(result["checked_date"], "2026-08-12", "should still mark today as checked")

    def test_no_data_available_leaves_existing_texture_untouched(self):
        today = datetime.date(2026, 8, 12)
        with unittest.mock.patch("urllib.request.urlopen", make_fake_urlopen(good_dates=["2026-08-12"])):
            earth_texture.update_earth_texture_if_stale(self.texture_path, self.marker_path, today=today)
        with open(self.texture_path, "rb") as f:
            original_bytes = f.read()

        tomorrow = datetime.date(2026, 8, 13)
        with unittest.mock.patch("urllib.request.urlopen", make_fake_urlopen(good_dates=[])):
            result = earth_texture.update_earth_texture_if_stale(self.texture_path, self.marker_path, today=tomorrow)

        with open(self.texture_path, "rb") as f:
            self.assertEqual(f.read(), original_bytes, "texture file should be untouched when no new imagery is found")
        self.assertEqual(result["image_date"], "2026-08-12", "metadata should still reflect the last successful fetch")
        self.assertEqual(result["checked_date"], "2026-08-13")

    def test_read_texture_meta_returns_defaults_when_no_marker_yet(self):
        meta = earth_texture.read_texture_meta(os.path.join(self.tmpdir, "does-not-exist.json"))
        self.assertEqual(meta, {"checked_date": None, "image_date": None, "layer": None})

    def test_read_texture_meta_reads_back_what_was_written(self):
        today = datetime.date(2026, 8, 12)
        with unittest.mock.patch("urllib.request.urlopen", make_fake_urlopen(good_dates=["2026-08-12"])):
            earth_texture.update_earth_texture_if_stale(self.texture_path, self.marker_path, today=today)
        meta = earth_texture.read_texture_meta(self.marker_path)
        self.assertEqual(meta["image_date"], "2026-08-12")


if __name__ == "__main__":
    unittest.main(verbosity=2)
