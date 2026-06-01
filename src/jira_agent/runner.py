"""The monitoring loop: poll the Service Desk queue, process new tickets, act.

Idempotency: only tickets without an agent label are fetched (JQL), and an
in-memory `_seen` set guards against double-processing within a run. A durable
store would replace `_seen` for production (see README hardening notes).
"""

from __future__ import annotations

import time

from .agent.pipeline import AgentPipeline
from .config import Settings
from .jira.actions import TicketActions
from .jira.client import JiraClient
from .jira.mapping import issue_to_ticket
from .logging_setup import get_logger

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
        # NOTE: Jira JQL `labels NOT IN (...)` excludes issues whose labels are EMPTY, so a
        # brand-new (label-less) ticket would be missed — hence the explicit `labels IS EMPTY`.
        unprocessed = (
            f'labels IS EMPTY OR labels NOT IN ("{self._resolved_label}", "{self._defer_label}")'
        )
        return (
            f'project = "{self._project}" AND ({unprocessed}) '
            f"AND statusCategory != Done ORDER BY created ASC"
        )

    def poll_once(self) -> int:
        processed = 0
        for issue in self._jira.search(self._new_ticket_jql()):
            ticket = issue_to_ticket(issue)
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
