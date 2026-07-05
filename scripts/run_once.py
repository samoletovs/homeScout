"""Local one-shot runner for homeScout.

Two modes:

  python scripts/run_once.py            # real pipeline run (seeds on first run, then
                                        # prints only genuinely new/changed listings)
  python scripts/run_once.py --preview  # on-demand brief: fetch live listings, rank,
                                        # enrich + advise the top few, render the digest
                                        # exactly as the daily brief looks. Add --send to
                                        # also push it to Telegram (if TELEGRAM_* are set).

Set HOMESCOUT_DB to persist dedup state between real runs (defaults to data/homescout.sqlite).
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "functions"))

from notify import format_listing  # noqa: E402
from pipeline import run_once  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# Windows consoles default to cp1252; force UTF-8 so Latvian text / emoji print.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except AttributeError:
        pass


async def _run() -> None:
    fresh = await run_once(notify_results=False)
    print(f"\n{len(fresh)} new/changed listing(s):\n")
    for listing, reason in fresh[:20]:
        print(format_listing(listing, reason))
        print("-" * 44)


async def _preview(top: int, send: bool) -> None:
    """Render (and optionally send) a brief for the current top listings on demand.

    Unlike a real run this ignores seen-state — it always fetches, ranks, enriches and
    advises the current best listings and renders the digest, so you can see exactly what
    the daily brief looks like without waiting for the seed cycle.
    """
    import httpx

    from adviser import advise
    from adviser import enabled as adviser_enabled
    from config import ADVISE_TOP_N, ENRICH_CAP, USER_AGENT
    from enrich import enrich_all
    from feedback import format_taste_for_adviser
    from notify import TelegramNotifier, format_digest
    from pipeline import _dedupe
    from scoring import HardFilters, passes_hard_filters, score_listing
    from sources import fetch_all
    from store import Store
    from valuation import bucket_for, value_listing

    filters = HardFilters.from_env()
    store = Store(":memory:")  # preview never touches the real state DB
    try:
        async with httpx.AsyncClient(timeout=25.0, headers={"User-Agent": USER_AGENT}) as client:
            listings = [
                lst for lst in _dedupe(await fetch_all(client)) if passes_hard_filters(lst, filters)
            ]
            for lst in listings:  # cheap pre-score to pick candidates worth enriching
                value_listing(lst)
                lst.score, _ = score_listing(lst)
            listings.sort(key=lambda lst: lst.score or 0.0, reverse=True)
            shortlist = listings[:top]
            await enrich_all(shortlist, client, store, cap=ENRICH_CAP)
            for lst in shortlist:  # re-value + re-score now that commute/schools are known
                value_listing(lst)
                lst.score, _ = score_listing(lst)
            shortlist.sort(key=lambda lst: lst.score or 0.0, reverse=True)
            if adviser_enabled():
                taste = format_taste_for_adviser(store.taste_summary())
                for lst in shortlist[:ADVISE_TOP_N]:
                    lst.adviser = await advise(lst, store.area_stats(bucket_for(lst)), taste)
            pairs = [(lst, "new") for lst in shortlist]
            print(f"\n=== PREVIEW BRIEF ({len(pairs)} of {len(listings)} listings) ===\n")
            print(format_digest(pairs, limit=top))
            if send:
                notifier = TelegramNotifier()
                cards = await notifier.send_cards(pairs, client, top)
                state = "configured" if notifier.enabled else "not configured — nothing sent"
                print(f"\n[telegram: cards={cards}] ({state})")
    finally:
        store.close()


def main() -> None:
    args = sys.argv[1:]
    if "--preview" in args:
        top = 8
        if "--top" in args:
            try:
                top = int(args[args.index("--top") + 1])
            except (ValueError, IndexError):
                pass
        asyncio.run(_preview(top=top, send="--send" in args))
    else:
        asyncio.run(_run())


if __name__ == "__main__":
    main()
