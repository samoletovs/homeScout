"""Notification formatting tests (offline; no network)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "functions"))

from models import Listing  # noqa: E402
from notify import TelegramNotifier, feedback_buttons, format_digest, format_listing  # noqa: E402


def _listing() -> Listing:
    return Listing(id="1", source="ss.lv", url="https://ss.lv/x.html",
                   title="Bright flat", price=200000, area_m2=50, rooms=2,
                   district="Rīga", energy_class="B")


class FormatTests(unittest.TestCase):
    def test_contains_key_facts(self):
        msg = format_listing(_listing(), "new")
        self.assertIn("€200,000", msg)
        self.assertIn("2 комн.", msg)
        self.assertIn("50 м²", msg)
        self.assertIn("https://ss.lv/x.html", msg)
        self.assertIn("🆕", msg)

    def test_price_drop_uses_distinct_tag(self):
        self.assertIn("📉", format_listing(_listing(), "price_drop"))


class NotifierTests(unittest.TestCase):
    def test_disabled_without_credentials(self):
        self.assertFalse(TelegramNotifier(token="", chat_id="").enabled)

    def test_enabled_with_credentials(self):
        self.assertTrue(TelegramNotifier(token="t", chat_id="c").enabled)

    def test_chat_id_list_reaches_every_family_member(self):
        notifier = TelegramNotifier(token="t", chat_id="111, 222,333")
        self.assertEqual(notifier.chat_ids, ["111", "222", "333"])
        self.assertEqual(notifier.chat_id, "111")
        self.assertTrue(notifier.enabled)

    def test_single_chat_id_still_works(self):
        self.assertEqual(TelegramNotifier(token="t", chat_id="111").chat_ids, ["111"])

    def test_cards_are_sent_to_every_chat(self):
        import asyncio

        notifier = TelegramNotifier(token="t", chat_id="111,222")
        payloads: list[dict] = []

        async def _capture(client, payload):
            payloads.append(payload)

        notifier._send = _capture  # noqa: SLF001 — exercising the broadcast, not the HTTP call
        sent = asyncio.run(
            notifier.send_cards([(_listing(), "new")], client=None, top_n=1, pause_s=0)
        )
        self.assertEqual(sent, 2)
        self.assertEqual([p["chat_id"] for p in payloads], ["111", "222"])

    def test_one_failing_chat_does_not_block_the_others(self):
        import asyncio

        notifier = TelegramNotifier(token="t", chat_id="111,222")
        delivered: list[str] = []

        async def _flaky(client, payload):
            if payload["chat_id"] == "111":
                raise RuntimeError("blocked by user")
            delivered.append(payload["chat_id"])

        notifier._send = _flaky  # noqa: SLF001
        sent = asyncio.run(
            notifier.send_cards([(_listing(), "new")], client=None, top_n=1, pause_s=0)
        )
        self.assertEqual(sent, 1)
        self.assertEqual(delivered, ["222"])


class CardTests(unittest.TestCase):
    def test_feedback_buttons_encode_key(self):
        datas = [b["callback_data"] for row in feedback_buttons(_listing()) for b in row]
        self.assertIn("hs:1:ss.lv:1", datas)
        self.assertIn("hs:-1:ss.lv:1", datas)

    def test_callback_data_within_telegram_limit(self):
        # Telegram rejects callback_data over 64 bytes (BUTTON_DATA_INVALID).
        from models import Listing
        lst = Listing(id="epjdd", source="ss.lv", url="https://www.ss.lv/msg/lv/real-estate/x.html")
        for row in feedback_buttons(lst):
            for btn in row:
                self.assertLessEqual(len(btn["callback_data"].encode()), 64)

    def test_listing_shows_adviser_take(self):
        lst = _listing()
        lst.adviser = "Great fit near the school."
        self.assertIn("💬 Great fit near the school.", format_listing(lst, "new"))


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
