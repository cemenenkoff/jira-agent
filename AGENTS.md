# AGENTS.md

Guidance for an agent working in this repo. Keep it current; favor signal over completeness.

## 1. Project overview

A grounded AI agent that monitors a **Jira Service Desk** project, **auto-resolves** IT-policy
questions it can answer from a fixed set of 10 policies (citing the exact section), and
**defers** everything else to a human with a structured reason code. The 10 policies are the
*only* authorized knowledge source — it refuses to answer from prior knowledge. A self-directed
learning lab. Full design write-up: [`README.md`](README.md); results: [`docs/eval_report.md`](docs/eval_report.md).

## 2. Architecture & layout

Pipeline (in `agent/pipeline.py::AgentPipeline.process`), conservative by design — a ticket
RESOLVEs only by clearing every gate; any failure DEFERs:

`triage (LLM safety/scope) → retrieve top-k → confidence floor → grounded answer (LLM, only from
retrieved sections, or abstain) → verify citations → RESOLVE | DEFER → act on Jira`

```
data/policies/POL-01..10.md   drop-in Markdown (YAML front-matter + `### <section>`); add a file = new policy
data/tickets/eval_tickets.json 50-ticket eval set with structured ground truth
src/jira_agent/
  config.py        Settings (pydantic-settings, reads .env); require_jira()/require_llm()
  models.py        ActionType, ReasonCode (12), Citation, Policy/PolicySection, Ticket, Decision, Eval*
  reason_codes.py  REASON_CODE_DESCRIPTIONS; RETRIEVAL_REASON_CODES (LOW_CONFIDENCE/CONFLICTING_POLICIES)
  policies/        loader.py (PolicyCorpus) · retriever.py (Retriever protocol, TfidfRetriever,
                   LocalEmbeddingRetriever, build_retriever factory)
  triage/          classifier.py (TriageClassifier → reason code or None)
  llm/             base.py (LLMClient protocol) · anthropic_client.py · prompts.py · parsing.py
  jira/            client.py (REST, retry/timeout) · actions.py (resolve/defer) · mapping.py
                   (issue→Ticket) · seed.py (idempotent ticket seeding)
  agent/           pipeline.py (orchestration) · grounding.py (verify_citations)
  eval/            harness.py (offline) · live.py (against real Jira) · report.py (metrics + CSV/MD)
  runner.py        AgentRunner poll loop · cli.py  (typer: policies|seed|run|eval|eval-live)
tests/             pytest suite; fakes.py (FakeLLM, FakeRetriever, FakeJira)
docs/              eval_report.{md,csv} (snapshot) · adr/ (decision records) · media/ (demo video)
reports/           generated eval output (git-ignored)
```

Swappable layers sit behind small Protocols: `LLMClient` (`llm/base.py`) and `Retriever`
(`policies/retriever.py`). The agent **instructs** users on self-serve actions — it never
performs privileged actions itself.

## 3. Build / test / run

`uv` manages env + deps. The default retriever is semantic embeddings (`local`), which needs the
extra; tests/lint do not.

```bash
uv sync --extra local-embeddings   # full install (PyTorch); or plain `uv sync` + AGENT_RETRIEVER=tfidf
uv sync --extra dev                # dev tooling (pytest/ruff/mypy)
uv run pytest -q                   # full suite (uses fakes/tfidf — no torch needed)
uv run ruff format src tests && uv run ruff check src tests
uv run mypy src                    # strict; src only (tests are not type-checked)
cp .env.example .env               # then fill ANTHROPIC_API_KEY + Jira creds
uv run jira-agent policies | seed | run [--once] | eval | eval-live
```

## 4. Conventions

- Python ≥3.11, `from __future__ import annotations`, full type hints; `StrEnum` for enums.
- ruff (line length 100) + mypy `--strict` must pass; pydantic for domain models; Protocols for
  swappable backends. Match existing module style.
- **Secrets only via `.env`** (git-ignored) — never hard-code.
- Commits: imperative subject + a "why" body, ending with the trailer
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Work happens on `main`.
  **Ask before every `git push`.**

## 5. Gotchas

- **Shell is PowerShell on Windows.** `git push` prints to stderr and PowerShell renders it as a
  red "RemoteException" — check the exit code, not the color (exit 0 = success).
- **Commit messages: use `git commit -F tmp/commitmsg.txt`** (write the message with the Write
  tool). Inline PowerShell here-strings mangle multi-line messages with special chars.
- **`AGENT_CONFIDENCE_THRESHOLD` is a low *floor* (0.05), not the decision gate.** Calibration
  showed raw retrieval scores overlap between RESOLVE/DEFER; the real gate is triage + grounded
  abstention + `verify_citations`. Don't "fix" it by raising it.
- **Default `AGENT_RETRIEVER=local`** needs `--extra local-embeddings` (torch). Missing → a
  friendly RuntimeError pointing at the extra or `tfidf`.
- **`.env` overrides code defaults.** Changing a default in `config.py` has no effect if `.env`
  sets that variable — update both.
- **Jira JQL `labels NOT IN (...)` excludes EMPTY-label issues** — the runner uses
  `labels IS EMPTY OR labels NOT IN (...)` so hand-filed (label-less) tickets are seen.
- Seeded tickets carry an `eval-<id>` label (used by `eval-live` to join to ground truth); `seed`
  is idempotent. Live project key is `ITSD`.
- History rewrites use `git-filter-repo` (`uv tool install git-filter-repo`; ensure it's on PATH).

## 6. Current state & key decisions

**State:** feature-complete and working end-to-end against live Jira. Latest `eval-live`
(embeddings, `claude-sonnet-4-6`): action **50/50**, DEFER **25/25**, **0 false positives**,
RESOLVE **21/25 exact / 24/25 required-citation**, weighted_error **0**. Full per-ticket results:
[`docs/eval_report.md`](docs/eval_report.md). Suite currently 49 tests; ruff + mypy clean.

**Done:** policies + eval set, full pipeline (triage/retrieve/ground/verify), TF-IDF + embeddings
retrievers, Jira client/seed/actions, offline + live eval, README (≤2pp), eval-report snapshot,
and a demo-video embed in the README.

**Next / open:** user records the demo video (`docs/media/jira-agent-demo.mov`); confirm the
README Mermaid diagram renders on GitHub.

**Key decisions (with reasoning):**
- *Restraint is asymmetric* (we weight a false-positive resolve ~3× a missed resolve) → bias
  to DEFER; grounding/triage are conservative.
- *Grounding verified, not trusted* → `verify_citations` requires each cited section to exist AND
  have been retrieved.
- *Floor, not threshold* (see Gotchas) — an eval-driven choice, not a guess.
- *Default to embeddings* — lifted retrieval recall 21→25/25; `tfidf` kept as a no-torch fallback.
- *Stopped tuning the last 4 citations* — they're over-cite/adjacent judgment calls; chasing them
  would overfit the 50-ticket set.

> The two data-backed decisions (**floor-not-threshold**, **default-to-embeddings**) are recorded
> as ADRs in [`docs/adr/`](docs/adr/).
