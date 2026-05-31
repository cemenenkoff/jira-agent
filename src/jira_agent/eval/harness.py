"""Replay the eval set through the pipeline and produce EvalRecords."""

from __future__ import annotations

import json
from pathlib import Path

from ..agent.pipeline import AgentPipeline
from ..models import ActionType, Citation, EvalRecord, EvalTicket


def load_eval_tickets(path: Path) -> list[EvalTicket]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [EvalTicket(**t) for t in data["tickets"]]


def _citation_set(citations: list[Citation]) -> set[tuple[str, str]]:
    return {(c.policy_id, c.section) for c in citations}


def score_ticket(
    expected: EvalTicket,
    decision_action: ActionType,
    *,
    predicted_citations: list[Citation],
    predicted_reason: object,
    confidence: float,
) -> EvalRecord:
    action_correct = decision_action == expected.expected_action
    if expected.expected_action is ActionType.RESOLVE:
        detail_correct = action_correct and (
            _citation_set(predicted_citations) == _citation_set(expected.expected_citations)
        )
    else:
        detail_correct = action_correct and predicted_reason == expected.expected_reason_code
    return EvalRecord(
        ticket_id=expected.id,
        expected_action=expected.expected_action,
        predicted_action=decision_action,
        expected_citations=expected.expected_citations,
        predicted_citations=predicted_citations,
        expected_reason_code=expected.expected_reason_code,
        predicted_reason_code=predicted_reason,  # type: ignore[arg-type]
        action_correct=action_correct,
        detail_correct=detail_correct,
        confidence=confidence,
    )


def evaluate(pipeline: AgentPipeline, tickets: list[EvalTicket]) -> list[EvalRecord]:
    records: list[EvalRecord] = []
    for t in tickets:
        decision = pipeline.process(t.to_ticket())
        records.append(
            score_ticket(
                t,
                decision.action,
                predicted_citations=decision.citations,
                predicted_reason=decision.reason_code,
                confidence=decision.confidence,
            )
        )
    return records
