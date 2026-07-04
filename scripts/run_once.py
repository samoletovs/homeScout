"""Local one-shot runner — real fetch, prints alertable listings (no Telegram unless configured).

Usage:  python scripts/run_once.py
Set HOMESCOUT_DB to persist dedup state between runs (defaults to data/homescout.sqlite).
The first run seeds the store; run it again to see only genuinely new listings.
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


async def main() -> None:
    fresh = await run_once(notify_results=False)
    print(f"\n{len(fresh)} new/changed listing(s):\n")
    for listing, reason in fresh[:20]:
        print(format_listing(listing, reason))
        print("-" * 44)


if __name__ == "__main__":
    asyncio.run(main())
