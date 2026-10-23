"""Enrichment dataset tests (offline; uses the committed OSM asset)."""
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "functions"))

import enrich  # noqa: E402
from enrich import _amenities, nearby  # noqa: E402
from geo import nearest  # noqa: E402
from models import Listing  # noqa: E402


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


class AmenitiesCacheTests(unittest.TestCase):
    def test_missing_dataset_is_cached_as_empty(self):
        with patch.object(enrich, "_amenities_cache", None), patch.object(
            enrich, "_AMENITIES_PATH", "/missing/amenities.json"
        ):
            self.assertEqual(enrich._amenities(), [])
            with patch("builtins.open", side_effect=AssertionError("dataset should be cached")):
                self.assertEqual(enrich._amenities(), [])


class GeocodeTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_cached_coordinates_without_request(self):
        store = MagicMock()
        store.get_geo.return_value = (56.9, 24.1)
        client = AsyncMock()
        self.assertEqual(await enrich.geocode("Mārupe", client, store), (56.9, 24.1))
        client.get.assert_not_awaited()

    async def test_success_stores_coordinates_and_waits_for_rate_limit(self):
        response = MagicMock()
        response.json.return_value = [{"lat": "56.9", "lon": "24.1"}]
        client = AsyncMock()
        client.get.return_value = response
        store = MagicMock()
        store.get_geo.return_value = None

        with patch("enrich.asyncio.sleep", new_callable=AsyncMock) as sleep:
            result = await enrich.geocode("Mārupe", client, store)

        self.assertEqual(result, (56.9, 24.1))
        store.put_geo.assert_called_once_with("Mārupe", 56.9, 24.1)
        sleep.assert_awaited_once_with(1.0)
        self.assertEqual(client.get.await_args.args[0], enrich.NOMINATIM_URL)

    async def test_empty_search_result_returns_none(self):
        response = MagicMock()
        response.json.return_value = []
        client = AsyncMock()
        client.get.return_value = response
        store = MagicMock()
        store.get_geo.return_value = None

        with patch("enrich.asyncio.sleep", new_callable=AsyncMock):
            self.assertIsNone(await enrich.geocode("unknown", client, store))
        store.put_geo.assert_not_called()

    async def test_request_failure_returns_none(self):
        client = AsyncMock()
        client.get.side_effect = RuntimeError("network unavailable")
        store = MagicMock()
        store.get_geo.return_value = None
        self.assertIsNone(await enrich.geocode("Mārupe", client, store))
        store.put_geo.assert_not_called()


class CommuteTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_api_key_skips_request(self):
        client = AsyncMock()
        with patch.object(enrich, "ORS_API_KEY", ""):
            self.assertIsNone(await enrich.commute_minutes(56.9, 24.1, client))
        client.post.assert_not_awaited()

    async def test_parses_response_and_sends_lon_lat_order(self):
        response = MagicMock()
        response.json.return_value = {"durations": [[1200]]}
        client = AsyncMock()
        client.post.return_value = response
        destination = (56.95, 24.11)

        with patch.object(enrich, "ORS_API_KEY", "test-key"), patch.object(
            enrich, "COMMUTE_DEST", destination
        ):
            minutes = await enrich.commute_minutes(56.9, 24.1, client)

        self.assertEqual(minutes, 20.0)
        request = client.post.await_args.kwargs
        self.assertEqual(request["json"]["locations"], [[24.1, 56.9], [24.11, 56.95]])
        self.assertEqual(request["headers"]["Authorization"], "test-key")

    async def test_request_failure_returns_none(self):
        client = AsyncMock()
        client.post.side_effect = RuntimeError("service unavailable")
        with patch.object(enrich, "ORS_API_KEY", "test-key"):
            self.assertIsNone(await enrich.commute_minutes(56.9, 24.1, client))


class EnrichListingTests(unittest.IsolatedAsyncioTestCase):
    async def test_enriches_existing_coordinates_and_populates_features(self):
        listing = Listing(
            id="1", source="city24", url="u", lat=56.9, lon=24.1, price=200000, area_m2=100
        )
        schools = [{"lat": 56.901, "lon": 24.1, "kind": "school"}]
        kindergartens = [{"lat": 56.902, "lon": 24.1, "kind": "kindergarten"}]
        client = AsyncMock()
        with patch("enrich.nearby", side_effect=lambda kind: {
            "school": schools, "kindergarten": kindergartens
        }[kind]), patch(
            "enrich.commute_minutes", new_callable=AsyncMock, return_value=22.5
        ) as commute:
            result = await enrich.enrich_listing(listing, client, MagicMock())

        self.assertIs(result, listing)
        self.assertAlmostEqual(listing.nearest_school_km, nearest(56.9, 24.1, schools)[1], places=2)
        self.assertEqual(listing.nearest_kindergarten_km, round(nearest(56.9, 24.1, kindergartens)[1], 2))
        self.assertEqual(listing.commute_min, 22.5)
        self.assertEqual(listing.features["commute"], 22.5)
        self.assertEqual(listing.features["price_per_m2"], 2000)
        self.assertEqual(listing.features["size"], 100)
        commute.assert_awaited_once_with(56.9, 24.1, client)

    async def test_returns_unchanged_when_geocoding_fails(self):
        listing = Listing(id="1", source="ss.lv", url="u", district="Mārupe")
        client, store = AsyncMock(), MagicMock()
        with patch("enrich.geocode", new_callable=AsyncMock, return_value=None) as geocode, patch(
            "enrich.commute_minutes", new_callable=AsyncMock
        ) as commute:
            result = await enrich.enrich_listing(listing, client, store)

        self.assertIs(result, listing)
        geocode.assert_awaited_once_with("Mārupe, Latvija", client, store)
        commute.assert_not_awaited()

    async def test_enrich_all_respects_cap(self):
        listings = [Listing(id=str(i), source="x", url="u") for i in range(4)]
        with patch("enrich.enrich_listing", new_callable=AsyncMock) as enrich_one:
            await enrich.enrich_all(listings, AsyncMock(), MagicMock(), cap=2)
        self.assertEqual(enrich_one.await_count, 2)
        self.assertEqual([call.args[0].id for call in enrich_one.await_args_list], ["0", "1"])


if __name__ == "__main__":
    unittest.main()
