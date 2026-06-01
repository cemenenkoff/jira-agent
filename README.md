# Helix IT Helpdesk Agent

A grounded AI agent for **Helix Industries** that monitors a Jira Service Desk
project, **auto-resolves** the IT-policy questions it can answer confidently —
citing a specific policy section — and **defers** everything else to a human
with a structured reason code.

> Built for the Forward Deployed Engineer take-home. The assignment brief lives
> in [`input/`](input/).

---

## Why it's built this way

The grading rubric is the design spec, and two clauses drive every decision:

1. **Restraint is asymmetric.** Resolving a ticket that should have been deferred
   costs **~3× a missed resolve.** So the pipeline is *conservative by
   construction*: a ticket is resolved only when (a) triage finds no
   safety/scope red flag, (b) retrieval clears a confidence threshold, and
   (c) the generated answer's citation is **verified to exist** in the corpus.
   Any failure → `DEFER`.

2. **Grounding is verified, not trusted.** Every `RESOLVE` must cite a real
   `POL-XX §Y.Z`. We don't take the model's word for it — a post-generation
   check confirms each cited section exists and was actually retrieved. The 10
   policies are the *only* authorized knowledge source; the agent refuses to
   answer from prior knowledge.

## Pipeline

```
                       ┌──────────────┐
  Jira new ticket ───► │   TRIAGE     │  safety + scope classification
                       │ (classifier) │  → ACTIVE_INCIDENT, PROMPT_INJECTION,
                       └──────┬───────┘    HOSTILE_TONE, PII_REQUEST, OUT_OF_SCOPE,
                              │             WRONG_TENANT, PRIVILEGED_ACCESS, …
                   red flag?  │ yes ─────────────────────────────► DEFER (reason code)
                              │ no
                       ┌──────▼───────┐
                       │  RETRIEVE    │  score top-k policy sections
                       └──────┬───────┘
                   score <    │ yes ─────────────────────────────► DEFER (LOW_CONFIDENCE)
                   floor?     │ no   (low floor — catches no-overlap retrieval only)
                       ┌──────▼───────┐
                       │   GROUND     │  LLM answers ONLY from retrieved sections,
                       │  + VERIFY    │  or abstains; citation must exist & be retrieved
                       └──────┬───────┘
                  abstain /   │ yes ─────────────────────────────► DEFER (LOW_CONFIDENCE)
                  unsupported │            (or CONFLICTING_POLICIES on conflict)
                  / conflict? │ no
                              ▼
                           RESOLVE  (grounded answer + POL-XX §Y.Z citation)
```

> **Why a *floor*, not a score threshold?** Calibrating against the 50-ticket set
> showed raw TF-IDF top-scores overlap completely between RESOLVE (0.15–0.46) and
> DEFER (0.00–0.65) tickets — there is no cutoff that separates them. So the score
> gate is only a low floor for *no lexical overlap at all*; the real RESOLVE/DEFER
> decision is triage + the LLM grounding/abstention + citation verification.

Acting on Jira is the last step: `RESOLVE` posts the answer, applies the
`auto-resolved` label, and transitions the ticket; `DEFER` posts the reason-code
comment, applies `needs-human` + a per-reason label, and leaves it for a person.

## Repository layout

```
data/
  policies/            # POL-01..POL-10 as drop-in Markdown (onboarding policy #11 = add a file)
  tickets/             # eval_tickets.json — the 50-ticket eval set + structured ground truth
src/jira_agent/
  config.py            # typed settings from env (.env), secrets never hard-coded
  models.py            # Ticket, Policy, Citation, ReasonCode, Decision, EvalRecord
  reason_codes.py      # the 12 DEFER reason codes + descriptions
  logging_setup.py     # structured logging
  policies/            # loader.py (parse Markdown) + retriever.py (score + threshold)
  triage/              # classifier.py — safety/scope detection
  llm/                 # base.py (provider interface), anthropic_client.py, prompts.py
  jira/                # client.py (REST + retry/timeout), actions.py (resolve/defer)
  agent/               # pipeline.py (orchestration), grounding.py (citation verification)
  eval/                # harness.py (replay 50 tickets), report.py (CSV + metrics)
  runner.py            # the monitoring loop
  cli.py               # `jira-agent run | eval | seed | policies`
tests/                 # dataset integrity, policy loader, models
reports/               # generated eval output (git-ignored)
```

## Setup

```bash
# 1. Install (uv is used for env + deps)
uv sync

# 2. Configure secrets
cp .env.example .env        # then edit .env  (PowerShell: Copy-Item .env.example .env)

# 3. Run the offline eval over all 50 tickets (no Jira needed)
uv run jira-agent eval

# 4. Dry-run the live agent against your Jira queue (AGENT_DRY_RUN=true logs, doesn't write)
uv run jira-agent run
```

## Status

End-to-end working against a live Jira project (dry-run). `jira-agent seed` loads
the 50 eval tickets; `jira-agent run` triages, retrieves, grounds, and decides each.
Restraint is strong (0 false positives on the 25 DEFER tickets in the first live run).
RESOLVE recall is being tuned — see the lexical-retrieval limitation below.

## Design decisions

- **Stack:** Python · `uv` · pydantic · Anthropic Claude (swappable LLM layer).
- **Confidence ≠ retrieval score.** Calibration showed raw TF-IDF scores don't
  separate RESOLVE from DEFER, so the score is only a low floor; triage + LLM
  grounding/abstention + citation verification make the real decision.
- **Retrieval:** hybrid RAG. A TF-IDF baseline ships with zero API keys so the
  eval runs offline; a semantic embeddings backend (Voyage or local) is an opt-in
  extra and the planned fix for the lexical misses below.
- **Self-serve actions:** the agent *instructs* users on self-serve steps rather
  than performing privileged actions itself — safer default, documented seam.

## What we'd harden before production

- **Semantic retrieval.** TF-IDF misses a few RESOLVE tickets on pure vocabulary
  gaps (e.g. "shut my laptop down if hacked" vs POL-09 §9.2 "do NOT power off").
  Embeddings (the `voyage` / `local-embeddings` extras) would close these.
- Durable processed-ticket store (replace the in-memory `_seen` set) for idempotency.
- JIRA-side: rate-limit/backoff tuning, and JSM portal-visible replies via the
  servicedesk API (today we post internal comments).
- Human-in-the-loop review queue for low-confidence resolves; per-tenant policy
  isolation; an eval CI gate that fails the build on accuracy regressions.
