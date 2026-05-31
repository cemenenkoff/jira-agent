"""The minimal LLM surface the agent depends on. Implementations live alongside."""

from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    def complete(self, *, system: str, prompt: str, max_tokens: int = 1024) -> str:
        """Single-turn completion. `system` is the (cacheable) instruction block;
        `prompt` is the per-ticket user content. Returns the model's text."""
        ...
