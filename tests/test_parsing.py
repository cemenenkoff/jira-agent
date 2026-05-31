from __future__ import annotations

import pytest

from jira_agent.llm.parsing import JsonParseError, complete_json, extract_json

from .fakes import SequenceLLM


def test_extract_plain_json() -> None:
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_in_code_fence() -> None:
    raw = '```json\n{"reason_code": "OUT_OF_SCOPE", "rationale": "hr"}\n```'
    assert extract_json(raw)["reason_code"] == "OUT_OF_SCOPE"


def test_extract_json_with_surrounding_prose() -> None:
    raw = 'Sure! Here is the result:\n{"answer": "x", "citations": []}\nHope that helps.'
    assert extract_json(raw)["answer"] == "x"


def test_extract_rejects_non_object() -> None:
    with pytest.raises(JsonParseError):
        extract_json("[1, 2, 3]")


def test_extract_rejects_garbage() -> None:
    with pytest.raises(JsonParseError):
        extract_json("no json here")


def test_complete_json_retries_then_succeeds() -> None:
    llm = SequenceLLM(["not json", '{"ok": true}'])
    result = complete_json(llm, system="s", prompt="p", attempts=2)
    assert result == {"ok": True}
    assert llm.calls == 2


def test_complete_json_gives_up_after_attempts() -> None:
    llm = SequenceLLM(["nope", "still nope"])
    with pytest.raises(JsonParseError):
        complete_json(llm, system="s", prompt="p", attempts=2)
    assert llm.calls == 2
