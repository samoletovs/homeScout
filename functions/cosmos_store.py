"""Cosmos DB implementation of the store interface — durable cloud state.

Mirrors the method surface of `store.Store` (SQLite) so the pipeline and feedback endpoint
use them interchangeably via `store.open_store()`. Selected when `COSMOS_ENDPOINT` is set;
otherwise SQLite is used (local dev + tests). Serverless Functions disks aren't persistent,
so this is what makes homeScout's seen-state + learned family feedback survive in the cloud.

Auth: DefaultAzureCredential on Azure (Cosmos DB Built-in Data Contributor role), or
COSMOS_KEY against the local emulator. Containers are provisioned by Bicep in production
(the runtime identity only does data-plane ops); the emulator path creates them on demand.

Data model (database `homescout`, shared throughput):
  - listings  (pk /key)          one doc per listing; key = "source:id"; price history embedded
  - feedback  (pk /listing_key)  one doc per reaction; area denormalised for taste queries
  - geocache  (pk /id)           geocode cache; id = sha1(query)
"""
from __future__ import annotations

import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from models import Listing

log = logging.getLogger("homescout.cosmos")

_DB_NAME = os.getenv("COSMOS_DATABASE", "homescout")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _geo_id(query: str) -> str:
    """Stable, id-safe key for a geocode query (query text can contain '/', '#', etc.)."""
    return hashlib.sha1(query.encode("utf-8")).hexdigest()


def _is_emulator(endpoint: str) -> bool:
    return "localhost" in endpoint or "127.0.0.1" in endpoint


