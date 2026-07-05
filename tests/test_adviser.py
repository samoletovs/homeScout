"""Adviser tests (offline — no LLM calls; prompt building + config gating)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "functions"))

from adviser import build_messages, enabled  # noqa: E402
from models import Listing  # noqa: E402


def _listing() -> Listing:
    return Listing(
        id="1", source="city24", url="u", district="Mārupe", description="Mārupe",
        price=190000, area_m2=78, rooms=3, energy_class="A", commute_min=14,
        nearest_school_km=1.4, valuation="under (-8% vs Mārupe median 1,980 €/m²)",
        property_type="apartment",
    )


class AdviserPromptTests(unittest.TestCase):
    def test_messages_include_facts_and_profile(self):
        msgs = build_messages(_listing(), {"count": 12, "avg_ppm2": 2400.0})
        self.assertEqual(len(msgs), 2)
        joined = msgs[0]["content"] + msgs[1]["content"]
        self.assertIn("Mārupe", joined)
        self.assertIn("under", joined)            # valuation carried through
        self.assertIn("12 listings", joined)      # market context grounds it
        self.assertIn("buyer's agent", msgs[0]["content"])

    def test_messages_without_stats(self):
        msgs = build_messages(_listing(), None)
        self.assertNotIn("Market context", msgs[1]["content"])

    def test_messages_include_taste_and_language(self):
        msgs = build_messages(_listing(), None, taste="1 liked, 0 disliked | Mārupe +1/-0", lang="ru")
        joined = msgs[0]["content"] + msgs[1]["content"]
        self.assertIn("Russian", joined)
        self.assertIn("Learned family preferences", msgs[0]["content"])
        self.assertIn("Mārupe +1", msgs[0]["content"])

    def test_enabled_is_bool(self):
        self.assertIsInstance(enabled(), bool)


if __name__ == "__main__":
    unittest.main()
