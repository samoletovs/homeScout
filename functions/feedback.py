"""Family feedback + the learning loop.

Anyone in the family can 👍/👎 and comment on a listing. Comments arrive in the family's
language (Russian) and are translated to English for storage. The accumulated taste feeds
the adviser, so homeScout judges better over time.

Channel-agnostic: `ingest()` is the intake API any surface (the agentMode Telegram gate, a
CLI, a future dashboard) calls.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

log = logging.getLogger("homescout.feedback")

if TYPE_CHECKING:
    from store import Store

SENTIMENTS = {
    "like": 1, "love": 1, "yes": 1, "good": 1, "👍": 1, "❤️": 1, "❤": 1,
    "dislike": -1, "hate": -1, "no": -1, "bad": -1, "👎": -1,
    "meh": 0, "maybe": 0,
}


def parse_sentiment(word: Optional[str]) -> int:
    """Map a keyword / emoji to -1 / 0 / +1 (0 if unknown)."""
    return SENTIMENTS.get((word or "").strip().lower(), 0)


async def ingest(
    store: "Store", listing_ref: str, member: str, sentiment: int,
    comment: Optional[str] = None, translate: bool = True,
) -> bool:
    """Resolve the listing, translate the comment to English, and record the feedback."""
    key = store.key_for(listing_ref)
    if not key:
        log.warning("feedback: listing not found for %s", listing_ref)
        return False
    comment_en = comment
    if translate and comment:
        from translate import to_english

        comment_en = await to_english(comment)
    store.add_feedback(key, member or "family", int(sentiment), comment_en)
    return True


def format_taste_for_adviser(summary: Optional[dict]) -> Optional[str]:
    """Compact English summary of learned family taste for the adviser prompt."""
    if not summary or (not summary.get("liked") and not summary.get("disliked")):
        return None
    parts = [f"{summary['liked']} liked, {summary['disliked']} disliked so far"]
    for area, counts in summary.get("by_area", {}).items():
        if counts["like"] or counts["dislike"]:
            parts.append(f"{area} +{counts['like']}/-{counts['dislike']}")
    for note in summary.get("recent", []):
        verb = "liked" if note["sentiment"] > 0 else "disliked" if note["sentiment"] < 0 else "noted"
        parts.append(f"{verb} ({note['area']}): {note['comment']}")
    return " | ".join(parts)
