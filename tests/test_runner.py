from __future__ import annotations

from jira_agent.config import Settings
from jira_agent.models import ActionType, Decision, ReasonCode
from jira_agent.runner import AgentRunner

from .fakes import FakeJira


def test_new_ticket_jql_includes_empty_labels() -> None:
    # A brand-new ticket has no labels; Jira `labels NOT IN (...)` excludes empty labels,
    # so the query must explicitly allow `labels IS EMPTY` or label-less tickets are missed.
    runner = AgentRunner(
        pipeline=object(),  # type: ignore[arg-type]
        jira=object(),  # type: ignore[arg-type]
        actions=object(),  # type: ignore[arg-type]
        settings=Settings(jira_project_key="ITSD"),
    )
    jql = runner._new_ticket_jql()
    assert "labels IS EMPTY" in jql
    assert 'project = "ITSD"' in jql
    assert "statusCategory != Done" in jql


class _FakePipeline:
    def __init__(self) -> None:
        self.seen: list[str] = []

    def process(self, ticket: object) -> Decision:
        tid = ticket.id  # type: ignore[attr-defined]
        self.seen.append(tid)
        return Decision(ticket_id=tid, action=ActionType.DEFER, reason_code=ReasonCode.OUT_OF_SCOPE)


class _RecordingActions:
    def __init__(self) -> None:
        self.applied: list[str] = []

    def apply(self, decision: Decision) -> None:
        self.applied.append(decision.ticket_id)


def test_poll_once_processes_each_new_ticket_once() -> None:
    issues = [
        {"key": "ITSD-1", "fields": {"summary": "q1", "labels": []}},
        {"key": "ITSD-2", "fields": {"summary": "q2", "labels": []}},
    ]
    jira = FakeJira(existing=issues)
    pipeline = _FakePipeline()
    actions = _RecordingActions()
    runner = AgentRunner(
        pipeline=pipeline,  # type: ignore[arg-type]
        jira=jira,  # type: ignore[arg-type]
        actions=actions,  # type: ignore[arg-type]
        settings=Settings(_env_file=None, jira_project_key="ITSD"),
    )
    first = runner.poll_once()
    second = runner.poll_once()  # same issues returned; the _seen set must skip them
    assert first == 2
    assert second == 0
    assert pipeline.seen == ["ITSD-1", "ITSD-2"]
    assert actions.applied == ["ITSD-1", "ITSD-2"]
