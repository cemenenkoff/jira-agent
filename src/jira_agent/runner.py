"""The monitoring loop: poll the Service Desk queue, process new tickets, act.

Idempotency: only tickets without an agent label are fetched (JQL), and an
in-memory `_seen` set guards against double-processing within a run. A durable
store would replace `_seen` for production (see README hardening notes).
"""

from __future__ import annotations

import time
from typing import Any

from .agent.pipeline import AgentPipeline
from .config import Settings
from .jira.actions import TicketActions
from .jira.client import JiraClient
from .logging_setup import get_logger
from .models import Ticket

log = get_logger("agent.runner")


class AgentRunner:
    def __init__(
        self,
        *,
        pipeline: AgentPipeline,
        jira: JiraClient,
        actions: TicketActions,
        settings: Settings,
    ) -> None:
        self._pipeline = pipeline
        self._jira = jira
        self._actions = actions
        self._project = settings.jira_project_key
        self._interval = settings.agent_poll_interval_seconds
        self._resolved_label = settings.agent_resolved_label
        self._defer_label = settings.agent_defer_label
        self._seen: set[str] = set()

    def _new_ticket_jql(self) -> str:
        # "Unprocessed" = no agent label yet and not already Done. FIFO by creation.
        return (
            f'project = "{self._project}" '
            f'AND labels NOT IN ("{self._resolved_label}", "{self._defer_label}") '
            f"AND statusCategory != Done ORDER BY created ASC"
        )

    def poll_once(self) -> int:
        processed = 0
        for issue in self._jira.search(self._new_ticket_jql()):
            ticket = _to_ticket(issue)
            if ticket.id in self._seen:
                continue
            log.info("processing", ticket=ticket.id)
            decision = self._pipeline.process(ticket)
            self._actions.apply(decision)
            self._seen.add(ticket.id)
            processed += 1
        return processed

    def run_forever(self) -> None:
        log.info("agent.start", project=self._project, interval=self._interval)
        while True:
            try:
                n = self.poll_once()
                log.info("poll.done", processed=n)
            except Exception as exc:  # keep the loop alive; surface the error
                log.error("poll.error", error=str(exc))
            time.sleep(self._interval)


def _to_ticket(issue: dict[str, Any]) -> Ticket:
    fields = issue.get("fields", {})
    desc = fields.get("description")
    body = _adf_to_text(desc) if isinstance(desc, dict) else (desc or "")
    summary = fields.get("summary")
    full = f"{summary}\n\n{body}".strip() if summary else body
    reporter = (fields.get("reporter") or {}).get("displayName")
    return Ticket(id=issue["key"], body=full, summary=summary, reporter=reporter, raw=issue)


def _adf_to_text(node: object) -> str:
    """Best-effort flatten of an Atlassian Document Format node to plain text."""
    if isinstance(node, dict):
        if node.get("type") == "text":
            return str(node.get("text", ""))
        return "".join(_adf_to_text(c) for c in node.get("content", []))
    if isinstance(node, list):
        return "".join(_adf_to_text(c) for c in node)
    return ""
