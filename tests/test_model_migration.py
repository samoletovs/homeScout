"""Azure OpenAI model-retirement contract tests (offline: the wire body is captured by httpx).

gpt-4o / gpt-4.1 retire on 2027-04-14 and their deployments auto-upgrade to gpt-6-luna, which
answers 400 to max_tokens. Until the live AZURE_OPENAI_DEPLOYMENT is flipped the code still talks
to the OLD deployment, which answers 400 to reasoning_effort. So the request body must be valid for
both: max_completion_tokens always, temperature kept, reasoning_effort "none" only on gpt-6-luna.
"""
import importlib
import json
import os
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "functions"))

import adviser  # noqa: E402
import aoai  # noqa: E402
import translate  # noqa: E402
from models import Listing  # noqa: E402

_COMPLETION = {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "created": 0,
    "model": "test",
    "choices": [
        {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}
    ],
}


def _listing() -> Listing:
    return Listing(
        id="1", source="city24", url="u", district="Mārupe", description="Mārupe",
        price=190000, area_m2=78, rooms=3, property_type="apartment",
    )


class _WireCapture:
    """Patch the shared client so every request body the SDK sends is recorded."""

    def __init__(self, deployment: str):
        self.deployment = deployment
        self.bodies: list[dict] = []

    def __enter__(self):
        from openai import AsyncAzureOpenAI

        def handler(request: httpx.Request) -> httpx.Response:
            self.bodies.append(json.loads(request.content))
            return httpx.Response(200, json=_COMPLETION)

        client = AsyncAzureOpenAI(
            azure_endpoint="https://example.invalid",
            api_key="test-key",
            api_version="2024-10-21",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        self._patches = [
            patch.object(aoai, "AZURE_OPENAI_DEPLOYMENT", self.deployment),
            patch.object(aoai, "AZURE_OPENAI_ENDPOINT", "https://example.invalid"),
            patch.object(aoai, "AZURE_OPENAI_API_KEY", "test-key"),
            patch.object(aoai, "_client", client),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.stop()


class RequestShapeTests(unittest.IsolatedAsyncioTestCase):
    def assert_common(self, body: dict, deployment: str, max_completion: int, temperature: float):
        self.assertEqual(body["model"], deployment)
        self.assertEqual(body["max_completion_tokens"], max_completion)
        self.assertNotIn("max_tokens", body)
        self.assertEqual(body["temperature"], temperature)

    async def test_adviser_old_deployment_body(self):
        with _WireCapture("gpt-4.1") as wire:
            self.assertEqual(await adviser.advise(_listing()), "ok")
        (body,) = wire.bodies
        self.assert_common(body, "gpt-4.1", 180, 0.4)
        self.assertNotIn("reasoning_effort", body)

    async def test_adviser_luna_body(self):
        with _WireCapture("gpt-6-luna") as wire:
            self.assertEqual(await adviser.advise(_listing()), "ok")
        (body,) = wire.bodies
        self.assert_common(body, "gpt-6-luna", 180, 0.4)
        self.assertEqual(body["reasoning_effort"], "none")

    async def test_translate_old_deployment_body_keeps_temperature_zero(self):
        with _WireCapture("gpt-4.1") as wire:
            self.assertEqual(await translate.to_english("текст"), "ok")
        (body,) = wire.bodies
        self.assert_common(body, "gpt-4.1", 200, 0)
        self.assertNotIn("reasoning_effort", body)

    async def test_translate_luna_body_keeps_temperature_zero(self):
        with _WireCapture("gpt-6-luna") as wire:
            self.assertEqual(await translate.to_english("текст"), "ok")
        (body,) = wire.bodies
        self.assert_common(body, "gpt-6-luna", 200, 0)
        self.assertEqual(body["reasoning_effort"], "none")

    async def test_reasoning_only_for_exact_luna_name(self):
        for name in ("gpt-4o-mini", "gpt-4.1-nano", "gpt-6-luna-2", "GPT-6-LUNA", "gpt-6-sol"):
            with self.subTest(deployment=name):
                with _WireCapture(name) as wire:
                    await adviser.advise(_listing())
                self.assertNotIn("reasoning_effort", wire.bodies[0])
                self.assertIn("max_completion_tokens", wire.bodies[0])


class ClientLogTests(unittest.TestCase):
    def test_client_log_names_deployment_and_reasoning_mode(self):
        for deployment, expected in (("gpt-6-luna", "reasoning=none"), ("gpt-4.1", "reasoning=not sent")):
            with self.subTest(deployment=deployment):
                with patch.object(aoai, "_client", None), \
                        patch.object(aoai, "AZURE_OPENAI_DEPLOYMENT", deployment), \
                        patch.object(aoai, "AZURE_OPENAI_ENDPOINT", "https://example.invalid"), \
                        patch.object(aoai, "AZURE_OPENAI_API_KEY", "test-key"):
                    with self.assertLogs("aoai", level="INFO") as logs:
                        aoai.get_client()
                text = "\n".join(logs.output)
                self.assertIn(f"deployment={deployment}", text)
                self.assertIn("max_completion_tokens", text)
                self.assertIn(expected, text)
                self.assertNotIn("test-key", text)


class NoRetiringModelTests(unittest.TestCase):
    RETIRING = re.compile(r"gpt-4o|gpt-4\.1|gpt-35|gpt-3\.5|4o-mini|o4-mini|o3-mini|\bo3\b")

    def test_default_deployment_is_luna(self):
        import config

        try:
            with patch.dict(os.environ):
                os.environ.pop("AZURE_OPENAI_DEPLOYMENT", None)
                importlib.reload(config)
                self.assertEqual(config.AZURE_OPENAI_DEPLOYMENT, "gpt-6-luna")
        finally:
            importlib.reload(config)

    def test_no_retiring_model_name_in_shipped_files(self):
        files = [ROOT / "deploy.ps1", ROOT / ".env.example"]
        for folder in ("functions", "scripts", "infrastructure"):
            files += [
                p for p in (ROOT / folder).rglob("*")
                if p.suffix in {".py", ".ps1", ".bicep", ".json", ".txt", ".example"}
                and "assets" not in p.parts
            ]
        offenders = [
            f"{p.relative_to(ROOT)}:{m.group(0)}"
            for p in files
            for m in [self.RETIRING.search(p.read_text(encoding="utf-8", errors="ignore"))]
            if m
        ]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
