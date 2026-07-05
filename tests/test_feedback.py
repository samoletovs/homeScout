"""Feedback + learning-loop tests (offline; translate disabled)."""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "functions"))

from feedback import format_taste_for_adviser, ingest, parse_sentiment, record  # noqa: E402
from models import Listing  # noqa: E402
from store import Store  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class SentimentTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_sentiment("like"), 1)
        self.assertEqual(parse_sentiment("👎"), -1)
        self.assertEqual(parse_sentiment("что-то"), 0)


class FeedbackStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.listing = Listing(id="1", source="ss.lv", url="http://x/1",
                               price=200000, area_m2=50, rooms=2, district="Rīga")
        self.store.filter_new([self.listing])
        self.store.save_evaluation(self.listing, "Rīga")

    def tearDown(self):
        self.store.close()

    def test_ingest_and_taste_summary(self):
        ok = _run(ingest(self.store, "http://x/1", "papa", 1, "нравится район", translate=False))
        self.assertTrue(ok)
        summary = self.store.taste_summary()
        self.assertEqual(summary["liked"], 1)
        self.assertEqual(summary["by_area"]["Rīga"]["like"], 1)
        self.assertIn("1 liked", format_taste_for_adviser(summary))

    def test_unknown_listing_rejected(self):
        self.assertFalse(_run(ingest(self.store, "http://nope", "papa", 1, "x", translate=False)))


class TasteFormatTests(unittest.TestCase):
    def test_empty_is_none(self):
        empty = {"liked": 0, "disliked": 0, "by_area": {}, "recent": []}
        self.assertIsNone(format_taste_for_adviser(empty))


class RecordTests(unittest.TestCase):
    def test_record_stores_and_returns_taste(self):
        import shutil
        import tempfile

        tmpdir = tempfile.mkdtemp()
        tmp = os.path.join(tmpdir, "hs.sqlite")
        try:
            seed = Store(tmp)
            seed.filter_new([Listing(id="1", source="city24", url="https://city24.lv/1",
                                     price=190000, area_m2=78, rooms=3, district="Mārupe")])
            seed.close()
            res = _run(record(
                {"listing_ref": "https://city24.lv/1", "member": "mama",
                 "sentiment": "like", "comment": "нравится"},
                db_path=tmp,
            ))
            self.assertTrue(res["ok"])
            self.assertIn("1 liked", res["taste"])
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_record_requires_ref(self):
        res = _run(record({"member": "papa", "sentiment": 1}))
        self.assertFalse(res["ok"])


if __name__ == "__main__":
    unittest.main()
