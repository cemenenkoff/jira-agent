from __future__ import annotations

from typing import Any

from jira_agent.config import Settings
from jira_agent.llm.anthropic_client import AnthropicClient


class _Block:
    def __init__(self, text: str, kind: str = "text") -> None:
        self.text = text
        self.type = kind


class _Resp:
    def __init__(self, blocks: list[_Block]) -> None:
        self.content = blocks


class _Messages:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> _Resp:
        self.kwargs = kwargs
        return _Resp([_Block("hello "), _Block("world"), _Block("[img]", kind="image")])


class _FakeAnthropic:
    def __init__(self) -> None:
        self.messages = _Messages()


def test_complete_joins_text_blocks_and_sets_caching() -> None:
    client = AnthropicClient(Settings(_env_file=None, anthropic_api_key="x"))
    fake = _FakeAnthropic()
    client._client = fake  # bypass the lazy SDK import / network

    out = client.complete(system="SYS", prompt="P", max_tokens=123)

    assert out == "hello world"  # non-text blocks filtered out
    kw = fake.messages.kwargs
    assert kw["temperature"] == 0.0
    assert kw["max_tokens"] == 123
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert kw["messages"] == [{"role": "user", "content": "P"}]
