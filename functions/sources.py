"""Source adapters — fetch raw payloads and delegate to pure parsers.

Phase 1 (active): ss.lv RSS + city24 JSON. Later-phase sources are stubbed below.
Prefer structured feeds over HTML scraping.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from config import CITY24_TARGET_AREAS, CITY24_URL, SSLV_FEEDS
from models import Deal, Listing
from parsers import parse_city24, parse_sslv

if TYPE_CHECKING:
    import httpx

log = logging.getLogger("homescout.sources")


async def fetch_sslv(client: "httpx.AsyncClient") -> list[Listing]:
    listings: list[Listing] = []
    for url, area, kind in SSLV_FEEDS:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            items = parse_sslv(resp.text, area, kind)
            if items:
                log.info("ss.lv %s: %d sale listings", area, len(items))
            else:
                log.warning("ss.lv %s: 0 sale listings (feed layout changed?)", area)
            listings.extend(items)
        except Exception:
            log.exception("ss.lv fetch failed: %s", url)
    return listings


async def fetch_city24() -> list[Listing]:
    """Fetch city24 via curl_cffi (browser-TLS impersonation) — its API is Cloudflare-fronted."""
    try:
        from curl_cffi.requests import AsyncSession
    except ImportError:
        log.warning("curl_cffi not installed — city24 skipped (Cloudflare TLS check)")
        return []
    try:
        async with AsyncSession() as session:
            resp = await session.get(CITY24_URL, impersonate="chrome", timeout=25)
        if resp.status_code != 200:
            log.warning("city24 returned HTTP %s", resp.status_code)
            return []
        data = resp.json()
        items = parse_city24(data, CITY24_TARGET_AREAS)
        log.info("city24: %d listings in target areas (of %d)", len(items), len(data))
        return items
    except Exception:
        log.exception("city24 fetch failed")
        return []


async def fetch_all(client: "httpx.AsyncClient") -> list[Listing]:
    ss, c24 = await asyncio.gather(fetch_sslv(client), fetch_city24())
    return [*ss, *c24]


# ── Later-phase stubs (kept for the roadmap) ─────────────────────────────
class IzsolesAuctions:
    """izsoles.ta.gov.lv — no API; scrape filtered HTML (Phase 5). Sets is_auction=True."""

    name = "izsoles"

    def fetch_new(self) -> list[Listing]:
        log.info("TODO(Phase 5): scrape izsoles auctions")
        return []


class VzdNitisDeals:
    """VZD NĪTIS sold deals — data.gov.lv CKAN (Phase 3 valuation layer)."""

    name = "vzd-nitis"

    def fetch_deals(self) -> list[Deal]:
        log.info("TODO(Phase 3): download NĪTIS deals")
        return []
