"""Thin Jira Cloud REST v3 client with explicit timeouts and bounded retries.

Production Jira integrations need robust retry/timeout behavior, so it lives here
in one place: a 10s request timeout and exponential backoff on transport errors /
429 / 5xx via tenacity. 4xx (other than 429) fails fast.
"""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..config import Settings
from ..logging_setup import get_logger

log = get_logger("jira.client")

# Transport-level errors and a synthetic error we raise for 429/5xx are retryable.
_RETRYABLE = (httpx.TimeoutException, httpx.TransportError)


class JiraError(RuntimeError):
    """Non-retryable Jira API error (4xx other than 429)."""


class JiraClient:
    def __init__(self, settings: Settings) -> None:
        settings.require_jira()
        assert settings.jira_base_url and settings.jira_email and settings.jira_api_token
        self._http = httpx.Client(
            base_url=f"{settings.jira_base_url.rstrip('/')}/rest/api/3",
            auth=(settings.jira_email, settings.jira_api_token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=httpx.Timeout(10.0, connect=5.0),
        )

    # ── lifecycle ────────────────────────────────────────────────────
    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> JiraClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # ── core request with retry/backoff ──────────────────────────────
    @retry(
        reraise=True,
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=0.5, max=8),
        retry=retry_if_exception_type(_RETRYABLE),
    )
    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        resp = self._http.request(method, path, **kwargs)
        if resp.status_code == 429 or resp.status_code >= 500:
            # Surface as a retryable transport error so tenacity backs off.
            raise httpx.TransportError(f"Jira {resp.status_code} on {method} {path}")
        if resp.status_code >= 400:
            raise JiraError(f"Jira {resp.status_code} on {method} {path}: {resp.text}")
        return resp

    # ── read ─────────────────────────────────────────────────────────
    def search(self, jql: str, max_results: int = 50) -> list[dict[str, Any]]:
        # NOTE: Jira Cloud's current endpoint is POST /search/jql; older sites use /search.
        # Paginate via nextPageToken so a queue larger than one page isn't silently truncated;
        # stop once we have max_results or the server reports no further pages.
        issues: list[dict[str, Any]] = []
        next_token: str | None = None
        while len(issues) < max_results:
            payload: dict[str, Any] = {
                "jql": jql,
                "maxResults": min(100, max_results - len(issues)),
                "fields": ["summary", "description", "labels", "reporter", "status"],
            }
            if next_token:
                payload["nextPageToken"] = next_token
            data = self._request("POST", "/search/jql", json=payload).json()
            issues.extend(data.get("issues", []))
            next_token = data.get("nextPageToken")
            if not next_token:
                break
        return issues[:max_results]

    def get_transitions(self, issue_key: str) -> list[dict[str, Any]]:
        data = self._request("GET", f"/issue/{issue_key}/transitions").json()
        return list(data.get("transitions", []))

    # ── write ────────────────────────────────────────────────────────
    def add_comment(self, issue_key: str, text: str) -> None:
        self._request("POST", f"/issue/{issue_key}/comment", json={"body": _adf(text)})

    def add_labels(self, issue_key: str, labels: list[str]) -> None:
        ops = [{"add": label} for label in labels]
        self._request("PUT", f"/issue/{issue_key}", json={"update": {"labels": ops}})

    def transition_issue(self, issue_key: str, transition_id: str) -> None:
        self._request(
            "POST",
            f"/issue/{issue_key}/transitions",
            json={"transition": {"id": transition_id}},
        )

    def get_project_issue_types(self, project_key: str) -> list[dict[str, Any]]:
        data = self._request("GET", f"/issue/createmeta/{project_key}/issuetypes").json()
        # Tolerate both the paginated ("values") and legacy ("issueTypes") shapes.
        items = data.get("values") or data.get("issueTypes") or []
        return list(items)

    def create_issue(
        self,
        *,
        project_key: str,
        summary: str,
        description: str,
        issue_type: str,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "project": {"key": project_key},
            "summary": summary,
            "description": _adf(description),
            "issuetype": {"name": issue_type},
        }
        if labels:
            fields["labels"] = labels
        return dict(self._request("POST", "/issue", json={"fields": fields}).json())


def _adf(text: str) -> dict[str, Any]:
    """Wrap plain text (newline-separated) in Atlassian Document Format."""
    paragraphs = [
        {"type": "paragraph", "content": [{"type": "text", "text": line}]}
        for line in text.split("\n")
        if line.strip()
    ]
    return {
        "type": "doc",
        "version": 1,
        "content": paragraphs or [{"type": "paragraph", "content": []}],
    }
