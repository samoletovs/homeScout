"""Valuation — compare a listing's €/m² to registered sold-deals (VZD NĪTIS).

Uses a committed median index (functions/assets/lv_deals.json). Apartment-only; the area
median is city/municipality level, so treat Rīga (heterogeneous) as a rough guide and
Mārupe/Jūrmala (smaller, more uniform) as more precise.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

from models import Listing

log = logging.getLogger("homescout.valuation")

_INDEX_PATH = os.path.join(os.path.dirname(__file__), "assets", "lv_deals.json")
_index_cache: Optional[dict] = None


def load_index() -> dict:
    """Load and cache the committed sold-deal median index."""
    global _index_cache
    if _index_cache is None:
        try:
            with open(_INDEX_PATH, encoding="utf-8") as handle:
                _index_cache = json.load(handle)
        except FileNotFoundError:
            log.warning("deals index missing: %s", _INDEX_PATH)
            _index_cache = {"buckets": {}}
    return _index_cache


def bucket_for(listing: Listing) -> Optional[str]:
    """Map a listing to one of the valuation areas by its locality names."""
    text = " ".join(filter(None, [listing.district, listing.description])).lower()
    if "mārup" in text or "marup" in text:
        return "Mārupe"
    if "jūrmala" in text or "jurmala" in text:
        return "Jūrmala"
    if "rīga" in text or "riga" in text:
        return "Rīga"
    return None


def verdict(ppm2: float, median: float, band: float = 0.10) -> tuple[str, float]:
    """Classify €/m² vs area median: 'under' / 'fair' / 'over', plus the fractional delta."""
    delta = (ppm2 - median) / median
    if delta <= -band:
        return "under", delta
    if delta >= band:
        return "over", delta
    return "fair", delta


def value_listing(listing: Listing, index: Optional[dict] = None) -> None:
    """Annotate listing.valuation (+ features['value']) from area comparables."""
    if listing.property_type != "apartment":
        return
    ppm2 = listing.price_per_m2
    bucket = bucket_for(listing)
    if not ppm2 or not bucket:
        return
    idx = index if index is not None else load_index()
    entry = idx.get("buckets", {}).get(bucket)
    if not entry or not entry.get("median_ppm2"):
        return
    median = entry["median_ppm2"]
    label, delta = verdict(ppm2, median)
    listing.valuation = f"{label} ({delta * 100:+.0f}% vs {bucket} median {median:,.0f} €/m²)"
    # Scoring feature (Phase 4): cheaper-than-area is better → higher score.
    listing.features["value"] = max(0.0, min(1.0, 0.5 - delta))
