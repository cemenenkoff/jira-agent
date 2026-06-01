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


def test_build_retriever_local_missing_extra_raises_runtime(
    corpus: PolicyCorpus, monkeypatch
) -> None:
    # If sentence-transformers isn't installed, the 'local' branch turns the ImportError into a
    # friendly RuntimeError pointing at the extra / the tfidf fallback.
    import jira_agent.policies.retriever as retriever_mod

    def _boom(*_a: object, **_k: object) -> None:
        raise ImportError("No module named 'sentence_transformers'")

    monkeypatch.setattr(retriever_mod, "LocalEmbeddingRetriever", _boom)
    with pytest.raises(RuntimeError, match="local-embeddings"):
        retriever_mod.build_retriever(Settings(agent_retriever="local"), corpus)


def test_local_embedding_retriever_smoke() -> None:
    # Real semantic retrieval — runs only where the embeddings extra is installed; the suite
    # otherwise stays torch-free. Validates the default retriever's encode/rank path.
    pytest.importorskip("sentence_transformers")
    from jira_agent.models import Policy, PolicySection
    from jira_agent.policies.loader import PolicyCorpus as _Corpus
    from jira_agent.policies.retriever import LocalEmbeddingRetriever

    tiny = _Corpus(
        [
            Policy(
                id="POL-01",
                title="VPN & Remote Access",
                effective="2025",
                owner="Network Security",
                sections=[
                    PolicySection(
                        policy_id="POL-01",
                        section="1.1",
                        text="Use Cisco AnyConnect as the VPN client.",
                    ),
                    PolicySection(
                        policy_id="POL-01",
                        section="1.2",
                        text="MFA is required via Okta for all apps.",
                    ),
                ],
            )
        ]
    )
    out = LocalEmbeddingRetriever(tiny).retrieve("which vpn client should I install?", k=2)
    assert len(out) == 2
    assert out[0].score >= out[1].score
    assert out[0].section.section == "1.1"  # the VPN section ranks first for a VPN query
