"""Listing/deal source adapters.

Each adapter targets a real Latvian source. Endpoints are documented here from the
mindVault research; the fetch logic is a stub to implement per phase (see AGENTS.md).
Prefer structured feeds (RSS, JSON) over HTML scraping.
"""
from __future__ import annotations

import logging
from typing import Protocol

from models import Deal, Listing

log = logging.getLogger("homescout.sources")


class ListingSource(Protocol):
    name: str

    def fetch_new(self) -> list[Listing]:
        ...


class SsLvRss:
    """ss.lv — RSS per district: {SSLV_RSS_BASE}/{city}/rss/ (ttl=5). Volume leader."""

    name = "ss.lv"

    def fetch_new(self) -> list[Listing]:
        log.info("TODO: parse ss.lv RSS (feedparser) -> Listing[]")
        return []


class City24Api:
    """city24.lv — JSON: {CITY24_API_BASE}/search/realties?tsType=sale&unitType=Apartment.

    Richest source: already includes lat/long and energy class.
    """

    name = "city24"

    def fetch_new(self) -> list[Listing]:
        log.info("TODO: call city24 JSON API -> Listing[]")
        return []


class IzsolesAuctions:
    """izsoles.ta.gov.lv — no API; scrape filtered HTML. Set Listing.is_auction=True.

    Apply the due-diligence checklist before alerting (title / debts / occupancy / cash).
    """

    name = "izsoles"

    def fetch_new(self) -> list[Listing]:
        log.info("TODO: scrape izsoles real-estate auctions -> Listing[](is_auction=True)")
        return []


class VzdNitisDeals:
    """VZD NĪTIS registered sold deals — data.gov.lv CKAN dataset {VZD_NITIS_DATASET}.

    The valuation layer: comparables for €/m² over/under-priced checks.
    """

    name = "vzd-nitis"

    def fetch_deals(self) -> list[Deal]:
        log.info("TODO: download NĪTIS CSV/XLSX from data.gov.lv -> Deal[]")
        return []


def default_listing_sources() -> list[ListingSource]:
    return [SsLvRss(), City24Api(), IzsolesAuctions()]
