from __future__ import annotations

from jira_agent.agent.grounding import verify_citations
from jira_agent.models import Citation, RetrievedSection
from jira_agent.policies.loader import PolicyCorpus


def _retrieved(corpus: PolicyCorpus, policy_id: str, section: str) -> RetrievedSection:
    sec = corpus.get_section(policy_id, section)
    assert sec is not None
    return RetrievedSection(section=sec, score=0.9)


def test_valid_citation_passes(corpus: PolicyCorpus) -> None:
    retrieved = [_retrieved(corpus, "POL-01", "1.4")]
    result = verify_citations([Citation(policy_id="POL-01", section="1.4")], corpus, retrieved)
    assert result.ok


def test_nonexistent_section_fails(corpus: PolicyCorpus) -> None:
    retrieved = [_retrieved(corpus, "POL-01", "1.4")]
    result = verify_citations([Citation(policy_id="POL-01", section="1.9")], corpus, retrieved)
    assert not result.ok


def test_unretrieved_citation_fails(corpus: PolicyCorpus) -> None:
    # Cites a real section that was NOT among the retrieved set -> possible hallucination.
    retrieved = [_retrieved(corpus, "POL-01", "1.4")]
    result = verify_citations([Citation(policy_id="POL-02", section="2.1")], corpus, retrieved)
    assert not result.ok


def test_empty_citations_fail(corpus: PolicyCorpus) -> None:
    assert not verify_citations([], corpus, []).ok
