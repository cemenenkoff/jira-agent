"""Retrieval over the policy corpus.

The pipeline depends only on the `Retriever` protocol, so the embedding-backed
retriever (Voyage / local) can be swapped in later without touching the agent.
The TF-IDF retriever is the default: zero API keys, runs offline, and gives a
real similarity score for the LOW_CONFIDENCE threshold on a ~60-section corpus.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ..models import RetrievedSection
from .loader import PolicyCorpus

if TYPE_CHECKING:
    from ..config import Settings


class Retriever(Protocol):
    def retrieve(self, query: str, k: int = 5) -> list[RetrievedSection]:
        """Return the top-k policy sections for a query, scored 0..1 (desc)."""
        ...


class TfidfRetriever:
    def __init__(self, corpus: PolicyCorpus) -> None:
        self._sections = corpus.sections
        # Prepend the citation so a query naming a policy id gets a lexical boost.
        docs = [f"{s.policy_id} {s.section} {s.text}" for s in self._sections]
        self._vectorizer = TfidfVectorizer(stop_words="english")
        self._matrix = self._vectorizer.fit_transform(docs)

    def retrieve(self, query: str, k: int = 5) -> list[RetrievedSection]:
        if not query.strip():
            return []
        q_vec = self._vectorizer.transform([query])
        scores = cosine_similarity(q_vec, self._matrix)[0]
        top_idx = np.argsort(scores)[::-1][:k]
        return [
            RetrievedSection(section=self._sections[i], score=float(scores[i])) for i in top_idx
        ]


class LocalEmbeddingRetriever:
    """Semantic retriever using a local sentence-transformers model (no API key).

    Closes the lexical gaps TF-IDF can't (e.g. "shut my laptop down if hacked" ->
    POL-09 §9.2 "do NOT power off"). Sections are embedded with their policy title for
    extra context; cosine similarity over normalized vectors gives the 0..1 score.
    """

    def __init__(
        self,
        corpus: PolicyCorpus,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    ) -> None:
        from sentence_transformers import SentenceTransformer

        self._sections = corpus.sections
        self._model = SentenceTransformer(model_name)
        docs = []
        for s in self._sections:
            policy = corpus.get_policy(s.policy_id)
            title = policy.title if policy else ""
            docs.append(f"{title} — {s.text}")
        self._embeddings = self._model.encode(
            docs, normalize_embeddings=True, convert_to_numpy=True
        )

    def retrieve(self, query: str, k: int = 5) -> list[RetrievedSection]:
        if not query.strip():
            return []
        q_vec = self._model.encode([query], normalize_embeddings=True, convert_to_numpy=True)[0]
        scores = self._embeddings @ q_vec  # cosine, vectors are normalized
        top_idx = np.argsort(scores)[::-1][:k]
        return [
            RetrievedSection(section=self._sections[i], score=float(scores[i])) for i in top_idx
        ]


def build_retriever(settings: Settings, corpus: PolicyCorpus) -> Retriever:
    """Select the retriever from config. Default TF-IDF; opt into semantic embeddings."""
    kind = settings.agent_retriever.lower()
    if kind == "tfidf":
        return TfidfRetriever(corpus)
    if kind in {"local", "local-embeddings", "embeddings"}:
        try:
            return LocalEmbeddingRetriever(corpus, settings.agent_embedding_model)
        except ImportError as exc:
            raise RuntimeError(
                "AGENT_RETRIEVER=local needs the embeddings extra. Run "
                "`uv sync --extra local-embeddings`, or set AGENT_RETRIEVER=tfidf for a "
                "PyTorch-free run."
            ) from exc
    raise ValueError(
        f"Unknown AGENT_RETRIEVER={settings.agent_retriever!r} (use 'tfidf' or 'local')"
    )
