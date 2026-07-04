"""Pure geo helpers: distance, response parsing, normalization (no I/O, unit-testable)."""
from __future__ import annotations

import math
from typing import Optional


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def parse_overpass_amenities(data: dict) -> list[dict]:
    """Extract {name, lat, lon, kind} points from an Overpass JSON response."""
    points: list[dict] = []
    for element in data.get("elements", []):
        lat = element.get("lat")
        lon = element.get("lon")
        if lat is None or lon is None:
            center = element.get("center") or {}
            lat, lon = center.get("lat"), center.get("lon")
        if lat is None or lon is None:
            continue
        tags = element.get("tags", {})
        points.append(
            {"name": tags.get("name", "?"), "lat": lat, "lon": lon, "kind": tags.get("amenity", "")}
        )
    return points


def nearest(lat: float, lon: float, points: list[dict]) -> Optional[tuple[dict, float]]:
    """Return (point, km) for the closest point, or None if the list is empty."""
    best: Optional[tuple[dict, float]] = None
    for point in points:
        dist = haversine_km(lat, lon, point["lat"], point["lon"])
        if best is None or dist < best[1]:
            best = (point, dist)
    return best


def parse_ors_matrix_minutes(data: dict) -> Optional[float]:
    """First origin→first destination duration (minutes) from an ORS matrix response."""
    durations = data.get("durations")
    if not durations or not durations[0] or durations[0][0] is None:
        return None
    return round(durations[0][0] / 60.0, 1)


def proximity_score(km: Optional[float], near: float = 0.3, far: float = 2.0) -> float:
    """Map a distance to a 0..1 'closeness' score (1 = at/under `near`, 0 = at/over `far`)."""
    if km is None:
        return 0.5
    if km <= near:
        return 1.0
    if km >= far:
        return 0.0
    return 1.0 - (km - near) / (far - near)
