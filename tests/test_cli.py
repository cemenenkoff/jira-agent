from __future__ import annotations

from typer.testing import CliRunner

from jira_agent import cli
from jira_agent.config import Settings

runner = CliRunner()


def test_policies_lists_corpus_without_credentials(monkeypatch) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: Settings(_env_file=None))
    result = runner.invoke(cli.app, ["policies"])
    assert result.exit_code == 0
    assert "POL-01" in result.stdout


def test_eval_exits_1_when_llm_credentials_missing(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(cli, "get_settings", lambda: Settings(_env_file=None))
    result = runner.invoke(cli.app, ["eval"])
    assert result.exit_code == 1
