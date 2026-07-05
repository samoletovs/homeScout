"""Deterministic listing scoring — hard filters + weighted-sum (SAW).

The LLM is used only to *extract* features elsewhere; scoring itself is deterministic
and auditable, because LLMs are unreliable at direct numeric ranking. See the mindVault
dig report §C (2026-07-04-ai-property-hunt-system-latvia).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional

from models import Listing

# Criteria importance weights (1–5). Sensible defaults — personalise per user.
# Only criteria we actually populate today are scored; others arrive with LLM extraction.
WEIGHTS: dict[str, int] = {
    "commute": 5,       # city / airport access                  (cost)
    "schools": 5,       # nearest school/kindergarten            (benefit)
    "condition": 5,     # freshly renovated / new + fitted kitchen (turnkey)  (benefit)
    "size": 4,          # usable m² (space + home office)         (benefit)
    "value": 4,         # under/over-priced vs area (VZD NĪTIS)   (benefit)
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
    "condition": (0, 1),          # 0 needs work .. 1 turnkey renovated/new + kitchen
    "size": (40, 200),            # m²
    "price_per_m2": (800, 4000),  # €/m²
    "energy": (1, 7),             # A=1 (best) .. G=7 (worst)
}


@dataclass
class HardFilters:
    """Binary deal-breakers applied before scoring.

    Size/room floors have sensible defaults for this family (big, move-in-ready home);
    price bounds stay env-only so no budget figure lives in the repo.
    """

    max_price: Optional[float] = None
    min_price: Optional[float] = None
    min_rooms: Optional[int] = 4
    min_area: Optional[float] = 75.0
    max_commute_min: Optional[float] = None
    exclude_flood: bool = True
    exclude_ground_floor: bool = False
    exclude_rented: bool = True
    require_ready: bool = True

    @classmethod
    def from_env(cls) -> "HardFilters":
        def _num(key: str, default: Optional[float] = None) -> Optional[float]:
            raw = os.getenv(key)
            return float(raw) if raw else default

        def _int(key: str, default: Optional[int] = None) -> Optional[int]:
            raw = os.getenv(key)
            return int(raw) if raw else default

        def _bool(key: str, default: bool) -> bool:
            return os.getenv(key, "1" if default else "0") != "0"

        return cls(
            max_price=_num("HOMESCOUT_MAX_PRICE"),
            min_price=_num("HOMESCOUT_MIN_PRICE"),
            min_rooms=_int("HOMESCOUT_MIN_ROOMS", 4),
            min_area=_num("HOMESCOUT_MIN_AREA", 75.0),
            max_commute_min=_num("HOMESCOUT_MAX_COMMUTE"),
            exclude_flood=_bool("HOMESCOUT_EXCLUDE_FLOOD", True),
            exclude_ground_floor=_bool("HOMESCOUT_EXCLUDE_GROUND", False),
            exclude_rented=_bool("HOMESCOUT_EXCLUDE_RENTED", True),
            require_ready=_bool("HOMESCOUT_REQUIRE_READY", True),
        )


# Condition keywords (Latvian + Russian). The family will NOT renovate — they want a freshly
# renovated or newly built, fully move-in-ready home, ideally with a fitted kitchen.
_RENTED_KW = (
    "izīrē", "izīrēt", "izīrēts", "īrniek", "сдан", "сдаётся", "в аренд", "аренда",
)
_UNFINISHED_KW = (
    "nepabeigt", "nav pabeigt", "būvniecības stadij", "būvniecībā", "gaidāms nodošan",
    "plānots nodot", "nodošana 20", "nodos 20", "строится", "сдача в 20", "сдача дома",
    "стадия строитель", "на этапе строитель",
)
_NEEDS_RENO_KW = (
    "bez apdares", "без отделки", "черновая отделка", "черновой", "недостро",
    "требует ремонт", "требуется ремонт", "под ремонт", "нужен ремонт",
    "renovējams", "jārenovē", "vajadzīgs remont", "nepiecieš remont", "белая коробка",
    "под чистовую", "предчистов",
)
_RENOVATED_KW = (
    "renovēt", "izremont", "pēc remonta", "atjaunot", "jaunbūv", "jauns projekt",
    "новостройк", "новый дом", "с ремонтом", "после ремонта", "евроремонт",
    "сделан ремонт", "качественный ремонт", "капитальный ремонт", "отремонтир",
    "дизайнерск", "свежий ремонт", "с отделкой", "полная отделка", "готов к заселению",
    "заезжай и живи", "labs stāvokl", "lielisks stāvokl",
)
_KITCHEN_KW = (
    "virtuves iekārt", "iebūvēta virtuve", "aprīkota virtuve", "кухня", "кухонн",
    "с кухней", "встроенная кухня", "кухонный гарнитур", "мебель на кухне",
)


def _condition_flags(listing: Listing) -> dict:
    """Detect condition signals from the listing headline + description text."""
    text = f"{listing.title} {listing.description}".lower()
    return {
        "rented": any(kw in text for kw in _RENTED_KW),
        "unfinished": any(kw in text for kw in _UNFINISHED_KW),
        "needs_reno": any(kw in text for kw in _NEEDS_RENO_KW),
        "renovated": any(kw in text for kw in _RENOVATED_KW),
        "kitchen": any(kw in text for kw in _KITCHEN_KW),
    }


def _condition_score(listing: Listing) -> float:
    """0..1 turnkey score: renovated/new + fitted kitchen ranks highest."""
    flags = _condition_flags(listing)
    if flags["needs_reno"] or flags["unfinished"]:
        return 0.0
    if flags["renovated"] and flags["kitchen"]:
        return 1.0
    if flags["renovated"]:
        return 0.85
    if flags["kitchen"]:
        return 0.6
    return 0.4  # condition unstated — shown, but ranked below explicit turnkey homes


def _floor_num(floor: Optional[str]) -> Optional[int]:
    """Current floor from a 'n/total' string (ground floor == 1 in Latvia)."""
    if not floor:
        return None
    match = re.match(r"\s*(\d+)", floor)
    return int(match.group(1)) if match else None


def passes_hard_filters(listing: Listing, f: HardFilters) -> bool:
    """True if the listing clears every configured deal-breaker."""
    if f.max_price is not None and listing.price is not None and listing.price > f.max_price:
        return False
    if f.min_price is not None and listing.price is not None and listing.price < f.min_price:
        return False
    if f.min_rooms is not None and listing.rooms is not None and listing.rooms < f.min_rooms:
        return False
    if f.min_area is not None and listing.area_m2 is not None and listing.area_m2 < f.min_area:
        return False
    if (
        f.max_commute_min is not None
        and listing.commute_min is not None
        and listing.commute_min > f.max_commute_min
    ):
        return False
    if f.exclude_flood and listing.flood_risk:
        return False
    if f.exclude_ground_floor and _floor_num(listing.floor) == 1:
        return False
    if f.exclude_rented or f.require_ready:
        flags = _condition_flags(listing)
        if f.exclude_rented and flags["rented"]:
            return False
        if f.require_ready and (flags["unfinished"] or flags["needs_reno"]):
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
    feats["condition"] = _condition_score(listing)
    return score(feats)
