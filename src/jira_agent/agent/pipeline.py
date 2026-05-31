"""The per-ticket decision pipeline.

Conservative by construction — a ticket reaches RESOLVE only by clearing every
gate; any failure falls through to DEFER:

    triage red flag?            -> DEFER (triage reason code)
    top retrieval < threshold?  -> DEFER (LOW_CONFIDENCE)
    answer cites unsupported?   -> DEFER (LOW_CONFIDENCE)
    sections conflict?          -> DEFER (CONFLICTING_POLICIES)
    else                        -> RESOLVE (grounded answer + verified citations)
"""

from __future__ import annotations

from ..config import Settings
from ..llm.base import LLMClient
from ..logging_setup import get_logger
from ..models import ActionType, Citation, Decision, ReasonCode, RetrievedSection, Ticket
from ..policies.loader import PolicyCorpus
from ..policies.retriever import Retriever
from ..triage.classifier import TriageClassifier
from .grounding import verify_citations

log = get_logger("agent.pipeline")


class AgentPipeline:
    def __init__(
        self,
        *,
        triage: TriageClassifier,
        retriever: Retriever,
        llm: LLMClient,
        corpus: PolicyCorpus,
        settings: Settings,
    ) -> None:
        self._triage = triage
        self._retriever = retriever
        self._llm = llm
        self._corpus = corpus
        self._threshold = settings.agent_confidence_threshold

    def process(self, ticket: Ticket) -> Decision:
        # 1. Safety / scope triage. Any red flag => DEFER immediately.
        triage = self._triage.classify(ticket)
        if triage.reason_code is not None:
            return Decision(
                ticket_id=ticket.id,
                action=ActionType.DEFER,
                reason_code=triage.reason_code,
                rationale=triage.rationale,
            )

        # 2. Retrieve + confidence gate.
        retrieved = self._retriever.retrieve(ticket.body, k=5)
        top = retrieved[0].score if retrieved else 0.0
        if top < self._threshold:
            return self._defer_low_confidence(
                ticket,
                top,
                retrieved,
                "Top retrieved policy section scored below the confidence threshold.",
            )

        # 3. Grounded answer generation (LLM constrained to retrieved sections).
        answer, citations, conflict = self._generate_grounded_answer(ticket, retrieved)
        if conflict:
            return Decision(
                ticket_id=ticket.id,
                action=ActionType.DEFER,
                reason_code=ReasonCode.CONFLICTING_POLICIES,
                confidence=top,
                rationale="Retrieved sections give contradictory guidance.",
                retrieved=retrieved,
            )

        # 4. Verify citations before allowing RESOLVE.
        grounding = verify_citations(citations, self._corpus, retrieved)
        if not grounding.ok:
            return self._defer_low_confidence(ticket, top, retrieved, "; ".join(grounding.problems))

        return Decision(
            ticket_id=ticket.id,
            action=ActionType.RESOLVE,
            answer=answer,
            citations=citations,
            confidence=top,
            retrieved=retrieved,
        )

    # ── helpers ──────────────────────────────────────────────────────
    def _defer_low_confidence(
        self, ticket: Ticket, score: float, retrieved: list[RetrievedSection], why: str
    ) -> Decision:
        return Decision(
            ticket_id=ticket.id,
            action=ActionType.DEFER,
            reason_code=ReasonCode.LOW_CONFIDENCE,
            confidence=score,
            rationale=why,
            retrieved=retrieved,
        )

    def _generate_grounded_answer(
        self, ticket: Ticket, retrieved: list[RetrievedSection]
    ) -> tuple[str, list[Citation], bool]:
        # TODO(next pass): render llm.prompts.GROUNDED_ANSWER_SYSTEM with the retrieved
        # sections + render_ticket_block(ticket.body), call self._llm.complete(...),
        # parse strict JSON {answer, citations[], conflict}. Returns (answer, citations, conflict).
        raise NotImplementedError("grounded answer generation lands in the next pass")
