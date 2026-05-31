"""Safety/scope triage — the first, conservative gate.

Catches the DEFER categories that are about *what kind of ticket this is* rather
than retrieval quality: ACTIVE_INCIDENT, PROMPT_INJECTION, HOSTILE_TONE,
PII_REQUEST, PRIVILEGED_ACCESS, OUT_OF_SCOPE, WRONG_TENANT, WRONG_INTENT,
SPECULATIVE, NONEXISTENT_POLICY. Returns reason_code=None when the ticket looks
like a genuine, in-scope policy question and should proceed to retrieval.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..llm.base import LLMClient
from ..models import ReasonCode, Ticket


@dataclass
class TriageResult:
    reason_code: ReasonCode | None  # None => no red flag; proceed to retrieval
    rationale: str = ""


class TriageClassifier:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def classify(self, ticket: Ticket) -> TriageResult:
        # TODO(next pass): render llm.prompts.TRIAGE_SYSTEM + render_ticket_block(ticket.body),
        # call self._llm.complete(...), parse the strict-JSON {reason_code, rationale}.
        # Map LOW_CONFIDENCE / CONFLICTING_POLICIES to None here (decided post-retrieval).
        raise NotImplementedError("TriageClassifier.classify lands in the next pass")
