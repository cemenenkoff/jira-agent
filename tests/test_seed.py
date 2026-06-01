from __future__ import annotations

from jira_agent.jira.seed import seed_tickets
from jira_agent.models import EvalTicket

from .fakes import FakeJira


def test_seeds_all_tickets_into_empty_project(eval_tickets: list[EvalTicket]) -> None:
    jira = FakeJira()
    result = seed_tickets(jira, project_key="ITSD", tickets=eval_tickets)
    assert len(result.created) == 50
    assert len(jira.created) == 50
    assert result.issue_type == "Service Request"
    # Every created issue carries its eval-<id> correlation label.
    assert jira.created[0]["labels"] == ["eval-T-001"]


def test_seed_is_idempotent(eval_tickets: list[EvalTicket]) -> None:
    existing = [{"fields": {"labels": ["eval-T-001", "auto-resolved"]}}]
    jira = FakeJira(existing=existing)
    result = seed_tickets(jira, project_key="ITSD", tickets=eval_tickets)
    assert len(result.created) == 49
    assert "T-001" in result.skipped_existing
    assert all(rec["labels"] != ["eval-T-001"] for rec in jira.created)


def test_seed_limit(eval_tickets: list[EvalTicket]) -> None:
    jira = FakeJira()
    result = seed_tickets(jira, project_key="ITSD", tickets=eval_tickets, limit=5)
    assert len(result.created) == 5
    assert len(jira.created) == 5


def test_seed_dry_run_creates_nothing(eval_tickets: list[EvalTicket]) -> None:
    jira = FakeJira()
    result = seed_tickets(jira, project_key="ITSD", tickets=eval_tickets, dry_run=True)
    assert result.dry_run
    assert len(result.created) == 50  # planned
    assert jira.created == []  # but nothing written
    assert all(key is None for _, key in result.created)


def test_issue_type_falls_back_when_requested_missing(eval_tickets: list[EvalTicket]) -> None:
    jira = FakeJira(issue_types=[{"name": "Task"}])
    result = seed_tickets(
        jira, project_key="ITSD", tickets=eval_tickets, issue_type="Service Request"
    )
    assert result.issue_type == "Task"


def test_issue_summary_is_within_jira_limit(eval_tickets: list[EvalTicket]) -> None:
    jira = FakeJira()
    seed_tickets(jira, project_key="ITSD", tickets=eval_tickets)
    assert all(len(rec["summary"]) <= 200 for rec in jira.created)
