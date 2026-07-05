"""Telegram notifier + message formatting."""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Optional

from models import Listing

if TYPE_CHECKING:
    import httpx

log = logging.getLogger("homescout.notify")

_AREA_EMOJI = {"Rīga": "🏙️", "Jūrmala": "🏖️", "Mārupe": "🏡"}


def format_listing(listing: Listing, reason: str = "new") -> str:
    """Render a listing as a Telegram message body."""
    tag = "🆕 New listing" if reason == "new" else "📉 Price drop"
    emoji = _AREA_EMOJI.get(listing.district or "", "📍")
    header = f"{tag} — {emoji} {listing.district or '?'}"
    if listing.score is not None:
        header = f"⭐ {listing.score:.2f}  ·  {header}"
    lines = [header]
    if listing.title:
        lines.append(listing.title)
    price = f"€{listing.price:,.0f}" if listing.price else "n/a"
    ppm2 = listing.price_per_m2
    lines.append(f"💶 {price}" + (f"  ·  {ppm2:,.0f} €/m²" if ppm2 else ""))
    if listing.valuation:
        mark = "🟢" if listing.valuation.startswith("under") else "🔴" if listing.valuation.startswith("over") else "⚪"
        lines.append(f"{mark} {listing.valuation}")
    facts = []
    if listing.rooms:
        facts.append(f"{listing.rooms} rooms")
    if listing.area_m2:
        facts.append(f"{listing.area_m2:g} m²")
    if listing.floor:
        facts.append(f"floor {listing.floor}")
    if listing.energy_class:
        facts.append(f"energy {listing.energy_class}")
    if listing.commute_min:
        facts.append(f"~{listing.commute_min:g} min to centre")
    if listing.nearest_school_km is not None:
        facts.append(f"school {listing.nearest_school_km:g} km")
    if listing.nearest_kindergarten_km is not None:
        facts.append(f"kindergarten {listing.nearest_kindergarten_km:g} km")
    if listing.flood_risk:
        facts.append("⚠️ flood zone")
    if facts:
        lines.append("  ·  ".join(facts))
    lines.append(f"🔗 {listing.url}")
    lines.append(f"({listing.source})")
    return "\n".join(lines)


class TelegramNotifier:
    """Sends alert messages to a Telegram chat. No-ops (logs) if unconfigured."""

    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None) -> None:
        self.token = token if token is not None else os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id if chat_id is not None else os.getenv("TELEGRAM_CHAT_ID")

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    async def send_all(
        self, items: list[tuple[Listing, str]], client: "httpx.AsyncClient", cap: int = 12
    ) -> int:
        """Send up to `cap` alerts. Returns the number actually sent."""
        if not self.enabled:
            log.warning("Telegram not configured — %d alert(s) would be sent", len(items))
            for listing, reason in items[:cap]:
                log.info("ALERT: %s", format_listing(listing, reason).replace("\n", " | "))
            return 0
        sent = 0
        for listing, reason in items[:cap]:
            try:
                resp = await client.post(
                    f"https://api.telegram.org/bot{self.token}/sendMessage",
                    json={"chat_id": self.chat_id, "text": format_listing(listing, reason)},
                )
                resp.raise_for_status()
                sent += 1
            except Exception:
                log.exception("telegram send failed")
        if len(items) > cap:
            log.info("%d further alert(s) suppressed this run", len(items) - cap)
        return sent
