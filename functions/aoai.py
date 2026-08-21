"""Shared lazy Azure OpenAI async client for the adviser + translator."""
from __future__ import annotations

import logging
from urllib.parse import urlparse

from config import (
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_DEPLOYMENT,
    AZURE_OPENAI_ENDPOINT,
)

log = logging.getLogger(__name__)

_client = None


def configured() -> bool:
    """True if Azure OpenAI credentials are present."""
    return bool(AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY)


def get_client():
    """Lazily create (once) and return the AsyncAzureOpenAI client."""
    global _client
    if _client is None:
        from openai import AsyncAzureOpenAI

        # A deployment name is an alias, not necessarily a model name. Log the
        # endpoint host with the deployment (never the key) so the resource and
        # deployment pair that answered is recoverable from logs.
        host = urlparse(AZURE_OPENAI_ENDPOINT).hostname or "unknown-endpoint"
        log.info("Azure OpenAI: deployment=%s on %s", AZURE_OPENAI_DEPLOYMENT, host)

        _client = AsyncAzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY,
            api_version=AZURE_OPENAI_API_VERSION,
        )
    return _client
