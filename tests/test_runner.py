from __future__ import annotations

from jira_agent.config import Settings
from jira_agent.runner import AgentRunner


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
