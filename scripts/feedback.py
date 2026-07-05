"""Record family feedback on a listing (to test the learning loop before the bot gate).

Usage:
  python scripts/feedback.py <listing-url-or-key> <like|dislike|meh> "<comment>" [member]

The comment can be in Russian — it's translated to English for storage when the LLM is
configured. The listing must already have been seen (run scripts/run_once.py first).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "functions"))

from config import DB_PATH  # noqa: E402
from feedback import ingest, parse_sentiment  # noqa: E402
from store import Store  # noqa: E402


async def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        return
    ref, word = sys.argv[1], sys.argv[2]
    comment = sys.argv[3] if len(sys.argv) > 3 else None
    member = sys.argv[4] if len(sys.argv) > 4 else "family"
    store = Store(DB_PATH)
    try:
        ok = await ingest(store, ref, member, parse_sentiment(word), comment)
        print("recorded ✓" if ok else "listing not found — has it been seen yet? (run run_once.py)")
    finally:
        store.close()


if __name__ == "__main__":
    asyncio.run(main())
