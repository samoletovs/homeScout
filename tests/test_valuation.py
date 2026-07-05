"""Valuation tests (offline; fake index + real logic)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "functions"))

from models import Listing  # noqa: E402
from valuation import bucket_for, value_listing, verdict  # noqa: E402

FAKE = {"buckets": {"Rīga": {"median_ppm2": 1200.0}, "Mārupe": {"median_ppm2": 2000.0}}}


def _apt(price: float, area: float, area_name: str) -> Listing:
    return Listing(id="1", source="x", url="u", price=price, area_m2=area,
                   district=area_name, description=area_name, property_type="apartment")


class VerdictTests(unittest.TestCase):
    def test_over(self):
        label, delta = verdict(2400, 2000)
        self.assertEqual(label, "over")
        self.assertAlmostEqual(delta, 0.2)

    def test_under(self):
        self.assertEqual(verdict(1600, 2000)[0], "under")

    def test_fair(self):
        self.assertEqual(verdict(2050, 2000)[0], "fair")


class BucketTests(unittest.TestCase):
    def test_riga_from_city_hint(self):
        listing = Listing(id="1", source="x", url="u", district="Pļavnieki", description="Rīga")
        self.assertEqual(bucket_for(listing), "Rīga")

    def test_marupe(self):
        listing = Listing(id="1", source="x", url="u", district="Mārupe", description="Mārupe")
        self.assertEqual(bucket_for(listing), "Mārupe")

    def test_unknown_area(self):
        listing = Listing(id="1", source="x", url="u", district="Liepāja", description="Liepāja")
        self.assertIsNone(bucket_for(listing))


class ValueListingTests(unittest.TestCase):
    def test_under_priced_apartment(self):
        lst = _apt(120000, 80, "Mārupe")  # 1500 vs 2000 → under
        value_listing(lst, FAKE)
        self.assertTrue(lst.valuation.startswith("under"))
        self.assertGreater(lst.features["value"], 0.5)

    def test_fair_apartment(self):
        lst = _apt(160000, 80, "Mārupe")  # 2000 vs 2000 → fair
        value_listing(lst, FAKE)
        self.assertIn("fair", lst.valuation)

    def test_house_is_not_valued(self):
        lst = _apt(300000, 150, "Mārupe")
        lst.property_type = "house"
        value_listing(lst, FAKE)
        self.assertIsNone(lst.valuation)

    def test_unknown_area_is_not_valued(self):
        value_listing((lst := _apt(100000, 50, "Liepāja")), FAKE)
        self.assertIsNone(lst.valuation)


if __name__ == "__main__":
    unittest.main()
