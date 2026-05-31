"""Test doubles for the LLM and retriever, so the pipeline can be exercised offline."""

from __future__ import annotations

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
