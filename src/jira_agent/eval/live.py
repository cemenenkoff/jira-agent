"""Live evaluation: score the agent against tickets read back from real Jira.

This is the end-to-end integration test. Unlike the offline harness (which reads
tickets from the JSON fixture), this fetches the seeded issues from Jira, rebuilds
each Ticket through the same read path the runner uses (issue -> ADF -> Ticket),
runs the pipeline, and joins back to ground truth via the `eval-<id>` label.
"""

from __future__ import annotations

from typing import Any, Protocol

from ..jira.mapping import issue_to_ticket
from ..jira.seed import EVAL_LABEL_PREFIX
from ..logging_setup import get_logger
from ..models import EvalRecord, EvalTicket
from .harness import score_ticket

log = get_logger("eval.live")


class _Pipeline(Protocol):
    def process(self, ticket: Any) -> Any: ...


class _Jira(Protocol):
    def search(self, jql: str, max_results: int = 50) -> list[dict[str, Any]]: ...


def _eval_id(issue: dict[str, Any]) -> str | None:
    for label in issue.get("fields", {}).get("labels", []):
        if isinstance(label, str) and label.startswith(EVAL_LABEL_PREFIX):
            return label[len(EVAL_LABEL_PREFIX) :]
    return None


def run_live_eval(
    jira: _Jira,
    pipeline: _Pipeline,
    *,
    project_key: str,
    eval_tickets: list[EvalTicket],
) -> list[EvalRecord]:
    ground_truth = {t.id: t for t in eval_tickets}
    records: list[EvalRecord] = []

    for issue in jira.search(f'project = "{project_key}"', max_results=100):
        eval_id = _eval_id(issue)
        if eval_id is None or eval_id not in ground_truth:
            continue  # not a seeded eval ticket
        expected = ground_truth[eval_id]
        ticket = issue_to_ticket(issue)  # the real read path
        decision = pipeline.process(ticket)
        log.info(
            "eval_live.scored",
            eval_id=eval_id,
            issue=issue.get("key"),
            action=decision.action.value,
        )
        records.append(
            score_ticket(
                expected,
                decision.action,
                predicted_citations=decision.citations,
                predicted_reason=decision.reason_code,
                confidence=decision.confidence,
            )
        )

    records.sort(key=lambda r: r.ticket_id)
    return records
