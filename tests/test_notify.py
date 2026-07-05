"""Notification formatting tests (offline; no network)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "functions"))

from models import Listing  # noqa: E402
from notify import TelegramNotifier, format_digest, format_listing  # noqa: E402


def _listing() -> Listing:
    return Listing(id="1", source="ss.lv", url="https://ss.lv/x.html",
                   title="Bright flat", price=200000, area_m2=50, rooms=2,
                   district="Rīga", energy_class="B")


class FormatTests(unittest.TestCase):
    def test_contains_key_facts(self):
        msg = format_listing(_listing(), "new")
        self.assertIn("€200,000", msg)
        self.assertIn("2 rooms", msg)
        self.assertIn("50 m²", msg)
        self.assertIn("https://ss.lv/x.html", msg)
        self.assertIn("🆕", msg)

    def test_price_drop_uses_distinct_tag(self):
        self.assertIn("📉", format_listing(_listing(), "price_drop"))


class NotifierTests(unittest.TestCase):
    def test_disabled_without_credentials(self):
        self.assertFalse(TelegramNotifier(token="", chat_id="").enabled)

    def test_enabled_with_credentials(self):
        self.assertTrue(TelegramNotifier(token="t", chat_id="c").enabled)


class DigestTests(unittest.TestCase):
    def test_digest_ranks_and_limits(self):
        items = [
            (Listing(id="1", source="x", url="u1", district="Rīga", price=100000, score=0.40), "new"),
            (Listing(id="2", source="x", url="u2", district="Mārupe", price=200000, score=0.80), "new"),
            (Listing(id="3", source="x", url="u3", district="Jūrmala", price=150000, score=0.60), "new"),
        ]
        msg = format_digest(items, limit=2)
        self.assertIn("homeScout", msg)   # header present (language-agnostic)
        self.assertIn("u2", msg)          # rank 1 kept
        self.assertIn("u3", msg)          # rank 2 kept
        self.assertNotIn("u1", msg)       # rank 3 dropped by limit


if __name__ == "__main__":
    unittest.main()
