"""Retrieval over the policy corpus.

The pipeline depends only on the `Retriever` protocol, so the embedding-backed
retriever (Voyage / local) can be swapped in later without touching the agent.
The TF-IDF retriever is the default: zero API keys, runs offline, and gives a
real similarity score for the LOW_CONFIDENCE threshold on a ~60-section corpus.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ..models import RetrievedSection
from .loader import PolicyCorpus


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
