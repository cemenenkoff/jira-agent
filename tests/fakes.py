"""Test doubles for the LLM, retriever, and Jira client, so the agent runs offline."""

from __future__ import annotations

from typing import Any

from jira_agent.models import RetrievedSection


class FakeLLM:
    """Routes by which stage's system prompt it receives.

    The triage system prompt contains "triage stage"; the answer system prompt
    contains "answering stage". Configure the canned JSON each stage returns.
    """

    def __init__(
        self,
        *,
        triage: str = '{"reason_code": null, "rationale": ""}',
        answer: str = '{"answer": "", "citations": [], "conflict": false}',
    ) -> None:
        self.triage = triage
        self.answer = answer
        self.prompts: list[str] = []

    def complete(self, *, system: str, prompt: str, max_tokens: int = 1024) -> str:
        self.prompts.append(prompt)
        if "triage stage" in system:
            return self.triage
        return self.answer


class SequenceLLM:
    """Returns queued responses in order (for retry/parse tests)."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls = 0

    def complete(self, *, system: str, prompt: str, max_tokens: int = 1024) -> str:
        self.calls += 1
        return self._responses.pop(0)


class FakeRetriever:
    """Returns a fixed result list, ignoring the query."""

    def __init__(self, results: list[RetrievedSection]) -> None:
        self._results = results

    def retrieve(self, query: str, k: int = 5) -> list[RetrievedSection]:
        return self._results[:k]


class FakeJira:
    """In-memory Jira double for seeding tests."""

    def __init__(
        self,
        *,
        issue_types: list[dict[str, Any]] | None = None,
        existing: list[dict[str, Any]] | None = None,
        transitions: list[dict[str, Any]] | None = None,
    ) -> None:
        self._issue_types = (
            issue_types
            if issue_types is not None
            else [{"name": "Service Request"}, {"name": "Task"}, {"name": "Incident"}]
        )
        self._existing = existing or []
        self._transitions = (
            transitions
            if transitions is not None
            else [{"name": "In Progress", "id": "11"}, {"name": "Resolved", "id": "31"}]
        )
        self.created: list[dict[str, Any]] = []
        # write-op recorders, so action tests can assert side effects
        self.comments: list[tuple[str, str]] = []
        self.labels: list[tuple[str, list[str]]] = []
        self.transitioned: list[tuple[str, str]] = []

    def get_project_issue_types(self, project_key: str) -> list[dict[str, Any]]:
        return self._issue_types

    def search(self, jql: str, max_results: int = 50) -> list[dict[str, Any]]:
        return self._existing

    def create_issue(
        self,
        *,
        project_key: str,
        summary: str,
        description: str,
        issue_type: str,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        key = f"{project_key}-{len(self.created) + 1}"
        record = {
            "key": key,
            "summary": summary,
            "description": description,
            "issue_type": issue_type,
            "labels": labels or [],
        }
        self.created.append(record)
        return {"key": key, "fields": {"summary": summary, "labels": labels or []}}

    # ── write ops (recorded for assertions) ──────────────────────────
    def add_comment(self, issue_key: str, text: str) -> None:
        self.comments.append((issue_key, text))

    def add_labels(self, issue_key: str, labels: list[str]) -> None:
        self.labels.append((issue_key, list(labels)))

    def get_transitions(self, issue_key: str) -> list[dict[str, Any]]:
        return self._transitions

    def transition_issue(self, issue_key: str, transition_id: str) -> None:
        self.transitioned.append((issue_key, transition_id))
