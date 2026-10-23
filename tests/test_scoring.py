"""Unit tests for the deterministic scorer (stdlib-only — no external deps)."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "functions"))

from models import Listing  # noqa: E402
from scoring import WEIGHTS, HardFilters, passes_hard_filters, score, score_listing  # noqa: E402


class ScoreTests(unittest.TestCase):
    def test_score_is_bounded_and_complete(self):
        overall, breakdown = score({})
        self.assertTrue(0.0 <= overall <= 1.0)
        self.assertEqual(set(breakdown), set(WEIGHTS))

    def test_missing_features_score_neutral(self):
        overall, breakdown = score({})
        self.assertEqual(overall, 0.5)
        self.assertEqual(set(breakdown.values()), {round(weight * 0.5, 4) for weight in WEIGHTS.values()})

    def test_better_listing_scores_higher(self):
        good = {"commute": 10, "price_per_m2": 1500, "size": 120, "schools": 0.9,
                "energy": 2, "condition": 0.9}
        poor = {"commute": 55, "price_per_m2": 3800, "size": 45, "schools": 0.1,
                "energy": 6, "condition": 0.1}
        self.assertGreater(score(good)[0], score(poor)[0])

    def test_cost_criteria_are_inverted(self):
        # A shorter commute should beat a longer one, all else equal.
        self.assertGreater(score({"commute": 10})[0], score({"commute": 55})[0])

    def test_normalization_clamps_out_of_range_values(self):
        _, low = score({"size": -1, "commute": 100})
        _, high = score({"size": 500, "commute": 0})
        self.assertEqual(low["size"], 0.0)
        self.assertEqual(low["commute"], 0.0)
        self.assertEqual(high["size"], WEIGHTS["size"])
        self.assertEqual(high["commute"], WEIGHTS["commute"])

    def test_benefit_criterion_rewards_higher_value(self):
        self.assertGreater(score({"size": 150})[0], score({"size": 80})[0])

    def test_cost_criterion_rewards_lower_value(self):
        self.assertGreater(score({"energy": 2})[0], score({"energy": 6})[0])

    def test_none_feature_is_treated_as_missing(self):
        self.assertEqual(score({"size": None})[0], score({})[0])


class HardFilterTests(unittest.TestCase):
    def test_rejects_over_budget(self):
        f = HardFilters(max_price=200000)
        self.assertFalse(passes_hard_filters(Listing(id="1", source="x", url="", price=250000), f))
        self.assertTrue(passes_hard_filters(Listing(id="2", source="x", url="", price=180000), f))

    def test_price_limits_include_their_boundaries(self):
        f = HardFilters(min_price=100000, max_price=200000)
        self.assertTrue(passes_hard_filters(Listing(id="1", source="x", url="", price=100000), f))
        self.assertTrue(passes_hard_filters(Listing(id="2", source="x", url="", price=200000), f))
        self.assertFalse(passes_hard_filters(Listing(id="3", source="x", url="", price=99999), f))

    def test_rejects_too_few_rooms(self):
        f = HardFilters(min_rooms=3)
        self.assertFalse(passes_hard_filters(Listing(id="1", source="x", url="", rooms=2), f))
        self.assertTrue(passes_hard_filters(Listing(id="2", source="x", url="", rooms=4), f))

    def test_area_and_commute_limits_include_their_boundaries(self):
        f = HardFilters(min_area=75, max_commute_min=30)
        listing = Listing(id="1", source="x", url="", area_m2=75, commute_min=30)
        self.assertTrue(passes_hard_filters(listing, f))
        listing.area_m2 = 74.99
        self.assertFalse(passes_hard_filters(listing, f))
        listing.area_m2, listing.commute_min = 75, 30.01
        self.assertFalse(passes_hard_filters(listing, f))

    def test_missing_values_do_not_fail_numeric_filters(self):
        self.assertTrue(
            passes_hard_filters(
                Listing(id="1", source="x", url=""),
                HardFilters(min_price=100000, max_price=200000, min_rooms=4, min_area=75,
                            max_commute_min=30),
            )
        )

    def test_excludes_fixer_upper_accepts_turnkey(self):
        base = dict(source="ss.lv", url="u", price=200000, area_m2=100, rooms=4)
        fixer = Listing(id="1", title="Dzīvoklis bez apdares, требует ремонта", **base)
        turnkey = Listing(id="2", title="Свежий ремонт, встроенная кухня", **base)
        f = HardFilters()  # defaults: 4 rooms / 75 m², require_ready
        self.assertFalse(passes_hard_filters(fixer, f))
        self.assertTrue(passes_hard_filters(turnkey, f))

    def test_turnkey_scores_above_unstated(self):
        from scoring import _condition_score
        turnkey = Listing(id="1", source="x", url="u", title="новостройка, встроенная кухня")
        plain = Listing(id="2", source="x", url="u", title="Dzīvoklis Rīgā")
        self.assertGreater(_condition_score(turnkey), _condition_score(plain))

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

    def test_from_env_parses_filter_settings(self):
        with patch.dict(os.environ, {
            "HOMESCOUT_MAX_PRICE": "250000",
            "HOMESCOUT_MIN_ROOMS": "3",
            "HOMESCOUT_MIN_AREA": "80.5",
            "HOMESCOUT_EXCLUDE_FLOOD": "0",
            "HOMESCOUT_REQUIRE_READY": "0",
        }, clear=True):
            filters = HardFilters.from_env()
        self.assertEqual(filters.max_price, 250000)
        self.assertEqual(filters.min_rooms, 3)
        self.assertEqual(filters.min_area, 80.5)
        self.assertFalse(filters.exclude_flood)
        self.assertFalse(filters.require_ready)


class ScoreListingTests(unittest.TestCase):
    def test_energy_class_maps_into_score(self):
        best = Listing(id="1", source="x", url="", energy_class="A")
        worst = Listing(id="2", source="x", url="", energy_class="G")
        self.assertGreater(score_listing(best)[0], score_listing(worst)[0])

    def test_value_feature_rewards_underpriced(self):
        cheap = Listing(id="1", source="x", url="", features={"value": 0.9})
        dear = Listing(id="2", source="x", url="", features={"value": 0.1})
        self.assertGreater(score_listing(cheap)[0], score_listing(dear)[0])

    def test_explicit_energy_feature_takes_precedence(self):
        listing = Listing(id="1", source="x", url="", energy_class="A", features={"energy": 7})
        self.assertEqual(score_listing(listing)[1]["energy"], 0.0)

    def test_energy_class_is_case_and_whitespace_insensitive(self):
        class_b = Listing(id="1", source="x", url="", energy_class=" b ")
        class_g = Listing(id="2", source="x", url="", energy_class="G")
        self.assertGreater(score_listing(class_b)[0], score_listing(class_g)[0])

    def test_unknown_energy_class_leaves_criterion_neutral(self):
        listing = Listing(id="1", source="x", url="", energy_class="unknown")
        self.assertEqual(score_listing(listing)[0], score_listing(Listing(id="2", source="x", url=""))[0])

    def test_condition_feature_is_derived_from_listing_text(self):
        listing = Listing(id="1", source="x", url="", title="новостройка, встроенная кухня",
                          features={"condition": 0.0})
        plain = Listing(id="2", source="x", url="")
        self.assertGreater(score_listing(listing)[0], score_listing(plain)[0])


if __name__ == "__main__":
    unittest.main()
