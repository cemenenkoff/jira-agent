from __future__ import annotations

import pytest

from jira_agent.config import Settings
from jira_agent.policies.loader import PolicyCorpus
from jira_agent.policies.retriever import TfidfRetriever, build_retriever


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


def test_default_retriever_is_local() -> None:
    # The shipped default leads with the best (semantic embeddings) retriever.
    assert Settings.model_fields["agent_retriever"].default == "local"


def test_build_retriever_tfidf(corpus: PolicyCorpus) -> None:
    retriever = build_retriever(Settings(agent_retriever="tfidf"), corpus)
    assert isinstance(retriever, TfidfRetriever)


def test_build_retriever_rejects_unknown(corpus: PolicyCorpus) -> None:
    # Unknown kinds fail fast rather than silently picking a default.
    with pytest.raises(ValueError, match="AGENT_RETRIEVER"):
        build_retriever(Settings(agent_retriever="bogus"), corpus)
