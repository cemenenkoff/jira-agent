from __future__ import annotations

from jira_agent.eval.report import summarize, to_markdown
from jira_agent.models import ActionType, Citation, EvalRecord, ReasonCode


def _resolve(ticket: str, expected: list[Citation], predicted: list[Citation]) -> EvalRecord:
    exact = {(c.policy_id, c.section) for c in expected} == {
        (c.policy_id, c.section) for c in predicted
    }
    return EvalRecord(
        ticket_id=ticket,
        expected_action=ActionType.RESOLVE,
        predicted_action=ActionType.RESOLVE,
        expected_citations=expected,
        predicted_citations=predicted,
        action_correct=True,
        detail_correct=exact,
    )


def test_superset_citation_counts_as_required_present_but_not_exact() -> None:
    exact = _resolve(
        "T-1",
        [Citation(policy_id="POL-01", section="1.4")],
        [Citation(policy_id="POL-01", section="1.4")],
    )
    over = _resolve(
        "T-2",
        [Citation(policy_id="POL-03", section="3.4")],
        [Citation(policy_id="POL-03", section="3.4"), Citation(policy_id="POL-03", section="3.5")],
    )
    defer = EvalRecord(
        ticket_id="T-3",
        expected_action=ActionType.DEFER,
        predicted_action=ActionType.DEFER,
        expected_reason_code=ReasonCode.OUT_OF_SCOPE,
        predicted_reason_code=ReasonCode.OUT_OF_SCOPE,
        action_correct=True,
        detail_correct=True,
    )
    m = summarize([exact, over, defer])
    assert m["resolve_total"] == 2
    assert m["resolve_correct"] == 1  # only the exact one
    assert m["resolve_required_cited"] == 2  # both have the required citation present
    assert m["false_positives"] == 0
    assert m["missed_resolves"] == 0


def test_to_markdown_distinguishes_overcite_from_miss() -> None:
    over = _resolve(
        "T-2",
        [Citation(policy_id="POL-03", section="3.4")],
        [Citation(policy_id="POL-03", section="3.4"), Citation(policy_id="POL-03", section="3.5")],
    )
    miss = _resolve(
        "T-3",
        [Citation(policy_id="POL-08", section="8.3"), Citation(policy_id="POL-09", section="9.6")],
        [Citation(policy_id="POL-08", section="8.3"), Citation(policy_id="POL-09", section="9.1")],
    )
    md = to_markdown([over, miss], summarize([over, miss]))
    rows = {ln.split("|")[1].strip(): ln for ln in md.splitlines() if ln.startswith("| T-")}
    assert "⚠️" in rows["T-2"]  # over-cite: required present + extra
    assert "❌" in rows["T-3"]  # miss: a required citation absent
    assert "Legend:" in md
