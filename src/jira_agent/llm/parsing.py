"""Robust JSON extraction for LLM outputs, with a small parse-retry wrapper.

Models occasionally wrap JSON in prose or markdown fences. `extract_json` first
tries a direct parse, then falls back to the outermost {...} object. `complete_json`
retries the LLM call when the output can't be parsed (default 2 attempts) before
giving up — callers treat that failure as a conservative DEFER.
"""

from __future__ import annotations

import json
from typing import Any

from .base import LLMClient


class JsonParseError(ValueError):
    pass


def extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise JsonParseError(f"no JSON object in model output: {text[:200]!r}") from None
        try:
            obj = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError as exc:
            raise JsonParseError(f"invalid JSON in model output: {exc}") from exc
    if not isinstance(obj, dict):
        raise JsonParseError("model output JSON was not an object")
    return obj


def complete_json(
    llm: LLMClient,
    *,
    system: str,
    prompt: str,
    attempts: int = 2,
    max_tokens: int = 1024,
) -> dict[str, Any]:
    last: Exception | None = None
    for _ in range(max(1, attempts)):
        raw = llm.complete(system=system, prompt=prompt, max_tokens=max_tokens)
        try:
            return extract_json(raw)
        except JsonParseError as exc:
            last = exc
    raise JsonParseError(str(last) if last else "no attempts made")
