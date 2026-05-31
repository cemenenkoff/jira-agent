"""`jira-agent` command-line entrypoint."""

from __future__ import annotations

from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.table import Table

from .config import Settings, get_settings
from .logging_setup import configure_logging
from .policies.loader import PolicyCorpus, load_policies

if TYPE_CHECKING:
    from .agent.pipeline import AgentPipeline

app = typer.Typer(add_completion=False, help="Helix IT helpdesk agent.")
console = Console()


def _corpus(settings: Settings) -> PolicyCorpus:
    return load_policies(settings.policies_dir)


def _build_pipeline(settings: Settings, corpus: PolicyCorpus) -> AgentPipeline:
    """Assemble the pipeline from swappable parts (LLM/retriever/triage)."""
    from .agent.pipeline import AgentPipeline
    from .llm.anthropic_client import AnthropicClient
    from .policies.retriever import TfidfRetriever
    from .triage.classifier import TriageClassifier

    llm = AnthropicClient(settings)
    return AgentPipeline(
        triage=TriageClassifier(llm, corpus),
        retriever=TfidfRetriever(corpus),
        llm=llm,
        corpus=corpus,
        settings=settings,
    )


@app.command()
def policies() -> None:
    """List the loaded policy corpus (no credentials required)."""
    settings = get_settings()
    corpus = _corpus(settings)
    table = Table("Policy", "Title", "Effective", "Sections")
    for p in corpus.policies:
        table.add_row(p.id, p.title, p.effective, str(len(p.sections)))
    console.print(table)
    console.print(f"[bold]{len(corpus)} policies, {len(corpus.sections)} sections[/bold]")


@app.command("eval")
def run_eval() -> None:
    """Run the agent over all 50 eval tickets and write reports/eval_report.{csv,md}."""
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    corpus = _corpus(settings)
    from .eval.harness import evaluate, load_eval_tickets
    from .eval.report import write_report

    tickets = load_eval_tickets(settings.tickets_file)
    try:
        pipeline = _build_pipeline(settings, corpus)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    records = evaluate(pipeline, tickets)
    metrics = write_report(records, settings.reports_dir)
    console.print(metrics)
    console.print(f"[green]Wrote reports to {settings.reports_dir}[/green]")


@app.command()
def run() -> None:
    """Start the live monitoring loop against the configured Jira project."""
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    corpus = _corpus(settings)
    from .jira.actions import TicketActions
    from .jira.client import JiraClient
    from .runner import AgentRunner

    try:
        pipeline = _build_pipeline(settings, corpus)
        jira_cm = JiraClient(settings)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    with jira_cm as jira:
        runner = AgentRunner(
            pipeline=pipeline,
            jira=jira,
            actions=TicketActions(jira, settings),
            settings=settings,
        )
        runner.run_forever()


@app.command()
def seed() -> None:
    """Create the 50 sample tickets in the Jira project (for demo/eval setup)."""
    console.print("[yellow]Not implemented yet[/yellow] — will create the eval tickets in Jira.")
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
