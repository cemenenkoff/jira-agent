"""Seed the 50 eval tickets into a Jira project for live demo / dry-run.

Idempotent: each created issue carries an ``eval-<id>`` label, and re-running skips
tickets already present (matched by that label) so it won't create duplicates.
The label also lets a later live-eval report join an issue back to its ground truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..logging_setup import get_logger
from ..models import EvalTicket

log = get_logger("jira.seed")

EVAL_LABEL_PREFIX = "eval-"


def eval_id_from_issue(issue: dict[str, Any]) -> str | None:
    """Return the eval-ticket id stamped on an issue via its ``eval-<id>`` label, or None."""
    for label in issue.get("fields", {}).get("labels", []):
        if isinstance(label, str) and label.startswith(EVAL_LABEL_PREFIX):
            return label[len(EVAL_LABEL_PREFIX) :]
    return None


# Preference order when the requested issue type isn't available in the project.
_ISSUE_TYPE_PREFERENCE = ("Service Request", "Task", "Incident", "Support")


class _Jira(Protocol):
    def get_project_issue_types(self, project_key: str) -> list[dict[str, Any]]: ...
    def search(self, jql: str, max_results: int = 50) -> list[dict[str, Any]]: ...
    def create_issue(
        self,
        *,
        project_key: str,
        summary: str,
        description: str,
        issue_type: str,
        labels: list[str] | None = None,
    ) -> dict[str, Any]: ...


@dataclass
class SeedSummary:
    issue_type: str
    dry_run: bool
    created: list[tuple[str, str | None]] = field(default_factory=list)  # (eval_id, issue_key)
    skipped_existing: list[str] = field(default_factory=list)


def seed_tickets(
    jira: _Jira,
    *,
    project_key: str,
    tickets: list[EvalTicket],
    issue_type: str = "Service Request",
    limit: int = 0,
    dry_run: bool = False,
) -> SeedSummary:
    resolved_type = _resolve_issue_type(jira, project_key, issue_type)
    existing = _existing_eval_ids(jira, project_key)

    pending = [t for t in tickets if t.id not in existing]
    skipped = sorted(t.id for t in tickets if t.id in existing)
    if limit > 0:
        pending = pending[:limit]

    summary = SeedSummary(issue_type=resolved_type, dry_run=dry_run, skipped_existing=skipped)
    for ticket in pending:
        if dry_run:
            summary.created.append((ticket.id, None))
            continue
        issue = jira.create_issue(
            project_key=project_key,
            summary=_issue_summary(ticket.body),
            description=ticket.body,
            issue_type=resolved_type,
            labels=[f"{EVAL_LABEL_PREFIX}{ticket.id}"],
        )
        key = issue.get("key")
        log.info("seed.created", eval_id=ticket.id, issue=key)
        summary.created.append((ticket.id, key))

    return summary


def _resolve_issue_type(jira: _Jira, project_key: str, requested: str) -> str:
    try:
        available = [str(t.get("name", "")) for t in jira.get_project_issue_types(project_key)]
    except Exception as exc:  # createmeta is best-effort; fall back to the requested name
        log.warning("seed.issue_types_unavailable", error=str(exc))
        return requested
    available = [name for name in available if name]
    if not available:
        return requested
    lowered = {name.lower(): name for name in available}
    if requested.lower() in lowered:
        return lowered[requested.lower()]
    for pref in _ISSUE_TYPE_PREFERENCE:
        if pref.lower() in lowered:
            log.warning(
                "seed.issue_type_fallback", requested=requested, using=lowered[pref.lower()]
            )
            return lowered[pref.lower()]
    return available[0]


def _existing_eval_ids(jira: _Jira, project_key: str) -> set[str]:
    ids: set[str] = set()
    for issue in jira.search(f'project = "{project_key}"', max_results=100):
        eval_id = eval_id_from_issue(issue)
        if eval_id is not None:
            ids.add(eval_id)
    return ids


def _issue_summary(body: str, max_len: int = 200) -> str:
    text = " ".join(body.split())
    return text if len(text) <= max_len else text[: max_len - 1].rstrip() + "…"
