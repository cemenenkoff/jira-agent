"""Turn a Decision into Jira side effects. Honors AGENT_DRY_RUN.

Design choice: for self-serve "yes, do this" answers the agent *instructs* the
user rather than performing privileged actions on their behalf — a safer default,
and an explicit seam to revisit per customer.
"""

from __future__ import annotations

from ..config import Settings
from ..logging_setup import get_logger
from ..models import ActionType, Decision
from ..reason_codes import REASON_CODE_DESCRIPTIONS
from .client import JiraClient

log = get_logger("jira.actions")

# Jira transition names we'll try (first match wins) when resolving.
_RESOLVE_TRANSITIONS = ("Resolve", "Resolved", "Done", "Close", "Closed")


class TicketActions:
    def __init__(self, client: JiraClient, settings: Settings) -> None:
        self._jira = client
        self._dry_run = settings.agent_dry_run
        self._resolved_label = settings.agent_resolved_label
        self._defer_label = settings.agent_defer_label

    def apply(self, decision: Decision) -> None:
        if decision.action is ActionType.RESOLVE:
            self._resolve(decision)
        else:
            self._defer(decision)

    # ── RESOLVE ──────────────────────────────────────────────────────
    def _resolve(self, d: Decision) -> None:
        comment = _format_resolve_comment(d)
        labels = [self._resolved_label]
        log.info(
            "resolve",
            ticket=d.ticket_id,
            citations=[str(c) for c in d.citations],
            confidence=round(d.confidence, 3),
            dry_run=self._dry_run,
        )
        if self._dry_run:
            return
        self._jira.add_comment(d.ticket_id, comment)
        self._jira.add_labels(d.ticket_id, labels)
        self._transition_to_resolved(d.ticket_id)

    # ── DEFER ────────────────────────────────────────────────────────
    def _defer(self, d: Decision) -> None:
        comment = _format_defer_comment(d)
        reason = d.reason_code.value if d.reason_code else "UNSPECIFIED"
        labels = [self._defer_label, f"reason:{reason}"]
        log.info("defer", ticket=d.ticket_id, reason=reason, dry_run=self._dry_run)
        if self._dry_run:
            return
        self._jira.add_comment(d.ticket_id, comment)
        self._jira.add_labels(d.ticket_id, labels)

    def _transition_to_resolved(self, issue_key: str) -> None:
        transitions = {t["name"]: t["id"] for t in self._jira.get_transitions(issue_key)}
        for name in _RESOLVE_TRANSITIONS:
            if name in transitions:
                self._jira.transition_issue(issue_key, transitions[name])
                return
        log.warning("no_resolve_transition", ticket=issue_key, available=list(transitions))


def _format_resolve_comment(d: Decision) -> str:
    cites = ", ".join(str(c) for c in d.citations)
    return (
        f"{d.answer}\n\n"
        f"Source: {cites}\n\n"
        "— Auto-resolved by the Helix IT policy agent. "
        "Reply to re-open if this didn't fully answer your question."
    )


def _format_defer_comment(d: Decision) -> str:
    reason = d.reason_code.value if d.reason_code else "UNSPECIFIED"
    desc = REASON_CODE_DESCRIPTIONS.get(d.reason_code, "") if d.reason_code else ""
    rationale = f"\n\n{d.rationale}" if d.rationale else ""
    return (
        f"This ticket needs a human. Reason: {reason} — {desc}{rationale}\n\n"
        "— Triaged by the Helix IT policy agent; a Service Desk agent will follow up."
    )
