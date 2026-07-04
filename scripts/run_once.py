"""Local one-shot runner — dry-runs the pipeline on sample data (no network)."""
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "functions"))

from models import Listing  # noqa: E402
from pipeline import run_once  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

SAMPLE = [
    Listing(
        id="s1", source="sample", url="https://example/1", title="3-room, Mārupe",
        price=210000, area_m2=78, rooms=3, district="Mārupe", commute_min=18,
        features={"commute": 18, "price_per_m2": 2692, "size": 78, "schools": 0.8,
                  "energy": 2, "outdoor": 1, "noise": 0.4, "condition": 0.9,
                  "parking": 1, "resale": 0.8},
    ),
    Listing(
        id="s2", source="sample", url="https://example/2", title="2-room, Rīga centre",
        price=185000, area_m2=48, rooms=2, district="Centrs", commute_min=8,
        features={"commute": 8, "price_per_m2": 3854, "size": 48, "schools": 0.5,
                  "energy": 5, "outdoor": 0, "noise": 0.8, "condition": 0.5,
                  "parking": 0, "resale": 0.7},
    ),
]


def main() -> None:
    scored = run_once(SAMPLE)
    print(f"\nRanked {len(scored)} listing(s):\n")
    for i, s in enumerate(scored, 1):
        ppm2 = s.listing.price_per_m2 or 0
        print(
            f"{i}. {s.score:>5.3f}  {s.listing.title}  "
            f"(€{s.listing.price:,.0f}, {ppm2:,.0f} €/m²)"
        )


if __name__ == "__main__":
    main()
