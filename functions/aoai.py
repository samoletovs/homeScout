"""Shared lazy Azure OpenAI async client for the adviser + translator."""
from __future__ import annotations

from config import AZURE_OPENAI_API_KEY, AZURE_OPENAI_API_VERSION, AZURE_OPENAI_ENDPOINT

_client = None


def configured() -> bool:
    """True if Azure OpenAI credentials are present."""
    return bool(AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY)


def get_client():
    """Lazily create (once) and return the AsyncAzureOpenAI client."""
    global _client
    if _client is None:
        from openai import AsyncAzureOpenAI

        _client = AsyncAzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY,
            api_version=AZURE_OPENAI_API_VERSION,
        )
    return _client
