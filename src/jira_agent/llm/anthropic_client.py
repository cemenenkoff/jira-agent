"""Anthropic-backed LLMClient.

The policy corpus / triage rubric is large and static, so the system block is
marked for prompt caching — every ticket after the first reuses the cached
prefix, cutting cost and latency.
"""

from __future__ import annotations

from typing import Any

from ..config import Settings
from .base import LLMClient


class AnthropicClient(LLMClient):
    def __init__(self, settings: Settings) -> None:
        settings.require_llm()
        self._model = settings.anthropic_model
        self._api_key = settings.anthropic_api_key
        self._client: Any = None  # created lazily so import never requires the key

    def _ensure_client(self) -> Any:
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def complete(self, *, system: str, prompt: str, max_tokens: int = 1024) -> str:
        client = self._ensure_client()
        resp = client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=0.0,
            system=[
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in resp.content if block.type == "text")
