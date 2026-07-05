"""Unit tests for the deterministic scorer (stdlib-only — no external deps)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "functions"))

from models import Listing  # noqa: E402
from scoring import WEIGHTS, HardFilters, passes_hard_filters, score, score_listing  # noqa: E402


class ScoreTests(unittest.TestCase):
    def test_score_is_bounded_and_complete(self):
        overall, breakdown = score({})
        self.assertTrue(0.0 <= overall <= 1.0)
        self.assertEqual(set(breakdown), set(WEIGHTS))

    def test_better_listing_scores_higher(self):
        good = {"commute": 10, "price_per_m2": 1500, "size": 120, "schools": 0.9,
                "energy": 2, "condition": 0.9}
        poor = {"commute": 55, "price_per_m2": 3800, "size": 45, "schools": 0.1,
                "energy": 6, "condition": 0.1}
        self.assertGreater(score(good)[0], score(poor)[0])

    def test_cost_criteria_are_inverted(self):
        # A shorter commute should beat a longer one, all else equal.
        self.assertGreater(score({"commute": 10})[0], score({"commute": 55})[0])


class HardFilterTests(unittest.TestCase):
    def test_rejects_over_budget(self):
        f = HardFilters(max_price=200000)
        self.assertFalse(passes_hard_filters(Listing(id="1", source="x", url="", price=250000), f))
        self.assertTrue(passes_hard_filters(Listing(id="2", source="x", url="", price=180000), f))

    def test_rejects_too_few_rooms(self):
        f = HardFilters(min_rooms=3)
        self.assertFalse(passes_hard_filters(Listing(id="1", source="x", url="", rooms=2), f))
        self.assertTrue(passes_hard_filters(Listing(id="2", source="x", url="", rooms=4), f))

    def test_rejects_flood_when_excluded(self):
        f = HardFilters(exclude_flood=True)
        self.assertFalse(
            passes_hard_filters(Listing(id="1", source="x", url="", flood_risk=True), f)
        )

    def test_rejects_ground_floor_when_excluded(self):
        f = HardFilters(exclude_ground_floor=True)
        self.assertFalse(passes_hard_filters(Listing(id="1", source="x", url="", floor="1/5"), f))
        self.assertTrue(passes_hard_filters(Listing(id="2", source="x", url="", floor="3/5"), f))
        self.assertTrue(passes_hard_filters(Listing(id="3", source="x", url="", floor=None), f))


class ScoreListingTests(unittest.TestCase):
    def test_energy_class_maps_into_score(self):
        best = Listing(id="1", source="x", url="", energy_class="A")
        worst = Listing(id="2", source="x", url="", energy_class="G")
        self.assertGreater(score_listing(best)[0], score_listing(worst)[0])

    def test_value_feature_rewards_underpriced(self):
        cheap = Listing(id="1", source="x", url="", features={"value": 0.9})
        dear = Listing(id="2", source="x", url="", features={"value": 0.1})
        self.assertGreater(score_listing(cheap)[0], score_listing(dear)[0])


if __name__ == "__main__":
    unittest.main()
