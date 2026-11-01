"""Enrichment dataset tests (offline; uses the committed OSM asset)."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "functions"))

import enrich  # noqa: E402
from enrich import _amenities, nearby  # noqa: E402
from models import Listing  # noqa: E402
from geo import nearest  # noqa: E402


class FakeResponse:
    def __init__(self, data=None, text=""):
        self.data = data or {}
        self.text = text

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class FakeClient:
    def __init__(self):
        self.urls = []

    async def get(self, url, **kwargs):
        self.urls.append(url)
        if url == enrich.SCHOOL_RESULTS_DATASET_URL:
            return FakeResponse({
                "success": True,
                "result": {"resources": [{
                    "format": "CSV",
                    "url": "https://data.gov.lv/dati/school-results.csv",
                    "last_modified": "2025-01-01",
                }]},
            })
        if url.endswith("school-results.csv"):
            return FakeResponse(text="Skolas nosaukums;Vidējais rezultāts (%)\nRīgas skola;80,0\nRīgas skola;90,0\n")
        if "/route/v1/driving/" in url:
            return FakeResponse({"routes": [{"duration": 750}]})
        raise AssertionError(f"Unexpected URL: {url}")


class FakeOrsClient:
    async def post(self, url, **kwargs):
        return FakeResponse({"durations": [[600]]})

    async def get(self, url, **kwargs):
        raise AssertionError("OSRM should not be used when ORS succeeds")


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


class AdditionalSourceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        enrich._school_ratings_cache = None

    def tearDown(self):
        enrich._school_ratings_cache = None

    async def test_enrich_all_uses_osrm_and_school_results(self):
        client = FakeClient()
        listing = Listing(
            id="1", source="test", url="https://example.test/1",
            lat=56.95, lon=24.11,
        )
        school_points = [{"name": "Rīgas skola", "lat": 56.95, "lon": 24.11}]
        with patch("enrich.ORS_API_KEY", ""), patch(
            "enrich.nearby",
            side_effect=lambda kind: school_points if kind == "school" else [],
        ):
            await enrich.enrich_all([listing], client, object())

        self.assertEqual(listing.commute_min, 12.5)
        self.assertEqual(listing.features["school_rating"], 85.0)
        self.assertEqual(listing.features["schools"], 1.0)
        self.assertTrue(any("/route/v1/driving/" in url for url in client.urls))
        self.assertEqual(client.urls.count(enrich.SCHOOL_RESULTS_DATASET_URL), 1)

    async def test_ors_remains_primary_commute_source(self):
        with patch("enrich.ORS_API_KEY", "test-key"):
            minutes = await enrich.commute_minutes(56.95, 24.11, FakeOrsClient())
        self.assertEqual(minutes, 10.0)

    def test_school_rating_parser_handles_latvian_headers_and_decimal_commas(self):
        ratings = enrich._parse_school_ratings(
            "Skolas kods;Izglītības iestādes nosaukums;Vidējais rezultāts (%)\n"
            "123;Rīgas skola;82,5\n"
        )
        self.assertEqual(ratings["rigasskola"], 82.5)


if __name__ == "__main__":
    unittest.main()
