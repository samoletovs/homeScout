"""Core data models for homeScout (stdlib dataclasses — no runtime deps)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class Listing:
    """A property listing from any source (ss.lv, city24, developer, auction)."""

    id: str
    source: str
    url: str
    title: str = ""
    price: Optional[float] = None
    area_m2: Optional[float] = None
    rooms: Optional[int] = None
    floor: Optional[str] = None
    district: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    energy_class: Optional[str] = None
    description: str = ""
    is_auction: bool = False
    property_type: str = "apartment"
    # --- enrichment (filled by the pipeline) ---
    commute_min: Optional[float] = None
    flood_risk: bool = False
    nearest_school_km: Optional[float] = None
    nearest_kindergarten_km: Optional[float] = None
    valuation: Optional[str] = None
    features: dict = field(default_factory=dict)
    first_seen: Optional[datetime] = None

    @property
    def price_per_m2(self) -> Optional[float]:
        if self.price and self.area_m2:
            return round(self.price / self.area_m2, 2)
        return None


@dataclass
class Deal:
    """A registered sold-deal comparable from VZD NĪTIS."""

    cadastre: str
    price: float
    area_m2: Optional[float] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    registered: Optional[date] = None

    @property
    def price_per_m2(self) -> Optional[float]:
        if self.price and self.area_m2:
            return round(self.price / self.area_m2, 2)
        return None


@dataclass
class ScoredListing:
    """A listing with its deterministic score, breakdown and valuation verdict."""

    listing: Listing
    score: float
    breakdown: dict = field(default_factory=dict)
    valuation: Optional[str] = None  # "under" | "fair" | "over" | None
