from __future__ import annotations

from jira_agent.agent.pipeline import AgentPipeline
from jira_agent.config import Settings
from jira_agent.models import ActionType, ReasonCode, RetrievedSection, Ticket
from jira_agent.policies.loader import PolicyCorpus
from jira_agent.triage.classifier import TriageClassifier

from .fakes import FakeLLM, FakeRetriever


def _rsec(corpus: PolicyCorpus, policy_id: str, section: str, score: float) -> RetrievedSection:
    sec = corpus.get_section(policy_id, section)
    assert sec is not None
    return RetrievedSection(section=sec, score=score)


def _pipeline(
    corpus: PolicyCorpus, *, llm: FakeLLM, retrieved: list[RetrievedSection]
) -> AgentPipeline:
    settings = Settings(agent_confidence_threshold=0.45)
    return AgentPipeline(
        triage=TriageClassifier(llm, corpus),
        retriever=FakeRetriever(retrieved),
        llm=llm,
        corpus=corpus,
        settings=settings,
    )


def test_resolves_when_answer_is_grounded(corpus: PolicyCorpus) -> None:
    llm = FakeLLM(
        answer='{"answer": "Yes — MFA via Okta is mandatory for all corporate apps.",'
        ' "citations": [{"policy_id": "POL-01", "section": "1.3"}], "conflict": false}'
    )
    pipe = _pipeline(corpus, llm=llm, retrieved=[_rsec(corpus, "POL-01", "1.3", 0.9)])
    decision = pipe.process(Ticket(id="T-002", body="Do I need MFA to log into Salesforce?"))
    assert decision.action is ActionType.RESOLVE
    assert [str(c) for c in decision.citations] == ["POL-01 §1.3"]
    assert decision.answer


def test_low_confidence_defers_before_answering(corpus: PolicyCorpus) -> None:
    llm = FakeLLM()
    pipe = _pipeline(corpus, llm=llm, retrieved=[_rsec(corpus, "POL-01", "1.3", 0.10)])
    decision = pipe.process(Ticket(id="T-002", body="Do I need MFA?"))
    assert decision.action is ActionType.DEFER
    assert decision.reason_code is ReasonCode.LOW_CONFIDENCE
    assert len(llm.prompts) == 1  # triage only; no answer generation attempted


def test_triage_red_flag_skips_retrieval_and_answer(corpus: PolicyCorpus) -> None:
    llm = FakeLLM(triage='{"reason_code": "OUT_OF_SCOPE", "rationale": "HR/PTO question"}')
    pipe = _pipeline(corpus, llm=llm, retrieved=[_rsec(corpus, "POL-01", "1.3", 0.9)])
    decision = pipe.process(Ticket(id="T-026", body="How many vacation days do I have left?"))
    assert decision.action is ActionType.DEFER
    assert decision.reason_code is ReasonCode.OUT_OF_SCOPE
    assert len(llm.prompts) == 1  # answer stage never reached


def test_conflict_flag_defers_conflicting_policies(corpus: PolicyCorpus) -> None:
    llm = FakeLLM(answer='{"answer": "", "citations": [], "conflict": true}')
    pipe = _pipeline(corpus, llm=llm, retrieved=[_rsec(corpus, "POL-06", "6.3", 0.8)])
    decision = pipe.process(Ticket(id="T-046", body="Need Restricted on BYOD after hours?"))
    assert decision.action is ActionType.DEFER
    assert decision.reason_code is ReasonCode.CONFLICTING_POLICIES


def test_unsupported_citation_defers_low_confidence(corpus: PolicyCorpus) -> None:
    # The model cites a real section that was NOT retrieved -> grounding rejects it.
    llm = FakeLLM(
        answer='{"answer": "Use Cisco AnyConnect.",'
        ' "citations": [{"policy_id": "POL-02", "section": "2.1"}], "conflict": false}'
    )
    pipe = _pipeline(corpus, llm=llm, retrieved=[_rsec(corpus, "POL-01", "1.3", 0.9)])
    decision = pipe.process(Ticket(id="T-x", body="which vpn client?"))
    assert decision.action is ActionType.DEFER
    assert decision.reason_code is ReasonCode.LOW_CONFIDENCE


def test_citation_normalization(corpus: PolicyCorpus) -> None:
    # Lowercased policy_id and a stray '§' on the section must still match the corpus.
    llm = FakeLLM(
        answer='{"answer": "Locked after 5 attempts.",'
        ' "citations": [{"policy_id": "pol-01", "section": "§1.4"}], "conflict": false}'
    )
    pipe = _pipeline(corpus, llm=llm, retrieved=[_rsec(corpus, "POL-01", "1.4", 0.9)])
    decision = pipe.process(Ticket(id="T-001", body="how many attempts before lockout?"))
    assert decision.action is ActionType.RESOLVE
    assert [str(c) for c in decision.citations] == ["POL-01 §1.4"]


def test_empty_answer_with_valid_citation_defers(corpus: PolicyCorpus) -> None:
    # An empty (whitespace-only) answer paired with an otherwise-valid, retrieved citation must
    # NOT resolve — that would post a bare "Source: ..." comment. It defers LOW_CONFIDENCE.
    llm = FakeLLM(
        answer='{"answer": "   ", "citations": [{"policy_id": "POL-01", "section": "1.4"}],'
        ' "conflict": false}'
    )
    pipe = _pipeline(corpus, llm=llm, retrieved=[_rsec(corpus, "POL-01", "1.4", 0.9)])
    decision = pipe.process(Ticket(id="T-001", body="how many attempts before lockout?"))
    assert decision.action is ActionType.DEFER
    assert decision.reason_code is ReasonCode.LOW_CONFIDENCE
    assert not decision.answer
