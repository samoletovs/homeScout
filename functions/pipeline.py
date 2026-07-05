"""Pipeline: ingest → dedupe → store(seen) → alert.

Phase 1 (MVP): new-listing + price-drop Telegram alerts, deduped across sources and
across runs. Enrichment / valuation / scoring arrive in later phases.
"""
from __future__ import annotations

import logging

import httpx

from adviser import advise
from adviser import enabled as adviser_enabled
from config import ADVISE_TOP_N, DB_PATH, ENRICH_CAP, USER_AGENT
from enrich import enrich_all
from feedback import format_taste_for_adviser
from models import Listing
from notify import TelegramNotifier
from scoring import HardFilters, passes_hard_filters, score_listing
from sources import fetch_all
from store import Store
from valuation import bucket_for, value_listing

log = logging.getLogger("homescout.pipeline")


def _dedupe(listings: list[Listing]) -> list[Listing]:
    seen: set[str] = set()
    unique: list[Listing] = []
    for lst in listings:
        key = f"{lst.source}:{lst.id}"
        if key not in seen:
            seen.add(key)
            unique.append(lst)
    return unique


async def run_once(*, db_path: str = DB_PATH, notify_results: bool = True) -> list[tuple[Listing, str]]:
    """Fetch, dedupe, persist, and return alertable (listing, reason) pairs.

    On the first run against an empty store, listings are seeded silently (no alert
    flood); later runs alert only genuinely new or price-dropped listings.
    """
    filters = HardFilters.from_env()
    store = Store(db_path)
    try:
        seeding = store.is_empty()
        async with httpx.AsyncClient(timeout=25.0, headers={"User-Agent": USER_AGENT}) as client:
            listings = _dedupe(await fetch_all(client))
            listings = [lst for lst in listings if passes_hard_filters(lst, filters)]
            fresh = store.filter_new(listings)
            log.info("ingested=%d alertable=%d seeding=%s", len(listings), len(fresh), seeding)
            if seeding:
                log.info("first run — seeded %d listings, no alerts sent", len(fresh))
            elif fresh:
                fresh_listings = [lst for lst, _ in fresh]
                await enrich_all(fresh_listings, client, store, cap=ENRICH_CAP)
                for listing in fresh_listings:
                    value_listing(listing)
                    listing.score, _ = score_listing(listing)
                fresh.sort(key=lambda pair: pair[0].score or 0.0, reverse=True)
                if adviser_enabled():
                    taste = format_taste_for_adviser(store.taste_summary())
                    for listing, _ in fresh[:ADVISE_TOP_N]:
                        stats = store.area_stats(bucket_for(listing))
                        listing.adviser = await advise(listing, stats, taste)
                for listing, _ in fresh:  # persist the knowledge (score/valuation/adviser)
                    store.save_evaluation(listing, bucket_for(listing))
                if notify_results:
                    notifier = TelegramNotifier()
                    sent = await notifier.send_digest(fresh, client)
                    # Top-N as individual cards with 👍/👎 buttons so the family can react
                    # per listing (tap, or reply with text/voice — the agentMode gate).
                    cards = await notifier.send_cards(fresh, client, ADVISE_TOP_N)
                    log.info(
                        "telegram digest sent=%d cards=%d listings=%d", sent, cards, len(fresh)
                    )
        return fresh
    finally:
        store.close()
