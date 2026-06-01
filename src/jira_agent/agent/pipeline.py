"""The per-ticket decision pipeline.

Conservative by construction — a ticket reaches RESOLVE only by clearing every
gate; any failure falls through to DEFER:

    triage red flag?            -> DEFER (triage reason code)
    top retrieval < threshold?  -> DEFER (LOW_CONFIDENCE)
    sections conflict?          -> DEFER (CONFLICTING_POLICIES)
    citation unsupported/empty? -> DEFER (LOW_CONFIDENCE)
    else                        -> RESOLVE (grounded answer + verified citations)
"""

from __future__ import annotations

from ..config import Settings
from ..llm.base import LLMClient
from ..llm.parsing import JsonParseError, complete_json
from ..llm.prompts import GROUNDED_ANSWER_SYSTEM, build_answer_prompt
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
        self._retrieval_k = settings.agent_retrieval_k

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

        # 2. Retrieve + confidence floor. The whole ticket body is one query and yields a
        # single grounded answer — multi-part tickets are not split (see README "Scope &
        # deliberate limitations"); a part that trips triage defers the whole ticket above.
        retrieved = self._retriever.retrieve(ticket.body, k=self._retrieval_k)
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

        # 4. Verify citations AND require a non-empty answer before allowing RESOLVE. An empty
        # answer paired with otherwise-valid citations must NOT resolve (the comment would be a
        # bare "Source: ..."); treat it as a conservative LOW_CONFIDENCE deferral.
        grounding = verify_citations(citations, self._corpus, retrieved)
        if not grounding.ok:
            return self._defer_low_confidence(ticket, top, retrieved, "; ".join(grounding.problems))
        if not answer.strip():
            return self._defer_low_confidence(
                ticket, top, retrieved, "Grounded answer was empty; nothing to resolve with."
            )

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
        """Ask the LLM to answer strictly from the retrieved sections.

        Returns (answer, citations, conflict). On a parse failure we return an empty
        answer with no citations, which the caller's grounding check turns into a
        conservative LOW_CONFIDENCE deferral.
        """
        try:
            data = complete_json(
                self._llm,
                system=GROUNDED_ANSWER_SYSTEM,
                prompt=build_answer_prompt(ticket.body, retrieved),
                max_tokens=600,
            )
        except JsonParseError as exc:
            log.warning("answer.parse_failed", ticket=ticket.id, error=str(exc))
            return "", [], False

        conflict = bool(data.get("conflict", False))
        answer = str(data.get("answer", "")).strip()
        citations = _parse_citations(data.get("citations", []))
        return answer, citations, conflict


def _parse_citations(raw: object) -> list[Citation]:
    """Normalize the model's citation list, tolerating '§'/stray formatting."""
    citations: list[Citation] = []
    if not isinstance(raw, list):
        return citations
    for item in raw:
        if not isinstance(item, dict):
            continue
        policy_id = str(item.get("policy_id", "")).strip().upper()
        section = str(item.get("section", "")).lstrip("§ ").strip()
        if policy_id and section:
            citations.append(Citation(policy_id=policy_id, section=section))
    return citations