class CosmosStore:
    """Durable store backed by Azure Cosmos DB (NoSQL). Same interface as `store.Store`."""

    def __init__(self, endpoint: Optional[str] = None) -> None:
        from azure.cosmos import CosmosClient, PartitionKey

        endpoint = endpoint or os.environ["COSMOS_ENDPOINT"]
        if _is_emulator(endpoint):
            client = CosmosClient(endpoint, credential=os.environ["COSMOS_KEY"], connection_verify=False)
            db = client.create_database_if_not_exists(_DB_NAME)
            self._listings = db.create_container_if_not_exists("listings", PartitionKey(path="/key"))
            self._feedback = db.create_container_if_not_exists("feedback", PartitionKey(path="/listing_key"))
            self._geo = db.create_container_if_not_exists("geocache", PartitionKey(path="/id"))
        else:
            from azure.identity import DefaultAzureCredential

            client = CosmosClient(endpoint, credential=DefaultAzureCredential())
            db = client.get_database_client(_DB_NAME)  # containers provisioned by Bicep
            self._listings = db.get_container_client("listings")
            self._feedback = db.get_container_client("feedback")
            self._geo = db.get_container_client("geocache")

    def close(self) -> None:  # symmetry with SQLite Store; nothing to release
        pass

    # ── seen-state ──────────────────────────────────────────────────────
    def is_empty(self) -> bool:
        rows = list(self._listings.query_items(query="SELECT VALUE COUNT(1) FROM c"))
        return (rows[0] if rows else 0) == 0

    def filter_new(self, listings: list[Listing]) -> list[tuple[Listing, str]]:
        """Persist all listings; return (listing, reason) for new or price-dropped ones."""
        from azure.cosmos import exceptions

        fresh: list[tuple[Listing, str]] = []
        now = _now()
        for lst in listings:
            key = f"{lst.source}:{lst.id}"
            try:
                doc = self._listings.read_item(item=key, partition_key=key)
            except exceptions.CosmosResourceNotFoundError:
                doc = None
            if doc is None:
                self._listings.upsert_item({
                    "id": key, "key": key, "source": lst.source, "url": lst.url,
                    "district": lst.district, "price": lst.price, "area_m2": lst.area_m2,
                    "rooms": lst.rooms, "first_seen": now, "last_seen": now,
                    "prices": [{"price": lst.price, "seen": now}],
                })
                fresh.append((lst, "new"))
            else:
                old_price = doc.get("price")
                doc["last_seen"] = now
                doc["price"] = lst.price
                dropped = (
                    lst.price is not None and old_price is not None and lst.price < old_price
                )
                if dropped:
                    doc.setdefault("prices", []).append({"price": lst.price, "seen": now})
                self._listings.replace_item(item=key, body=doc)
                if dropped:
                    fresh.append((lst, "price_drop"))
        return fresh

    # ── geocode cache ───────────────────────────────────────────────────
    def get_geo(self, query: str) -> Optional[tuple[float, float]]:
        from azure.cosmos import exceptions

        gid = _geo_id(query)
        try:
            doc = self._geo.read_item(item=gid, partition_key=gid)
            return (doc["lat"], doc["lon"])
        except exceptions.CosmosResourceNotFoundError:
            return None

    def put_geo(self, query: str, lat: float, lon: float) -> None:
        gid = _geo_id(query)
        self._geo.upsert_item({"id": gid, "q": query, "lat": lat, "lon": lon})

    # ── knowledge (evaluations) ─────────────────────────────────────────
    def save_evaluation(self, listing: Listing, bucket: Optional[str] = None) -> None:
        from azure.cosmos import exceptions

        key = f"{listing.source}:{listing.id}"
        try:
            doc = self._listings.read_item(item=key, partition_key=key)
        except exceptions.CosmosResourceNotFoundError:
            return
        doc.update({
            "score": listing.score, "valuation": listing.valuation, "adviser": listing.adviser,
            "bucket": bucket, "ppm2": listing.price_per_m2, "features": listing.features,
        })
        self._listings.replace_item(item=key, body=doc)

    def area_stats(self, bucket: Optional[str]) -> dict:
        if not bucket:
            return {"count": 0, "avg_ppm2": None}
        rows = list(self._listings.query_items(
            query="SELECT VALUE c.ppm2 FROM c WHERE c.bucket=@b AND IS_DEFINED(c.ppm2) AND c.ppm2 != null",
            parameters=[{"name": "@b", "value": bucket}],
        ))
        vals = [r for r in rows if r is not None]
        return {"count": len(vals), "avg_ppm2": round(sum(vals) / len(vals), 1) if vals else None}

    # ── feedback / learning loop ────────────────────────────────────────
    def key_for(self, ref: str) -> Optional[str]:
        from azure.cosmos import exceptions

        try:
            self._listings.read_item(item=ref, partition_key=ref)
            return ref
        except exceptions.CosmosResourceNotFoundError:
            pass
        rows = list(self._listings.query_items(
            query="SELECT c.key FROM c WHERE c.url=@u",
            parameters=[{"name": "@u", "value": ref}],
        ))
        return rows[0]["key"] if rows else None

    def add_feedback(self, listing_key: str, member: str, sentiment: int, comment: Optional[str]) -> None:
        from azure.cosmos import exceptions

        bucket = district = None
        try:
            doc = self._listings.read_item(item=listing_key, partition_key=listing_key)
            bucket, district = doc.get("bucket"), doc.get("district")
        except exceptions.CosmosResourceNotFoundError:
            pass
        self._feedback.upsert_item({
            "id": str(uuid.uuid4()), "listing_key": listing_key, "member": member,
            "sentiment": sentiment, "comment": comment, "created": _now(),
            "bucket": bucket, "district": district,
        })

    def feedback_for(self, listing_key: str) -> list[dict]:
        rows = list(self._feedback.query_items(
            query="SELECT c.member, c.sentiment, c.comment, c.created FROM c WHERE c.listing_key=@k",
            parameters=[{"name": "@k", "value": listing_key}], partition_key=listing_key,
        ))
        return [
            {"member": r["member"], "sentiment": r["sentiment"],
             "comment": r.get("comment"), "created": r["created"]}
            for r in rows
        ]

    def taste_summary(self, recent: int = 6) -> dict:
        rows = list(self._feedback.query_items(
            query="SELECT c.sentiment, c.comment, c.bucket, c.district, c.created FROM c"
        ))
        rows.sort(key=lambda r: r.get("created", ""), reverse=True)
        liked = sum(1 for r in rows if (r.get("sentiment") or 0) > 0)
        disliked = sum(1 for r in rows if (r.get("sentiment") or 0) < 0)
        by_area: dict = {}
        for r in rows:
            area = r.get("bucket") or r.get("district") or "?"
            counts = by_area.setdefault(area, {"like": 0, "dislike": 0})
            sentiment = r.get("sentiment") or 0
            if sentiment > 0:
                counts["like"] += 1
            elif sentiment < 0:
                counts["dislike"] += 1
        recent_notes = [
            {"sentiment": r.get("sentiment"), "comment": r.get("comment"),
             "area": r.get("bucket") or r.get("district") or "?"}
            for r in rows if r.get("comment")
        ][:recent]
        return {"liked": liked, "disliked": disliked, "by_area": by_area, "recent": recent_notes}
