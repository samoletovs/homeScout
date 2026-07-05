"""Pure parsers: raw feed payloads -> Listing objects (no I/O, unit-testable)."""
from __future__ import annotations

import html
import logging
import re
import xml.etree.ElementTree as ET
from typing import Optional

from models import Listing

log = logging.getLogger("homescout.parsers")


def _field(html_text: str, label: str) -> Optional[str]:
    """Extract the value after 'Label:' that sits inside one or more <b> tags."""
    match = re.search(re.escape(label) + r":\s*(?:<b>)+\s*([^<]+)", html_text)
    return match.group(1).strip() if match else None


def _num(text: Optional[str]) -> Optional[float]:
    """Parse a number, treating commas as thousands separators (e.g. '450,000')."""
    if not text:
        return None
    cleaned = text.replace("\xa0", " ").replace(",", "").replace(" ", "")
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    return float(match.group(0)) if match else None


def _sslv_id(link: str) -> str:
    """Compact, stable id from an ss.lv listing URL (its unique message slug).

    ss.lv URLs look like '.../marupe/epjdd.html' — the 'epjdd' stem is the site-wide
    unique ad id. Using it (not the full URL) keeps the store key and Telegram button
    callback_data (max 64 bytes) short.
    """
    slug = link.rstrip("/").rsplit("/", 1)[-1].split("?")[0]
    if slug.endswith(".html"):
        slug = slug[:-5]
    return slug or link


def parse_sslv(xml_text: str, area_hint: str = "", property_type: str = "apartment") -> list[Listing]:
    """Parse an ss.lv real-estate RSS feed into sale Listings (rentals skipped)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        log.exception("ss.lv RSS parse error (%s)", area_hint)
        return []

    listings: list[Listing] = []
    for item in root.iter("item"):
        link = (item.findtext("link") or "").strip()
        desc = item.findtext("description") or ""
        if not link or not desc:
            continue
        if "€/mēn" in desc or "/mēn" in desc:
            continue  # rental — we only want sales
        price = _num(_field(desc, "Cena"))
        if not price or price <= 0:
            continue
        rooms = _num(_field(desc, "Ist."))
        listings.append(
            Listing(
                id=_sslv_id(link),
                source="ss.lv",
                url=link,
                title=html.unescape((item.findtext("title") or "").strip())[:120],
                price=price,
                area_m2=_num(_field(desc, "m²")),
                rooms=int(rooms) if rooms else None,
                floor=_field(desc, "Stāvs"),
                district=_field(desc, "Pagasts") or area_hint,
                description=area_hint,
                property_type=property_type,
            )
        )
    return listings


def parse_city24(objs: list[dict], target_areas: Optional[set[str]] = None) -> list[Listing]:
    """Parse city24 JSON objects into Listings, optionally filtered to target areas."""
    listings: list[Listing] = []
    for obj in objs:
        try:
            addr = obj.get("address") or {}
            names = {
                addr.get(key)
                for key in ("city_name", "district_name", "county_name", "parish_name", "village_name")
            }
            names.discard(None)
            if target_areas and not (names & target_areas):
                continue

            price = _num(str(obj.get("price"))) if obj.get("price") is not None else None
            if not price:
                continue

            attrs = obj.get("attributes") or {}
            energy = None
            cert = attrs.get("ENERGY_CERTIFICATE_TYPE")
            if isinstance(cert, list) and cert:
                energy = cert[0]
            floor = None
            if attrs.get("FLOOR") is not None:
                total = attrs.get("TOTAL_FLOORS")
                floor = f"{attrs['FLOOR']}/{total}" if total is not None else str(attrs["FLOOR"])

            size = obj.get("property_size")
            rooms = obj.get("room_count")
            district = addr.get("district_name") or addr.get("city_name") or addr.get("county_name")
            friendly = obj.get("friendly_id") or obj.get("id")
            listings.append(
                Listing(
                    id=str(obj.get("id")),
                    source="city24",
                    url=f"https://www.city24.lv/real-estate/{friendly}",
                    title=f"{district or ''}, {rooms or '?'}-r., {size or '?'} m²".strip(", "),
                    price=price,
                    area_m2=float(size) if size else None,
                    rooms=int(rooms) if rooms else None,
                    floor=floor,
                    district=district,
                    description=addr.get("city_name") or addr.get("county_name") or "",
                    lat=obj.get("latitude"),
                    lon=obj.get("longitude"),
                    energy_class=energy,
                    property_type="apartment",
                )
            )
        except Exception:
            log.exception("city24 parse error (id=%s)", obj.get("id"))
    return listings
