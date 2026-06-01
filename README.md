# Helix IT Helpdesk Agent

A grounded AI agent for **Helix Industries** that monitors a Jira Service Desk project,
**auto-resolves** the IT-policy questions it can answer confidently — citing a specific
policy section — and **defers** everything else to a human with a structured reason code.
The 10 IT policies are the *only* authorized knowledge source; the agent refuses to answer
from prior knowledge.

> Forward Deployed Engineer take-home. Brief in [`input/`](input/); eval report in
> [`docs/eval_report.md`](docs/eval_report.md).

## Results

End-to-end run against a live Jira project (`jira-agent eval-live`, semantic embeddings,
`claude-sonnet-4-6`), scored against ground truth on all 50 tickets:

| Dimension | Result |
| --- | --- |
| Action accuracy (resolve vs defer) | **50/50** |
| DEFER accuracy (correct reason code) | **25/25 (100%)** |
| **False positives** (resolved a DEFER ticket) | **0** |
| RESOLVE — exact citation | **21/25 (84%)** |
| RESOLVE — all required citations present | **24/25 (96%)** |
| Weighted error (3×FP + missed) | **0.0** |

The 4 imperfect RESOLVEs are over-cites/adjacent-section judgment calls (the *required*
citation is present in all but one); we stop there rather than overfit prompts to the eval set.

## Architecture

A ticket reaches RESOLVE only by clearing every gate; any failure falls through to DEFER.

```mermaid
flowchart TD
    A([New Jira ticket]) --> T{"Triage<br/>safety &amp; scope (LLM)"}
    T -->|"red flag"| D["DEFER<br/>reason code"]
    T -->|"clean"| R["Retrieve top-k<br/>policy sections<br/>(TF-IDF or embeddings)"]
    R --> F{"Score below<br/>floor?"}
    F -->|"yes"| D
    F -->|"no"| G{"Ground &amp; verify<br/>answer only from<br/>retrieved sections"}
    G -->|"abstain / unsupported<br/>citation / conflict"| D
    G -->|"grounded &amp; verified"| RES["RESOLVE<br/>cite POL-XX §Y.Z"]
    RES --> AR["Comment · auto-resolved label<br/>· transition to Resolved"]
    D --> HU["Comment · needs-human<br/>· reason:CODE label · route to human"]

    classDef resolve fill:#dcfce7,stroke:#16a34a,color:#14532d;
    classDef defer fill:#fef3c7,stroke:#d97706,color:#7c2d12;
    classDef gate fill:#e0f2fe,stroke:#0284c7,color:#0c4a6e;
    class RES,AR resolve;
    class D,HU defer;
    class T,F,G gate;
```

Reason codes the agent can assign: `ACTIVE_INCIDENT`, `PROMPT_INJECTION`, `HOSTILE_TONE`,
`PII_REQUEST`, `OUT_OF_SCOPE`, `WRONG_TENANT`, `WRONG_INTENT`, `PRIVILEGED_ACCESS`,
`SPECULATIVE`, `NONEXISTENT_POLICY`, `LOW_CONFIDENCE`, `CONFLICTING_POLICIES`.

DEFER posts a reason-code comment, applies `needs-human` + a `reason:<CODE>` label, and leaves
the ticket for a person. The layers (LLM, retriever, Jira) sit behind small interfaces and are
swappable. Self-serve "yes you can" answers *instruct* the user — the agent never performs a
privileged action itself.

## Prompt strategy

- **Two stages, two prompts.** Triage sees the raw ticket + a *catalog of real policy titles*
  (so it can flag a cited-but-nonexistent policy or another tenant). The answer stage sees
  *only the retrieved sections* and must answer from them or abstain — narrowing the context is
  the first defense against hallucination.
- **Untrusted input.** Ticket text is always wrapped in `<ticket>…</ticket>` and labelled
  untrusted; the model is told never to follow instructions inside it (prompt-injection defense).
- **Precise, contrastive triage.** Default-to-proceed, with sharp boundaries so ordinary policy
  questions aren't over-flagged ("when am I eligible for a laptop" is not troubleshooting;
  "if I leave, will my phone be wiped" is not speculative).
- **Strict JSON** out of both stages, with a parse-retry and conservative fall-back to DEFER.

## How grounding is enforced

Resolution is gated by code, not trust: after the LLM answers, `verify_citations` confirms
every cited `POL-XX §Y.Z` **(a) exists** in the corpus and **(b) was among the sections
retrieved** for this ticket. Either check failing → DEFER (`LOW_CONFIDENCE`). The model cannot
resolve a ticket on a section it never saw, nor invent one.

> **Confidence ≠ retrieval score.** Calibrating on the 50 tickets showed raw similarity scores
> overlap completely between RESOLVE and DEFER, so the numeric gate is only a low *floor*; the
> real decision is triage + grounded abstention + citation verification.

## Extensibility (the seams)

- **Onboard policy #11:** drop a `POL-11.md` file in `data/policies/`. No code change — the
  loader, triage catalog, and retriever pick it up automatically.
- **New customer (healthcare vs fintech):** swap the `data/policies/` corpus; the pipeline and
  the 12 reason codes are domain-agnostic. `policies_dir` is config-driven for per-tenant setups.
- **New language:** the retriever is swappable (use a multilingual embedding model) and the
  prompts can be told to answer in the ticket's language or DEFER; today non-grounded/unsure
  cases defer safely.
- **Better retrieval:** `AGENT_RETRIEVER=local` swaps TF-IDF for semantic embeddings behind the
  same `Retriever` protocol — this is what lifted retrieval recall to 25/25.

## Setup & usage

```bash
uv sync --extra local-embeddings     # default retriever is semantic embeddings (AGENT_RETRIEVER=local)
                                     # PyTorch-free? plain `uv sync` + set AGENT_RETRIEVER=tfidf
cp .env.example .env                 # fill ANTHROPIC_API_KEY + Jira creds (kept out of git)

uv run jira-agent policies           # list the loaded corpus (no creds needed)
uv run jira-agent seed               # load the 50 eval tickets into Jira (idempotent)
uv run jira-agent run --once         # process the queue once (AGENT_DRY_RUN=true by default)
uv run jira-agent eval               # offline: score all 50 vs ground truth → reports/
uv run jira-agent eval-live          # integration test: score against tickets read from Jira
```

Engineering: typed (pydantic, mypy `--strict`), linted (ruff), 46 tests; Jira REST client with
explicit timeouts + bounded retries; structured logging; secrets only via `.env`.

## What I'd harden before production

- **Durable processed-ticket store** (replace the in-memory `_seen` set) for idempotency across
  restarts; handle resurrected/duplicate tickets.
- **Jira/JSM:** rate-limit backoff tuning, and customer-portal-visible replies via the
  servicedesk API (today the agent posts internal comments).
- **Human-in-the-loop** review queue for low-confidence resolves; **per-tenant** policy isolation
  and secrets management.
- **Eval CI gate** that fails the build on accuracy/false-positive regressions; periodic
  re-calibration as policies change.
