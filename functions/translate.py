"""Translation via Azure OpenAI — inbound family messages → English for storage.

The family communicates in their language (Russian); stored knowledge is English. Graceful:
returns the text unchanged if the LLM isn't configured.
"""
from __future__ import annotations

import logging
from typing import Optional

from config import AZURE_OPENAI_DEPLOYMENT

log = logging.getLogger("homescout.translate")


async def to_english(text: Optional[str]) -> Optional[str]:
    """Translate a family message to concise English (no-op if LLM unconfigured)."""
    from aoai import configured, get_client

    if not text or not configured():
        return text
    try:
        resp = await get_client().chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT,
            messages=[
                {"role": "system", "content": "Translate the user's message into concise English. Output only the translation, nothing else."},
                {"role": "user", "content": text},
            ],
            max_tokens=200,
            temperature=0,
        )
        return (resp.choices[0].message.content or text).strip()
    except Exception:
        log.exception("translation failed")
        return text
