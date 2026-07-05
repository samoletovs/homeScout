"""SQLite dedup / seen-state store (stdlib sqlite3)."""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from models import Listing

log = logging.getLogger("homescout.store")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
  key TEXT PRIMARY KEY, source TEXT, url TEXT, district TEXT,
  price REAL, area_m2 REAL, rooms INTEGER, first_seen TEXT, last_seen TEXT,
  score REAL, valuation TEXT, adviser TEXT, bucket TEXT, ppm2 REAL, features TEXT
);
CREATE TABLE IF NOT EXISTS price_history (key TEXT, price REAL, seen TEXT);
CREATE TABLE IF NOT EXISTS geocache (q TEXT PRIMARY KEY, lat REAL, lon REAL);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    """Tracks which listings have been seen, plus price history for drop detection."""

    def __init__(self, path: str = ":memory:") -> None:
        if path not in (":memory:", ""):
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.executescript(_SCHEMA)
        self._migrate()

    def close(self) -> None:
        self.conn.close()

    def is_empty(self) -> bool:
        return self.conn.execute("SELECT 1 FROM listings LIMIT 1").fetchone() is None

    def get_geo(self, query: str) -> Optional[tuple[float, float]]:
        row = self.conn.execute("SELECT lat, lon FROM geocache WHERE q=?", (query,)).fetchone()
        return (row[0], row[1]) if row else None

    def put_geo(self, query: str, lat: float, lon: float) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO geocache(q, lat, lon) VALUES(?,?,?)", (query, lat, lon)
        )
        self.conn.commit()

    def _migrate(self) -> None:
        existing = {row[1] for row in self.conn.execute("PRAGMA table_info(listings)")}
        for col, col_type in (
            ("score", "REAL"), ("valuation", "TEXT"), ("adviser", "TEXT"),
            ("bucket", "TEXT"), ("ppm2", "REAL"), ("features", "TEXT"),
        ):
            if col not in existing:
                self.conn.execute(f"ALTER TABLE listings ADD COLUMN {col} {col_type}")
        self.conn.commit()

    def save_evaluation(self, listing: Listing, bucket: Optional[str] = None) -> None:
        """Persist a listing's judgment (score/valuation/adviser) — the knowledge layer."""
        self.conn.execute(
            "UPDATE listings SET score=?, valuation=?, adviser=?, bucket=?, ppm2=?, features=? WHERE key=?",
            (
                listing.score, listing.valuation, listing.adviser, bucket, listing.price_per_m2,
                json.dumps(listing.features, ensure_ascii=False),
                f"{listing.source}:{listing.id}",
            ),
        )
        self.conn.commit()

    def area_stats(self, bucket: Optional[str]) -> dict:
        """Accumulated stats for an area bucket — grounds the adviser in what we've seen."""
        if not bucket:
            return {"count": 0, "avg_ppm2": None}
        row = self.conn.execute(
            "SELECT COUNT(*), AVG(ppm2) FROM listings WHERE bucket=? AND ppm2 IS NOT NULL", (bucket,)
        ).fetchone()
        return {"count": row[0] or 0, "avg_ppm2": round(row[1], 1) if row[1] else None}

    def filter_new(self, listings: list[Listing]) -> list[tuple[Listing, str]]:
        """Persist all listings; return (listing, reason) for new or price-dropped ones.

        reason is "new" or "price_drop". Price increases are recorded but not returned.
        """
        fresh: list[tuple[Listing, str]] = []
        now = _now()
        for lst in listings:
            key = f"{lst.source}:{lst.id}"
            row = self.conn.execute("SELECT price FROM listings WHERE key=?", (key,)).fetchone()
            if row is None:
                self.conn.execute(
                    "INSERT INTO listings(key,source,url,district,price,area_m2,rooms,first_seen,last_seen)"
                    " VALUES(?,?,?,?,?,?,?,?,?)",
                    (key, lst.source, lst.url, lst.district, lst.price, lst.area_m2, lst.rooms, now, now),
                )
                self.conn.execute(
                    "INSERT INTO price_history(key,price,seen) VALUES(?,?,?)", (key, lst.price, now)
                )
                fresh.append((lst, "new"))
            else:
                old_price = row[0]
                self.conn.execute(
                    "UPDATE listings SET last_seen=?, price=? WHERE key=?", (now, lst.price, key)
                )
                if lst.price is not None and old_price is not None and lst.price < old_price:
                    self.conn.execute(
                        "INSERT INTO price_history(key,price,seen) VALUES(?,?,?)", (key, lst.price, now)
                    )
                    fresh.append((lst, "price_drop"))
        self.conn.commit()
        return fresh
