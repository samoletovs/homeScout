"""Store dedup tests (in-memory sqlite, offline)."""
import os
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "functions"))

from models import Listing  # noqa: E402
from store import Store  # noqa: E402


def _mk(listing_id: str, price: float) -> Listing:
    return Listing(id=listing_id, source="ss.lv", url=f"http://x/{listing_id}",
                   price=price, area_m2=50, rooms=2, district="Rīga")


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = Store(":memory:")

    def tearDown(self) -> None:
        self.store.close()

    def test_new_listing_then_seen(self):
        first = self.store.filter_new([_mk("a", 100000)])
        self.assertEqual([reason for _, reason in first], ["new"])
        second = self.store.filter_new([_mk("a", 100000)])
        self.assertEqual(second, [])  # already seen, unchanged

    def test_price_drop_is_detected(self):
        self.store.filter_new([_mk("a", 100000)])
        dropped = self.store.filter_new([_mk("a", 90000)])
        self.assertEqual([reason for _, reason in dropped], ["price_drop"])

    def test_price_increase_is_not_alerted(self):
        self.store.filter_new([_mk("a", 100000)])
        self.assertEqual(self.store.filter_new([_mk("a", 110000)]), [])

    def test_is_empty_reflects_state(self):
        self.assertTrue(self.store.is_empty())
        self.store.filter_new([_mk("a", 100000)])
        self.assertFalse(self.store.is_empty())

    def test_get_listings_empty(self):
        self.assertEqual(self.store.get_listings(), [])

    def test_get_listings_includes_stored_fields_and_decodes_features(self):
        listing = _mk("a", 100000)
        listing.features = {"balcony": True}
        self.store.filter_new([listing, _mk("b", 120000)])
        self.store.save_evaluation(listing, "Rīga")
        self.store.filter_new([_mk("a", 90000)])

        rows = self.store.get_listings()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["key"], "ss.lv:a")
        self.assertEqual(rows[0]["district"], "Rīga")
        self.assertEqual(rows[0]["price"], 90000)
        self.assertEqual(rows[0]["features"], {"balcony": True})
        self.assertEqual(rows[0]["bucket"], "Rīga")
        self.assertTrue(rows[0]["first_seen"])
        self.assertTrue(rows[0]["last_seen"])
        self.assertEqual(rows[1]["features"], {})
        self.assertIsNone(rows[1]["score"])

    def test_save_evaluation_and_area_stats(self):
        listing = _mk("a", 200000)  # area_m2 50 → 4000 €/m²
        listing.score = 0.7
        listing.valuation = "under (-5% vs Rīga median)"
        self.store.filter_new([listing])
        self.store.save_evaluation(listing, "Rīga")
        stats = self.store.area_stats("Rīga")
        self.assertEqual(stats["count"], 1)
        self.assertAlmostEqual(stats["avg_ppm2"], 4000.0)
        self.assertEqual(self.store.area_stats("Mārupe")["count"], 0)


class OpenStoreTests(unittest.TestCase):
    def test_explicit_path_always_sqlite(self):
        # An explicit db_path must win over COSMOS_ENDPOINT (used by preview + tests).
        from store import open_store
        os.environ["COSMOS_ENDPOINT"] = "https://example.documents.azure.com:443/"
        try:
            store = open_store(":memory:")
            self.assertIsInstance(store, Store)
            store.close()
        finally:
            os.environ.pop("COSMOS_ENDPOINT", None)


class CosmosHelperTests(unittest.TestCase):
    def test_geo_id_is_stable_and_id_safe(self):
        from cosmos_store import _geo_id  # importable without the azure-cosmos package
        self.assertEqual(_geo_id("Mārupe, Latvija"), _geo_id("Mārupe, Latvija"))
        self.assertNotEqual(_geo_id("Rīga"), _geo_id("Jūrmala"))
        self.assertNotIn("/", _geo_id("a/b#c?d"))

    def test_get_listings_empty(self):
        from cosmos_store import CosmosStore
        store = CosmosStore.__new__(CosmosStore)
        store._listings = Mock()
        store._listings.query_items.return_value = iter([])
        self.assertEqual(store.get_listings(), [])

    def test_get_listings_matches_sqlite_without_cosmos_metadata(self):
        from cosmos_store import CosmosStore
        sqlite = Store()
        try:
            sqlite.filter_new([_mk("a", 100000)])
            expected = sqlite.get_listings()
        finally:
            sqlite.close()
        doc = {k: v for k, v in expected[0].items()
               if v is not None and k != "features"}
        doc.update({"id": "ss.lv:a", "_etag": "internal", "prices": []})
        store = CosmosStore.__new__(CosmosStore)
        store._listings = Mock()
        store._listings.query_items.return_value = iter([doc])

        self.assertEqual(store.get_listings(), expected)
        self.assertTrue(store._listings.query_items.call_args.kwargs["enable_cross_partition_query"])


if __name__ == "__main__":
    unittest.main()
