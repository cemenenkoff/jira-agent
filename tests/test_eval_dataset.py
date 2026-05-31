"""Integrity checks on the 50-ticket eval set.

These also serve as a transcription guard: every RESOLVE citation must point at a
section that actually exists in the loaded policy corpus.
"""

from __future__ import annotations

from jira_agent.models import ActionType, EvalTicket
from jira_agent.policies.loader import PolicyCorpus


def test_fifty_tickets_split_25_25(eval_tickets: list[EvalTicket]) -> None:
    assert len(eval_tickets) == 50
    resolves = [t for t in eval_tickets if t.expected_action is ActionType.RESOLVE]
    defers = [t for t in eval_tickets if t.expected_action is ActionType.DEFER]
    assert len(resolves) == 25
    assert len(defers) == 25


def test_ticket_ids_are_unique_and_sequential(eval_tickets: list[EvalTicket]) -> None:
    ids = [t.id for t in eval_tickets]
    assert ids == [f"T-{i:03d}" for i in range(1, 51)]


def test_resolve_citations_exist_in_corpus(
    eval_tickets: list[EvalTicket], corpus: PolicyCorpus
) -> None:
    for ticket in eval_tickets:
        if ticket.expected_action is not ActionType.RESOLVE:
            continue
        assert ticket.expected_citations, f"{ticket.id} RESOLVE has no expected citation"
        for c in ticket.expected_citations:
            assert corpus.get_section(c.policy_id, c.section) is not None, (
                f"{ticket.id} cites {c}, which is not in the corpus"
            )


def test_resolves_have_no_reason_code_and_defers_have_one(
    eval_tickets: list[EvalTicket],
) -> None:
    for ticket in eval_tickets:
        if ticket.expected_action is ActionType.RESOLVE:
            assert ticket.expected_reason_code is None
        else:
            assert ticket.expected_reason_code is not None
            assert not ticket.expected_citations
