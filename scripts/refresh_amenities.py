"""Refresh the committed schools/kindergartens dataset from OpenStreetMap (ODbL).

Run occasionally to update functions/assets/lv_amenities.json. Uses an Overpass mirror
via curl_cffi (browser impersonation) and a greater-Rīga bounding box covering Rīga,
Jūrmala and Mārupe.

Usage:  python scripts/refresh_amenities.py
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "functions"))

from geo import parse_overpass_amenities  # noqa: E402

BBOX = "56.8,23.5,57.1,24.4"  # greater Rīga: Rīga + Jūrmala + Mārupe
OVERPASS_MIRRORS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "functions", "assets", "lv_amenities.json")

QUERY = f"""[out:json][timeout:120];
(
 node[amenity=school]({BBOX});
 way[amenity=school]({BBOX});
 node[amenity=kindergarten]({BBOX});
 way[amenity=kindergarten]({BBOX});
);
out center;"""


async def main() -> None:
    from curl_cffi.requests import AsyncSession

    data = None
    for url in OVERPASS_MIRRORS:
        try:
            async with AsyncSession() as session:
                resp = await session.get(url, params={"data": QUERY}, impersonate="chrome", timeout=120)
            if resp.status_code == 200:
                data = resp.json()
                print(f"fetched from {url}")
                break
            print(f"{url} -> HTTP {resp.status_code}")
        except Exception as exc:  # noqa: BLE001
            print(f"{url} failed: {exc}")
    if data is None:
        raise SystemExit("all Overpass mirrors failed")

    points = parse_overpass_amenities(data)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as handle:
        json.dump(points, handle, ensure_ascii=False)
    kinds: dict = {}
    for point in points:
        kinds[point["kind"]] = kinds.get(point["kind"], 0) + 1
    print(f"saved {len(points)} points {kinds} -> {OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
