"""Pipeline orchestration: ingest → dedupe → enrich → value → extract → score → notify.

Only the scoring stage is real in this scaffold; the others are honest stubs that log a
TODO and pass data through, so `scripts/run_once.py` runs end-to-end without network.
"""
from __future__ import annotations

import logging
from typing import Optional

from models import Listing, ScoredListing
from scoring import HardFilters, passes_hard_filters, score
from sources import default_listing_sources

log = logging.getLogger("homescout.pipeline")


def ingest() -> list[Listing]:
    listings: list[Listing] = []
    for src in default_listing_sources():
        try:
            listings.extend(src.fetch_new())
        except Exception:  # noqa: BLE001 — one bad source shouldn't kill the run
            log.exception("source %s failed", getattr(src, "name", "?"))
    return listings


def dedupe(listings: list[Listing]) -> list[Listing]:
    # TODO: cross-portal dedup (perceptual hash on photos + fuzzy address/€). Report §C.
    seen: set[str] = set()
    out: list[Listing] = []
    for lst in listings:
        if lst.id in seen:
            continue
        seen.add(lst.id)
        out.append(lst)
    return out


def enrich(listing: Listing) -> Listing:
    # TODO: geocode → commute (ORS), schools (ĢEOLatvija), flood flag, amenities (Overpass).
    return listing


def value(listing: Listing) -> Optional[str]:
    # TODO: compare listing.price_per_m2 vs nearby VZD NĪTIS deals → "under"/"fair"/"over".
    return None


def extract_features(listing: Listing) -> Listing:
    # TODO: LLM structured extraction (condition, outdoor, noise, ...) into listing.features.
    return listing


def notify(scored: list[ScoredListing]) -> None:
    # TODO: send the ranked shortlist to Telegram.
    log.info("TODO: notify %d scored listings", len(scored))


def run_once(
    listings: Optional[list[Listing]] = None, *, notify_results: bool = False
) -> list[ScoredListing]:
    """Run the full pipeline once. Pass `listings` to run offline on sample data."""
    filters = HardFilters.from_env()
    raw = listings if listings is not None else ingest()
    log.info("ingested %d listings", len(raw))

    scored: list[ScoredListing] = []
    for lst in dedupe(raw):
        lst = enrich(lst)
        if not passes_hard_filters(lst, filters):
            continue
        lst = extract_features(lst)
        overall, breakdown = score(lst.features)
        scored.append(ScoredListing(lst, overall, breakdown, value(lst)))

    scored.sort(key=lambda s: s.score, reverse=True)
    if notify_results:
        notify(scored)
    return scored
