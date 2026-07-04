"""Enrichers — geocode (Nominatim), nearby schools/kindergartens (local OSM dataset), commute (ORS).

Each enricher is resilient: on any failure it logs and leaves the field unset, so the
pipeline still alerts on the listing. Geocoding is cached in the store and throttled to
respect Nominatim's ~1 req/sec policy. School/kindergarten distances use a committed OSM
dataset (functions/assets/lv_amenities.json) — no runtime Overpass dependency.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import TYPE_CHECKING, Optional

from config import COMMUTE_DEST, NOMINATIM_URL, ORS_API_KEY, ORS_MATRIX_URL, USER_AGENT
from geo import nearest, parse_ors_matrix_minutes, proximity_score
from models import Listing

if TYPE_CHECKING:
    import httpx

    from store import Store

log = logging.getLogger("homescout.enrich")

_AMENITIES_PATH = os.path.join(os.path.dirname(__file__), "assets", "lv_amenities.json")
_amenities_cache: Optional[list[dict]] = None


def _amenities() -> list[dict]:
    """Load and cache the committed schools/kindergartens dataset (OSM, ODbL)."""
    global _amenities_cache
    if _amenities_cache is None:
        try:
            with open(_AMENITIES_PATH, encoding="utf-8") as handle:
                _amenities_cache = json.load(handle)
        except FileNotFoundError:
            log.warning("amenities dataset missing: %s", _AMENITIES_PATH)
            _amenities_cache = []
    return _amenities_cache


def nearby(kind: str) -> list[dict]:
    """Amenities of a given kind ('school'/'kindergarten') from the local OSM dataset."""
    return [point for point in _amenities() if point.get("kind") == kind]


async def geocode(query: str, client: "httpx.AsyncClient", store: "Store") -> Optional[tuple[float, float]]:
    cached = store.get_geo(query)
    if cached is not None:
        return cached
    try:
        resp = await client.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "lv"},
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
        results = resp.json()
        await asyncio.sleep(1.0)  # Nominatim usage policy: <= 1 req/sec
        if not results:
            return None
        lat, lon = float(results[0]["lat"]), float(results[0]["lon"])
        store.put_geo(query, lat, lon)
        return lat, lon
    except Exception:
        log.exception("geocode failed: %s", query)
        return None


async def commute_minutes(lat: float, lon: float, client: "httpx.AsyncClient") -> Optional[float]:
    if not ORS_API_KEY:
        return None
    try:
        resp = await client.post(
            ORS_MATRIX_URL,
            headers={"Authorization": ORS_API_KEY, "Content-Type": "application/json"},
            json={
                "locations": [[lon, lat], [COMMUTE_DEST[1], COMMUTE_DEST[0]]],
                "sources": [0],
                "destinations": [1],
                "metrics": ["duration"],
            },
        )
        resp.raise_for_status()
        return parse_ors_matrix_minutes(resp.json())
    except Exception:
        log.exception("ORS commute failed")
        return None


async def enrich_listing(listing: Listing, client: "httpx.AsyncClient", store: "Store") -> Listing:
    """Attach coordinates, nearest school/kindergarten, and commute time to a listing."""
    # city24 carries coordinates; ss.lv needs geocoding (district + area hint).
    if listing.lat is None or listing.lon is None:
        parts: list[str] = []
        for part in (listing.district, listing.description):
            if part and part not in parts:
                parts.append(part)
        parts.append("Latvija")
        coords = await geocode(", ".join(parts), client, store)
        if coords:
            listing.lat, listing.lon = coords
    if listing.lat is None or listing.lon is None:
        return listing

    schools = nearby("school")
    kindergartens = nearby("kindergarten")
    nearest_school = nearest(listing.lat, listing.lon, schools)
    nearest_kg = nearest(listing.lat, listing.lon, kindergartens)
    if nearest_school:
        listing.nearest_school_km = round(nearest_school[1], 2)
    if nearest_kg:
        listing.nearest_kindergarten_km = round(nearest_kg[1], 2)
    distances = [d for d in (listing.nearest_school_km, listing.nearest_kindergarten_km) if d is not None]
    listing.features["schools"] = proximity_score(min(distances) if distances else None)

    minutes = await commute_minutes(listing.lat, listing.lon, client)
    if minutes is not None:
        listing.commute_min = minutes
        listing.features["commute"] = minutes

    if listing.price_per_m2:
        listing.features["price_per_m2"] = listing.price_per_m2
    if listing.area_m2:
        listing.features["size"] = listing.area_m2
    return listing


async def enrich_all(
    listings: list[Listing], client: "httpx.AsyncClient", store: "Store", cap: int = 15
) -> None:
    """Enrich up to `cap` listings in place (sequential, to respect rate limits)."""
    for listing in listings[:cap]:
        await enrich_listing(listing, client, store)
