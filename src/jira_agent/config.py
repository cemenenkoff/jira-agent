"""Typed settings, loaded from environment / `.env`. No secrets are hard-coded."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# repo root = .../jira-agent  (this file is src/jira_agent/config.py)
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── Anthropic (LLM) ──────────────────────────────────────────────
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-6"

    # ── Jira ─────────────────────────────────────────────────────────
    jira_base_url: str | None = None
    jira_email: str | None = None
    jira_api_token: str | None = None
    jira_project_key: str = "ITSD"

    # ── Agent behavior ───────────────────────────────────────────────
    # A LOW floor, not the primary gate: raw retrieval scores (TF-IDF or
    # embeddings) don't separate resolve-able from defer-able tickets (they
    # overlap), so the real confidence comes from the LLM grounding + citation
    # verification. This only catches near-zero retrieval (no overlap at all).
    # See docs/adr/0001-confidence-floor-not-threshold.md.
    agent_confidence_threshold: float = 0.05
    # How many policy sections to retrieve and show the answering LLM.
    agent_retrieval_k: int = 8
    # Which retriever to use: "local" (semantic embeddings via sentence-transformers;
    # needs the local-embeddings extra — the default, best accuracy) or "tfidf"
    # (lexical baseline, no extra deps, for a PyTorch-free install).
    agent_retriever: str = "local"
    agent_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    agent_poll_interval_seconds: int = 30
    agent_dry_run: bool = True
    agent_resolved_label: str = "auto-resolved"
    agent_defer_label: str = "needs-human"

    # ── Observability ────────────────────────────────────────────────
    log_level: str = "INFO"
    log_format: str = "console"

    # ── Data paths ───────────────────────────────────────────────────
    policies_dir: Path = REPO_ROOT / "data" / "policies"
    tickets_file: Path = REPO_ROOT / "data" / "tickets" / "eval_tickets.json"
    reports_dir: Path = REPO_ROOT / "reports"

    def require_jira(self) -> None:
        """Raise a clear error if Jira credentials are missing."""
        missing = [
            name
            for name, val in {
                "JIRA_BASE_URL": self.jira_base_url,
                "JIRA_EMAIL": self.jira_email,
                "JIRA_API_TOKEN": self.jira_api_token,
            }.items()
            if not val
        ]
        if missing:
            raise RuntimeError(
                f"Missing Jira settings: {', '.join(missing)}. Copy .env.example to .env."
            )

    def require_llm(self) -> None:
        if not self.anthropic_api_key:
            raise RuntimeError("Missing ANTHROPIC_API_KEY. Copy .env.example to .env.")


def get_settings() -> Settings:
    return Settings()
