# 0001 — Retrieval score is a floor, not the RESOLVE/DEFER gate

- **Status:** Accepted (2026-06-01)

## Context

The agent must DEFER when it can't confidently answer. The first design gated RESOLVE on a
retrieval-score threshold (`AGENT_CONFIDENCE_THRESHOLD = 0.45`): if the top policy section scored
below it, defer with `LOW_CONFIDENCE`. The first live run deferred ~24 of 25 RESOLVE tickets — a
`LOW_CONFIDENCE` flood.

Offline calibration over the 50-ticket benchmark showed **the top retrieval score does not
separate the two classes**. With TF-IDF, RESOLVE tickets scored 0.15–0.46 while DEFER tickets
scored 0.00–0.65 — fully overlapping; several DEFER tickets scored *above* the highest RESOLVE.
Semantic embeddings raised all scores but kept the overlap (DEFER tickets are usually *about*
policy topics — they just shouldn't be auto-answered). No cutoff cleanly divides resolve-able
from defer-able tickets.

## Decision

Treat the numeric score as a **low floor** (`AGENT_CONFIDENCE_THRESHOLD = 0.05`) that only catches
near-zero / no-lexical-overlap retrieval. The real RESOLVE/DEFER decision is the combination of:

1. **Triage** — LLM safety/scope gate (runs before retrieval).
2. **Grounded abstention** — the answer stage answers strictly from the retrieved sections or
   returns an empty answer.
3. **Citation verification** — `verify_citations` requires every cited section to *exist* and to
   have been *retrieved*; otherwise defer.

## Consequences

- RESOLVE recovered from 1/25 to 20+/25 with **zero false positives** retained.
- We report a **dual citation metric** (exact vs. all-required-present) to stay honest about the
  remaining errors.
- The decision now leans on the LLM abstaining appropriately; the citation-verification gate is
  the backstop that makes that safe.
- The floor rarely fires in practice — it's kept as a guard for degenerate (no-overlap) retrieval.
- Do **not** "fix" missed resolves by raising the floor; it re-introduces the flood without
  improving precision.
