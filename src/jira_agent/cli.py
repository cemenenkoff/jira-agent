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
def seed(
    issue_type: str = typer.Option("Service Request", "--issue-type", help="Issue type to create."),
    limit: int = typer.Option(0, "--limit", help="Only seed the first N tickets (0 = all)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without creating issues."),
) -> None:
    """Load the 50 eval tickets into the Jira project (idempotent; re-runs skip existing)."""
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    from .eval.harness import load_eval_tickets
    from .jira.client import JiraClient
    from .jira.seed import seed_tickets

    tickets = load_eval_tickets(settings.tickets_file)
    try:
        jira_cm = JiraClient(settings)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    with jira_cm as jira:
        result = seed_tickets(
            jira,
            project_key=settings.jira_project_key,
            tickets=tickets,
            issue_type=issue_type,
            limit=limit,
            dry_run=dry_run,
        )

    verb = "Would create" if result.dry_run else "Created"
    console.print(
        f"[green]{verb} {len(result.created)}[/green] issue(s) as "
        f"[bold]{result.issue_type}[/bold] in {settings.jira_project_key}; "
        f"skipped {len(result.skipped_existing)} already present."
    )
    for eval_id, key in result.created:
        console.print(f"  {eval_id} -> {key or '(dry-run)'}")


if __name__ == "__main__":
    app()
