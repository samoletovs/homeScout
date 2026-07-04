"""Enrichment dataset tests (offline; uses the committed OSM asset)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "functions"))

from enrich import _amenities, nearby  # noqa: E402
from geo import nearest  # noqa: E402


class AmenitiesDatasetTests(unittest.TestCase):
    def test_dataset_loads(self):
        self.assertGreater(len(_amenities()), 50)

    def test_nearby_filters_by_kind(self):
        schools = nearby("school")
        self.assertTrue(schools)
        self.assertTrue(all(p["kind"] == "school" for p in schools))
        self.assertTrue(all("lat" in p and "lon" in p for p in schools))

    def test_nearest_school_in_riga_is_close(self):
        # A central-Rīga point should have a school within a few km.
        best = nearest(56.9496, 24.1052, nearby("school"))
        self.assertIsNotNone(best)
        self.assertLess(best[1], 3.0)


if __name__ == "__main__":
    unittest.main()
