"""Pipeline: ingest → dedupe → store(seen) → alert.

Phase 1 (MVP): new-listing + price-drop Telegram alerts, deduped across sources and
across runs. Enrichment / valuation / scoring arrive in later phases.
"""
from __future__ import annotations

import logging

import httpx

from config import DB_PATH, ENRICH_CAP, USER_AGENT
from enrich import enrich_all
from models import Listing
from notify import TelegramNotifier
from scoring import HardFilters, passes_hard_filters
from sources import fetch_all
from store import Store

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
                await enrich_all([lst for lst, _ in fresh], client, store, cap=ENRICH_CAP)
                if notify_results:
                    sent = await TelegramNotifier().send_all(fresh, client)
                    log.info("telegram: sent %d/%d", sent, len(fresh))
        return fresh
    finally:
        store.close()
