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

LUNA_DEPLOYMENT = "gpt-6-luna"

_client = None


def configured() -> bool:
    """True if Azure OpenAI credentials are present."""
    return bool(AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY)


def uses_reasoning_none() -> bool:
    """True when the runtime deployment is gpt-6-luna and the request must carry reasoning none."""
    return AZURE_OPENAI_DEPLOYMENT == LUNA_DEPLOYMENT


def chat_kwargs(max_tokens: int, temperature: float) -> dict:
    """Chat-completions arguments valid for both the old and the gpt-6-luna deployment.

    max_completion_tokens is accepted by both (gpt-6-luna rejects max_tokens). Luna accepts
    temperature only with reasoning none, while the old deployments reject reasoning_effort,
    so it is sent only when the deployment name resolved at runtime is gpt-6-luna.
    """
    kwargs = {
        "model": AZURE_OPENAI_DEPLOYMENT,
        "max_completion_tokens": max_tokens,
        "temperature": temperature,
    }
    if uses_reasoning_none():
        kwargs["reasoning_effort"] = "none"
    return kwargs


def get_client():
    """Lazily create (once) and return the AsyncAzureOpenAI client."""
    global _client
    if _client is None:
        from openai import AsyncAzureOpenAI

        # A deployment name is an alias, not necessarily a model name. Log the
        # endpoint host with the deployment (never the key) so the resource and
        # deployment pair that answered is recoverable from logs.
        host = urlparse(AZURE_OPENAI_ENDPOINT).hostname or "unknown-endpoint"
        log.info(
            "Azure OpenAI: deployment=%s on %s (max_completion_tokens, reasoning=%s)",
            AZURE_OPENAI_DEPLOYMENT, host, "none" if uses_reasoning_none() else "not sent",
        )

        _client = AsyncAzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY,
            api_version=AZURE_OPENAI_API_VERSION,
        )
    return _client
