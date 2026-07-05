"""Deterministic listing scoring — hard filters + weighted-sum (SAW).

The LLM is used only to *extract* features elsewhere; scoring itself is deterministic
and auditable, because LLMs are unreliable at direct numeric ranking. See the mindVault
dig report §C (2026-07-04-ai-property-hunt-system-latvia).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from models import Listing

# Criteria importance weights (1–5). Sensible defaults — personalise per user.
# Only criteria we actually populate today are scored; others arrive with LLM extraction.
WEIGHTS: dict[str, int] = {
    "value": 5,         # under/over-priced vs area (VZD NĪTIS)   (benefit)
    "commute": 5,       # minutes to centre/work                 (cost)
    "schools": 4,       # nearest school/kindergarten            (benefit)
    "size": 4,          # usable m²                              (benefit)
    "price_per_m2": 3,  # absolute €/m²                          (cost)
    "energy": 3,        # energy class running cost              (cost)
}

# Criteria where a higher raw value is worse (normalisation is inverted).
COST_CRITERIA = {"commute", "price_per_m2", "energy"}

# (lo, hi) bounds used to normalise each raw feature to 0..1.
RANGES: dict[str, tuple[float, float]] = {
    "value": (0, 1),              # 0 over-priced .. 1 under-priced
    "commute": (5, 60),           # minutes
    "schools": (0, 1),            # pre-normalised proximity
    "size": (40, 200),            # m²
    "price_per_m2": (800, 4000),  # €/m²
    "energy": (1, 7),             # A=1 (best) .. G=7 (worst)
}


@dataclass
class HardFilters:
    """Binary deal-breakers applied before scoring.

    No real figures are baked in — values come from the environment so a personal
    budget never lives in the repo.
    """

    max_price: Optional[float] = None
    min_rooms: Optional[int] = None
    max_commute_min: Optional[float] = None
    exclude_flood: bool = True

    @classmethod
    def from_env(cls) -> "HardFilters":
        def _num(key: str) -> Optional[float]:
            raw = os.getenv(key)
            return float(raw) if raw else None

        rooms = os.getenv("HOMESCOUT_MIN_ROOMS")
        return cls(
            max_price=_num("HOMESCOUT_MAX_PRICE"),
            min_rooms=int(rooms) if rooms else None,
            max_commute_min=_num("HOMESCOUT_MAX_COMMUTE"),
            exclude_flood=os.getenv("HOMESCOUT_EXCLUDE_FLOOD", "1") != "0",
        )


def passes_hard_filters(listing: Listing, f: HardFilters) -> bool:
    """True if the listing clears every configured deal-breaker."""
    if f.max_price is not None and listing.price is not None and listing.price > f.max_price:
        return False
    if f.min_rooms is not None and listing.rooms is not None and listing.rooms < f.min_rooms:
        return False
    if (
        f.max_commute_min is not None
        and listing.commute_min is not None
        and listing.commute_min > f.max_commute_min
    ):
        return False
    if f.exclude_flood and listing.flood_risk:
        return False
    return True


def _normalise(name: str, value: float) -> float:
    lo, hi = RANGES[name]
    if hi == lo:
        return 0.5
    x = max(0.0, min(1.0, (value - lo) / (hi - lo)))
    return 1.0 - x if name in COST_CRITERIA else x


def score(features: dict[str, float]) -> tuple[float, dict[str, float]]:
    """Weighted-sum score in 0..1 plus each criterion's weighted contribution.

    Missing features score a neutral 0.5, so an incomplete listing is neither
    unfairly punished nor rewarded.
    """
    total_weight = sum(WEIGHTS.values())
    breakdown: dict[str, float] = {}
    acc = 0.0
    for name, weight in WEIGHTS.items():
        raw = features.get(name)
        n = 0.5 if raw is None else _normalise(name, float(raw))
        contribution = weight * n
        breakdown[name] = round(contribution, 4)
        acc += contribution
    return round(acc / total_weight, 4), breakdown


ENERGY_MAP = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7}


def score_listing(listing: Listing) -> tuple[float, dict[str, float]]:
    """Score a listing from its enriched features, deriving energy from its class."""
    feats = dict(listing.features)
    if "energy" not in feats and listing.energy_class:
        feats["energy"] = ENERGY_MAP.get(listing.energy_class.strip().upper()[:1])
    return score(feats)
