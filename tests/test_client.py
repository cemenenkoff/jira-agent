from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from jira_agent.config import Settings
from jira_agent.jira.client import JiraClient, JiraError, _adf


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> JiraClient:
    settings = Settings(
        _env_file=None,
        jira_base_url="https://x.atlassian.net",
        jira_email="a@b.c",
        jira_api_token="t",
    )
    client = JiraClient(settings)
    # Swap the real transport for an in-memory one — no network.
    client._http = httpx.Client(
        base_url="https://x.atlassian.net/rest/api/3",
        transport=httpx.MockTransport(handler),
    )
    return client


def test_4xx_raises_jira_error_without_retry() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404, json={"errorMessages": ["not found"]})

    with pytest.raises(JiraError):
        _client(handler).get_transitions("ITSD-1")
    assert calls["n"] == 1  # 4xx (non-429) fails fast, no retry


def test_5xx_is_retried_then_maps_to_transport_error(monkeypatch) -> None:
    # Don't actually sleep between tenacity retries.
    monkeypatch.setattr(JiraClient._request.retry, "sleep", lambda *_a, **_k: None)
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, text="server boom")

    with pytest.raises(httpx.TransportError):
        _client(handler).get_transitions("ITSD-1")
    assert calls["n"] == 4  # stop_after_attempt(4)


def test_search_paginates_via_next_page_token() -> None:
    pages = iter(
        [
            {"issues": [{"key": "A-1"}], "nextPageToken": "tok2"},
            {"issues": [{"key": "A-2"}]},  # no token -> last page
        ]
    )
    tokens_seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        tokens_seen.append(body.get("nextPageToken"))
        return httpx.Response(200, json=next(pages))

    issues = _client(handler).search("project = X", max_results=50)
    assert [i["key"] for i in issues] == ["A-1", "A-2"]
    assert tokens_seen == [None, "tok2"]


def test_adf_wraps_nonempty_lines_only() -> None:
    doc = _adf("line one\n\nline two")
    assert doc["type"] == "doc"
    texts = [p["content"][0]["text"] for p in doc["content"] if p["content"]]
    assert texts == ["line one", "line two"]
