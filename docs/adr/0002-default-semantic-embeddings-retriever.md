# 0002 — Default to the local semantic-embeddings retriever

- **Status:** Accepted (2026-06-01)

## Context

The TF-IDF baseline retriever missed RESOLVE tickets on pure vocabulary gaps — e.g. "shut my
laptop down if hacked" never lexically matches POL-09 §9.2 "do NOT power off the device."
Measured over the benchmark, TF-IDF recall@8 was 21/25: for 4 tickets the ground-truth section
was never retrieved, so the agent either deferred or cited a plausible-but-wrong neighbor.

Retrieval sits behind a `Retriever` protocol (`policies/retriever.py`), so the backend is
swappable without touching the pipeline.

## Decision

Default `AGENT_RETRIEVER=local`: a local `sentence-transformers` model
(`all-MiniLM-L6-v2`) that embeds each policy section together with its policy title and ranks by
cosine similarity. Keep `tfidf` as a zero-dependency fallback. `build_retriever` selects by
config; if the embeddings extra isn't installed, it raises a friendly error pointing at
`uv sync --extra local-embeddings` or `AGENT_RETRIEVER=tfidf`.

## Consequences

- Retrieval recall@8 went 21/25 → **25/25** — every required section is now retrieved.
- Remaining citation errors became *over-cites* (the required section is present, plus one
  adjacent) rather than wrong-section misses; false positives stayed at **0**.
- No API key — embeddings run locally/offline, matching the "no secrets, reproducible" goal.
- Cost: a heavy dependency (PyTorch, ~hundreds of MB) gated behind the `local-embeddings` extra;
  the documented default install is `uv sync --extra local-embeddings`. First run downloads the
  model (~80 MB, then cached). `tfidf` remains for a PyTorch-free environment.
- The test suite and lint/type checks deliberately stay on the lightweight path (no torch needed).
