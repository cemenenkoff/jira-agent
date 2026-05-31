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
                   threshold? │ no
                       ┌──────▼───────┐
                       │   GROUND     │  LLM answers ONLY from retrieved sections
                       │  + VERIFY    │  → citation must exist & be supported
                       └──────┬───────┘
                  unsupported │ yes ─────────────────────────────► DEFER (LOW_CONFIDENCE)
                  / conflict? │            (or CONFLICTING_POLICIES)
                              │ no
                              ▼
                           RESOLVE  (grounded answer + POL-XX §Y.Z citation)
```

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

🚧 **Scaffolding.** Data layer (policies + eval set), domain models, config, and
module interfaces are in place; the triage / retrieval / grounding / Jira logic
is stubbed and filled in next. See module `TODO`s for the seams.

## Design decisions (so far)

- **Stack:** Python · `uv` · pydantic · Anthropic Claude (swappable LLM layer).
- **Retrieval:** hybrid RAG. A TF-IDF baseline ships with zero API keys so the
  eval runs offline; an embeddings backend (Voyage or local) is an opt-in extra.
- **Self-serve actions:** the agent *instructs* users on self-serve steps rather
  than performing privileged actions itself — safer default, documented seam.

## What we'd harden before production

Tracked in the README's final section as the build progresses (idempotency &
dedup of tickets, secret management, JIRA API rate-limit/backoff, human-in-the-loop
review of low-confidence resolves, per-tenant policy isolation, eval CI gate).
