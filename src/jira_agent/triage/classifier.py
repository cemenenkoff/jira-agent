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
from ..llm.parsing import JsonParseError, complete_json
from ..llm.prompts import build_triage_system, render_ticket_block
from ..logging_setup import get_logger
from ..models import ReasonCode, Ticket
from ..policies.loader import PolicyCorpus
from ..reason_codes import RETRIEVAL_REASON_CODES

log = get_logger("triage")


@dataclass
class TriageResult:
    reason_code: ReasonCode | None  # None => no red flag; proceed to retrieval
    rationale: str = ""


class TriageClassifier:
    def __init__(self, llm: LLMClient, corpus: PolicyCorpus) -> None:
        self._llm = llm
        self._system = build_triage_system(corpus)

    def classify(self, ticket: Ticket) -> TriageResult:
        try:
            data = complete_json(
                self._llm,
                system=self._system,
                prompt=render_ticket_block(ticket.body),
                max_tokens=300,
            )
        except JsonParseError as exc:
            # We couldn't run the safety check — fail safe by deferring.
            log.warning("triage.parse_failed", ticket=ticket.id, error=str(exc))
            return TriageResult(
                ReasonCode.LOW_CONFIDENCE,
                "Triage output could not be parsed; deferring out of caution.",
            )

        raw_code = data.get("reason_code")
        rationale = str(data.get("rationale", "")).strip()

        if not raw_code:  # null / empty => no red flag
            return TriageResult(None, rationale)

        try:
            code = ReasonCode(str(raw_code).strip())
        except ValueError:
            log.warning("triage.unknown_code", ticket=ticket.id, code=raw_code)
            return TriageResult(
                ReasonCode.LOW_CONFIDENCE,
                f"Triage returned an unrecognized reason code ({raw_code}); deferring.",
            )

        # LOW_CONFIDENCE / CONFLICTING_POLICIES are post-retrieval decisions, not triage's.
        if code in RETRIEVAL_REASON_CODES:
            return TriageResult(None, rationale)

        return TriageResult(code, rationale)
