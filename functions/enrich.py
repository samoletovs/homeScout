"""Enrichers — geocode, nearby amenities, school results, and commute estimates.

Each enricher is resilient: on any failure it logs and leaves the field unset, so the
pipeline still alerts on the listing. Geocoding is cached in the store and throttled to
respect Nominatim's ~1 req/sec policy. School/kindergarten distances use a committed OSM
dataset, school results come from Latvia's open-data catalog, and commute uses ORS with OSRM
as a fallback.
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import math
import os
import unicodedata
from typing import TYPE_CHECKING, Optional
from urllib.parse import urlparse

from config import (
    COMMUTE_DEST,
    NOMINATIM_URL,
    ORS_API_KEY,
    ORS_MATRIX_URL,
    OSRM_ROUTE_URL,
    SCHOOL_RESULTS_DATASET_URL,
    USER_AGENT,
)
from geo import nearest, parse_ors_matrix_minutes, proximity_score
from models import Listing

if TYPE_CHECKING:
    import httpx

    from store import Store

log = logging.getLogger("homescout.enrich")

_AMENITIES_PATH = os.path.join(os.path.dirname(__file__), "assets", "lv_amenities.json")
_amenities_cache: Optional[list[dict]] = None
_school_ratings_cache: Optional[dict[str, float]] = None


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
    if ORS_API_KEY:
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
            minutes = parse_ors_matrix_minutes(resp.json())
            if minutes is not None:
                return minutes
        except Exception:
            log.exception("ORS commute failed")

    try:
        resp = await client.get(
            f"{OSRM_ROUTE_URL.rstrip('/')}/route/v1/driving/"
            f"{lon},{lat};{COMMUTE_DEST[1]},{COMMUTE_DEST[0]}",
            params={"overview": "false"},
        )
        resp.raise_for_status()
        routes = resp.json().get("routes")
        if not routes or routes[0].get("duration") is None:
            return None
        seconds = float(routes[0]["duration"])
        if not math.isfinite(seconds) or seconds < 0:
            return None
        return round(seconds / 60.0, 1)
    except Exception:
        log.exception("OSRM commute failed")
        return None


def _school_key(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return "".join(char for char in normalized.casefold() if char.isalnum())


def _parse_school_ratings(contents: str) -> dict[str, float]:
    sample = contents[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = csv.DictReader(io.StringIO(contents.lstrip("\ufeff")), dialect=dialect)
    headers = rows.fieldnames or []
    school_columns = [
        header for header in headers
        if "skola" in _school_key(header)
        or ("izglitibas" in _school_key(header) and "iestade" in _school_key(header))
    ]
    school_column = next(
        (header for header in school_columns if "nosaukum" in _school_key(header)),
        next(
            (header for header in school_columns if not any(term in _school_key(header) for term in ("kods", "id"))),
            None,
        ),
    )
    score_columns = [
        header for header in headers
        if any(term in _school_key(header) for term in ("videj", "rezultat", "kopvertej", "procent"))
        and not any(term in _school_key(header) for term in ("skaits", "dalib", "limenis"))
    ]
    if school_column is None or not score_columns:
        return {}
    score_columns.sort(
        key=lambda header: 0 if any(term in _school_key(header) for term in ("videj", "kopvertej")) else 1
    )

    school_scores: dict[str, list[float]] = {}
    for row in rows:
        school = (row.get(school_column) or "").strip()
        if not school:
            continue
        for column in score_columns:
            raw_score = (row.get(column) or "").strip().replace("%", "").replace(",", ".")
            try:
                score = float(raw_score)
            except ValueError:
                continue
            if 0 <= score <= 100:
                school_scores.setdefault(_school_key(school), []).append(score)
                break
    return {
        school: round(sum(scores) / len(scores), 1)
        for school, scores in school_scores.items()
        if school and scores
    }


async def school_ratings(client: "httpx.AsyncClient") -> dict[str, float]:
    """Fetch Latvian school exam results from the CKAN open-data catalog."""
    global _school_ratings_cache
    if _school_ratings_cache is not None:
        return _school_ratings_cache
    try:
        resp = await client.get(SCHOOL_RESULTS_DATASET_URL)
        resp.raise_for_status()
        dataset = resp.json()
        if not dataset.get("success"):
            raise ValueError("school results dataset lookup failed")
        resources = [
            resource for resource in dataset.get("result", {}).get("resources", [])
            if (
                str(resource.get("format", "")).casefold() == "csv"
                or str(resource.get("url", "")).casefold().split("?")[0].endswith(".csv")
            )
            and urlparse(str(resource.get("url", ""))).scheme == "https"
            and urlparse(str(resource.get("url", ""))).hostname == "data.gov.lv"
        ]
        if not resources:
            raise ValueError("school results dataset has no CSV resource")
        resource = max(resources, key=lambda item: item.get("last_modified") or item.get("created") or "")
        data_resp = await client.get(resource["url"])
        data_resp.raise_for_status()
        _school_ratings_cache = _parse_school_ratings(data_resp.text)
        return _school_ratings_cache
    except Exception:
        log.exception("school ratings fetch failed")
        return {}


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
    distances = [
        d for d in (listing.nearest_school_km, listing.nearest_kindergarten_km)
        if d is not None
    ]
    listing.features["schools"] = proximity_score(min(distances) if distances else None)
    if nearest_school:
        ratings = await school_ratings(client)
        rating = ratings.get(_school_key(str(nearest_school[0].get("name", ""))))
        if rating is not None:
            listing.features["school_rating"] = rating

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
