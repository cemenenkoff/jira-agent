from __future__ import annotations

from jira_agent.models import ReasonCode, Ticket
from jira_agent.policies.loader import PolicyCorpus
from jira_agent.triage.classifier import TriageClassifier

from .fakes import FakeLLM


def _classify(corpus: PolicyCorpus, triage_json: str) -> object:
    classifier = TriageClassifier(FakeLLM(triage=triage_json), corpus)
    return classifier.classify(Ticket(id="T-x", body="anything"))


def test_null_reason_code_means_proceed(corpus: PolicyCorpus) -> None:
    result = _classify(corpus, '{"reason_code": null, "rationale": "looks fine"}')
    assert result.reason_code is None


def test_red_flag_is_returned(corpus: PolicyCorpus) -> None:
    result = _classify(corpus, '{"reason_code": "OUT_OF_SCOPE", "rationale": "HR question"}')
    assert result.reason_code is ReasonCode.OUT_OF_SCOPE
    assert result.rationale == "HR question"


def test_post_retrieval_codes_are_downgraded_to_proceed(corpus: PolicyCorpus) -> None:
    # Triage must not pre-empt the retrieval-stage decisions.
    assert _classify(corpus, '{"reason_code": "LOW_CONFIDENCE"}').reason_code is None
    assert _classify(corpus, '{"reason_code": "CONFLICTING_POLICIES"}').reason_code is None


def test_parse_failure_defers_conservatively(corpus: PolicyCorpus) -> None:
    result = _classify(corpus, "the model rambled and returned no json")
    assert result.reason_code is ReasonCode.LOW_CONFIDENCE


def test_unknown_code_defers_conservatively(corpus: PolicyCorpus) -> None:
    result = _classify(corpus, '{"reason_code": "BANANA"}')
    assert result.reason_code is ReasonCode.LOW_CONFIDENCE


def test_triage_prompt_includes_policy_catalog(corpus: PolicyCorpus) -> None:
    classifier = TriageClassifier(FakeLLM(), corpus)
    # The catalog lets triage detect NONEXISTENT_POLICY / WRONG_TENANT.
    assert "POL-01: Password & Authentication Policy" in classifier._system
