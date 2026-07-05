"""Adviser layer — a short, honest buyer's-agent take on a listing.

Grounded in the family profile (config.FAMILY_PROFILE) + accumulated market context from the
store. Uses Azure OpenAI when configured; degrades gracefully (returns None) otherwise, so the
daily brief still ships with facts. Cost-capped: only the top-N ranked listings get a take.
"""
from __future__ import annotations

import logging
from typing import Optional

from aoai import configured, get_client
from config import AZURE_OPENAI_DEPLOYMENT, COMM_LANGUAGE, FAMILY_PROFILE
from models import Listing

log = logging.getLogger("homescout.adviser")

LANG_NAMES = {"ru": "Russian", "en": "English", "lv": "Latvian"}


def enabled() -> bool:
    """True if Azure OpenAI is configured for the adviser."""
    return configured()


def build_messages(
    listing: Listing, stats: Optional[dict] = None, taste: Optional[str] = None,
    lang: str = COMM_LANGUAGE,
) -> list[dict]:
    """Build the chat messages for a listing's take (pure — unit-testable)."""
    facts = [
        f"Area: {listing.district or '?'}",
        f"Price: €{listing.price:,.0f}" if listing.price else "",
        f"{listing.price_per_m2:,.0f} €/m²" if listing.price_per_m2 else "",
        f"{listing.rooms} rooms" if listing.rooms else "",
        f"{listing.area_m2:g} m²" if listing.area_m2 else "",
        f"floor {listing.floor}" if listing.floor else "",
        f"energy class {listing.energy_class}" if listing.energy_class else "",
        f"~{listing.commute_min:g} min to centre" if listing.commute_min else "",
        f"nearest school {listing.nearest_school_km:g} km" if listing.nearest_school_km is not None else "",
        f"valuation: {listing.valuation}" if listing.valuation else "",
        f"type: {listing.property_type}",
        f'seller headline: "{listing.title}"' if listing.title else "",
    ]
    context = "; ".join(f for f in facts if f)
    if stats and stats.get("count"):
        context += f"\nMarket context: we've tracked {stats['count']} listings in this area"
        context += f", averaging {stats['avg_ppm2']:,.0f} €/m²." if stats.get("avg_ppm2") else "."
    lang_name = LANG_NAMES.get(lang, "Russian")
    system = (
        "You are a sharp, friendly Latvian property buyer's agent advising ONE specific family. "
        "Be honest and concrete — no marketing fluff. The family's must-haves: at least 4 rooms "
        "(4 is fine, more is better), at least ~75 m², move-in-ready (not rented, not unfinished), "
        "in Mārupe, Rīga centre, or Jūrmala. Both apartments and houses are acceptable — never "
        "criticise a listing merely for being an apartment or for having exactly 4 rooms. "
        "If it genuinely misses a must-have (fewer than 4 rooms, clearly too small, rented / "
        "unfinished, or outside those three areas), say so plainly first. Otherwise give a "
        "positive, useful read: whether it fits and why, the biggest plus, and the main thing to "
        "check or negotiate.\n\n"
        f"The family: {FAMILY_PROFILE}"
    )
    if taste:
        system += f"\n\nLearned family preferences (weigh these): {taste}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": (
            f"Listing:\n{context}\n\nWrite your take in 2-3 short sentences, ONLY in {lang_name} "
            f"(do not answer in Latvian or English):"
        )},
    ]


async def advise(
    listing: Listing, stats: Optional[dict] = None, taste: Optional[str] = None
) -> Optional[str]:
    """Return a short adviser take (in the family's language), or None if unconfigured / fails."""
    if not enabled():
        return None
    try:
        resp = await get_client().chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT,
            messages=build_messages(listing, stats, taste),
            max_tokens=180,
            temperature=0.4,
        )
        return (resp.choices[0].message.content or "").strip() or None
    except Exception:
        log.exception("adviser failed for %s", listing.url)
        return None
