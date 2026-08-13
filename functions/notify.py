"""Telegram notifier + message formatting."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Optional

from config import COMM_LANGUAGE
from models import Listing

if TYPE_CHECKING:
    import httpx

log = logging.getLogger("homescout.notify")

_AREA_EMOJI = {"rīga": "🏙️", "jūrmala": "🏖️", "mārup": "🏡"}


def _area_emoji(district: Optional[str]) -> str:
    d = (district or "").lower()
    for key, emoji in _AREA_EMOJI.items():
        if key in d:
            return emoji
    return "📍"


def _ru_plural(n: int, one: str, few: str, many: str) -> str:
    nn = abs(n) % 100
    if 11 <= nn <= 14:
        return many
    d = nn % 10
    if d == 1:
        return one
    if 2 <= d <= 4:
        return few
    return many


_TAGS = {
    "ru": {"new": "🆕 Новое", "price_drop": "📉 Снижение цены"},
    "en": {"new": "🆕 New listing", "price_drop": "📉 Price drop"},
}
_VAL_RU = {"under": "ниже рынка", "over": "выше рынка", "fair": "по рынку"}


def _ru_valuation(valuation: str) -> str:
    """Render an English valuation string ('under (…)') in Russian for the card."""
    word, _, rest = valuation.partition(" ")
    return f"{_VAL_RU.get(word, word)} {rest}".replace("median", "медиана").strip()


def format_listing(listing: Listing, reason: str = "new") -> str:
    """Render a listing as a Telegram message body (Russian when COMM_LANGUAGE='ru')."""
    ru = COMM_LANGUAGE == "ru"
    tag = _TAGS.get(COMM_LANGUAGE, _TAGS["en"]).get(reason, reason)
    emoji = _area_emoji(listing.district)
    header = f"{tag} — {emoji} {listing.district or '?'}"
    if listing.score is not None:
        header = f"⭐ {listing.score:.2f}  ·  {header}"
    lines = [header]
    # The Russian adviser take is the human-readable description + judgment; fall back to
    # the raw (often Latvian) seller headline only when no take was generated.
    if listing.adviser:
        lines.append(f"💬 {listing.adviser}")
    elif listing.title:
        lines.append(listing.title)
    price = f"€{listing.price:,.0f}" if listing.price else "n/a"
    ppm2 = listing.price_per_m2
    lines.append(f"💶 {price}" + (f"  ·  {ppm2:,.0f} €/m²" if ppm2 else ""))
    if listing.valuation:
        mark = "🟢" if listing.valuation.startswith("under") else "🔴" if listing.valuation.startswith("over") else "⚪"
        val = _ru_valuation(listing.valuation) if ru else listing.valuation
        lines.append(f"{mark} {val}")
    facts = []
    if listing.rooms:
        facts.append(f"{listing.rooms} комн." if ru else f"{listing.rooms} rooms")
    if listing.area_m2:
        facts.append(f"{listing.area_m2:g} м²" if ru else f"{listing.area_m2:g} m²")
    if listing.floor:
        facts.append(f"этаж {listing.floor}" if ru else f"floor {listing.floor}")
    if listing.energy_class:
        facts.append(f"класс {listing.energy_class}" if ru else f"energy {listing.energy_class}")
    if listing.commute_min:
        facts.append(f"~{listing.commute_min:g} мин до центра" if ru else f"~{listing.commute_min:g} min to centre")
    if listing.nearest_school_km is not None:
        facts.append(f"школа {listing.nearest_school_km:g} км" if ru else f"school {listing.nearest_school_km:g} km")
    if listing.nearest_kindergarten_km is not None:
        facts.append(f"садик {listing.nearest_kindergarten_km:g} км" if ru else f"kindergarten {listing.nearest_kindergarten_km:g} km")
    if listing.flood_risk:
        facts.append("⚠️ зона затопления" if ru else "⚠️ flood zone")
    if facts:
        lines.append("  ·  ".join(facts))
    lines.append(f"🔗 {listing.url}")
    lines.append(f"({listing.source})")
    return "\n".join(lines)


def format_digest(items: list[tuple[Listing, str]], limit: int = 10) -> str:
    """One compact 'daily brief' message with the top-ranked new matches."""
    ranked = sorted(items, key=lambda pair: pair[0].score or 0.0, reverse=True)
    n = len(items)
    if COMM_LANGUAGE == "ru":
        header = f"🏠 homeScout — {n} нов{_ru_plural(n, 'ый вариант', 'ых варианта', 'ых вариантов')}"
    else:
        header = f"🏠 homeScout daily brief — {n} new match{'' if n == 1 else 'es'}"
    blocks = [header]
    for listing, reason in ranked[:limit]:
        star = f"⭐{listing.score:.2f} " if listing.score is not None else ""
        emoji = _area_emoji(listing.district)
        price = f"€{listing.price:,.0f}" if listing.price else "n/a"
        ppm2 = listing.price_per_m2
        facts = []
        if listing.rooms:
            facts.append(f"{listing.rooms}r")
        if listing.area_m2:
            facts.append(f"{listing.area_m2:g}m²")
        if listing.commute_min:
            facts.append(f"~{listing.commute_min:g}min")
        if listing.nearest_school_km is not None:
            facts.append(f"school {listing.nearest_school_km:g}km")
        val = ""
        if listing.valuation:
            mark = "🟢" if listing.valuation.startswith("under") else "🔴" if listing.valuation.startswith("over") else "⚪"
            val = f"  {mark}{listing.valuation.split(' (')[0]}"
        drop = " 📉" if reason == "price_drop" else ""
        block = (
            f"\n{star}{emoji} {listing.district or '?'} · {price}"
            + (f" · {ppm2:,.0f}€/m²" if ppm2 else "")
            + val + drop
            + (f"\n{'  ·  '.join(facts)}" if facts else "")
        )
        if listing.adviser:
            block += f"\n💬 {listing.adviser}"
        block += f"\n{listing.url}"
        blocks.append(block)
    if len(items) > limit:
        extra = len(items) - limit
        blocks.append(f"\n…и ещё {extra}" if COMM_LANGUAGE == "ru" else f"\n…and {extra} more")
    return "\n".join(blocks)


def _listing_key(listing: Listing) -> str:
    """The store key the feedback endpoint resolves (also matches the listing URL)."""
    return f"{listing.source}:{listing.id}"


def feedback_buttons(listing: Listing) -> list[list[dict]]:
    """👍/👎 inline keyboard for a card. Callback 'hs:<sentiment>:<key>' → agentMode gate."""
    key = _listing_key(listing)
    like, dislike = ("👍 Нравится", "👎 Не то") if COMM_LANGUAGE == "ru" else ("👍 Like", "👎 Not it")
    return [[
        {"text": like, "callback_data": f"hs:1:{key}"},
        {"text": dislike, "callback_data": f"hs:-1:{key}"},
    ]]


class TelegramError(RuntimeError):
    """A Telegram call failed, described without the token-bearing URL."""


class TelegramNotifier:
    """Sends alert messages to a Telegram chat. No-ops (logs) if unconfigured."""

    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None) -> None:
        self.token = token if token is not None else os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id if chat_id is not None else os.getenv("TELEGRAM_CHAT_ID")

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    async def _send(self, client: "httpx.AsyncClient", payload: dict) -> None:
        """POST sendMessage, raising an error that cannot carry the token.

        httpx repeats the request URL in its exception text and the bot token sits in that
        path, so logging the raw error wrote the live credential into Application Insights.
        The error is raised outside the handler so no __context__ chain back to the httpx
        exception is recorded either - `raise ... from None` would leave that reachable.
        """
        import httpx  # local: keeps the module importable where httpx is absent

        detail: object = None
        try:
            resp = await client.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage", json=payload
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            detail = status if status is not None else type(exc).__name__
        if detail is not None:
            raise TelegramError(f"sendMessage failed: {detail}")

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
                await self._send(
                    client,
                    {"chat_id": self.chat_id, "text": format_listing(listing, reason)},
                )
                sent += 1
            except Exception:
                log.exception("telegram send failed")
        if len(items) > cap:
            log.info("%d further alert(s) suppressed this run", len(items) - cap)
        return sent

    async def send_digest(
        self, items: list[tuple[Listing, str]], client: "httpx.AsyncClient", limit: int = 10
    ) -> int:
        """Send one 'daily brief' digest with the top-ranked matches. Returns 1 if sent."""
        if not items:
            return 0
        text = format_digest(items, limit)
        if not self.enabled:
            log.warning("Telegram not configured — daily brief of %d would be sent", len(items))
            log.info("DIGEST: %s", text.replace("\n", " | "))
            return 0
        try:
            await self._send(
                client,
                {"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True},
            )
            return 1
        except Exception:
            log.exception("telegram digest send failed")
            return 0

    async def send_cards(
        self, items: list[tuple[Listing, str]], client: "httpx.AsyncClient", top_n: int = 5,
        pause_s: float = 1.1,
    ) -> int:
        """Send the top-N listings as individual cards with 👍/👎 buttons.

        Each card is one listing, so a family member can react to exactly that property —
        tap a button, or reply to the card with text/voice (handled by the agentMode gate).
        Returns the number of cards sent.
        """
        ranked = sorted(items, key=lambda pair: pair[0].score or 0.0, reverse=True)[:top_n]
        if not ranked:
            return 0
        if not self.enabled:
            log.info("Telegram not configured — %d card(s) would be sent", len(ranked))
            return 0
        sent = 0
        for listing, reason in ranked:
            # Telegram throttles bursts to one chat (~1 msg/s) — pace the cards.
            await asyncio.sleep(pause_s)
            try:
                await self._send(
                    client,
                    {
                        "chat_id": self.chat_id,
                        "text": format_listing(listing, reason),
                        "disable_web_page_preview": True,
                        "reply_markup": {"inline_keyboard": feedback_buttons(listing)},
                    },
                )
                sent += 1
            except Exception as exc:
                log.warning("telegram card send failed: %s", exc)
        return sent
