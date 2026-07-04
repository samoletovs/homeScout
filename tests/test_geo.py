"""Geo helper tests (offline, stdlib)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "functions"))

from geo import (  # noqa: E402
    haversine_km,
    nearest,
    parse_ors_matrix_minutes,
    parse_overpass_amenities,
    proximity_score,
)


class HaversineTests(unittest.TestCase):
    def test_known_distance_riga_to_jurmala(self):
        # Rīga centre → Jūrmala is roughly 20 km.
        km = haversine_km(56.9496, 24.1052, 56.9680, 23.7794)
        self.assertTrue(18 < km < 24, km)

    def test_zero_distance(self):
        self.assertEqual(haversine_km(56.9, 24.1, 56.9, 24.1), 0.0)


class OverpassTests(unittest.TestCase):
    def test_parses_nodes_and_way_centers_skips_coordless(self):
        data = {"elements": [
            {"type": "node", "lat": 56.95, "lon": 24.11, "tags": {"name": "Skola", "amenity": "school"}},
            {"type": "way", "center": {"lat": 56.96, "lon": 24.12}, "tags": {"amenity": "kindergarten"}},
            {"type": "node", "tags": {"name": "no-coords"}},
        ]}
        points = parse_overpass_amenities(data)
        self.assertEqual(len(points), 2)
        self.assertEqual(points[0]["name"], "Skola")


class NearestTests(unittest.TestCase):
    def test_picks_closest(self):
        points = [{"lat": 57.0, "lon": 24.2}, {"lat": 56.951, "lon": 24.106}]
        best = nearest(56.95, 24.105, points)
        self.assertIsNotNone(best)
        self.assertEqual(best[0], points[1])
        self.assertLess(best[1], 0.5)

    def test_empty_returns_none(self):
        self.assertIsNone(nearest(56.9, 24.1, []))


class OrsTests(unittest.TestCase):
    def test_parses_minutes(self):
        self.assertEqual(parse_ors_matrix_minutes({"durations": [[1200]]}), 20.0)

    def test_missing_or_empty_returns_none(self):
        self.assertIsNone(parse_ors_matrix_minutes({"durations": [[]]}))
        self.assertIsNone(parse_ors_matrix_minutes({}))


class ProximityTests(unittest.TestCase):
    def test_bounds_and_midpoint(self):
        self.assertEqual(proximity_score(0.2), 1.0)
        self.assertEqual(proximity_score(2.0), 0.0)
        self.assertEqual(proximity_score(None), 0.5)
        self.assertTrue(0 < proximity_score(1.0) < 1)


if __name__ == "__main__":
    unittest.main()
