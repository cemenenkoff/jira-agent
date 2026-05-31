from __future__ import annotations

from jira_agent.policies.loader import PolicyCorpus
from jira_agent.policies.retriever import TfidfRetriever


def test_retrieve_returns_scored_sections(corpus: PolicyCorpus) -> None:
    retriever = TfidfRetriever(corpus)
    results = retriever.retrieve("which VPN client should I install?", k=3)
    assert len(results) == 3
    # Scores are sorted descending and within [0, 1].
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)
    assert all(0.0 <= s <= 1.0 for s in scores)
    # The VPN client question should surface a POL-02 section near the top.
    assert any(r.section.policy_id == "POL-02" for r in results[:2])


def test_empty_query_returns_nothing(corpus: PolicyCorpus) -> None:
    assert TfidfRetriever(corpus).retrieve("   ") == []
