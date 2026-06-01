from __future__ import annotations

from jira_agent.agent.pipeline import AgentPipeline
from jira_agent.config import Settings
from jira_agent.eval.live import run_live_eval
from jira_agent.jira.mapping import adf_to_text, issue_to_ticket
from jira_agent.models import ActionType, EvalTicket, RetrievedSection
from jira_agent.policies.loader import PolicyCorpus
from jira_agent.triage.classifier import TriageClassifier

from .fakes import FakeJira, FakeLLM, FakeRetriever


def _adf(text: str) -> dict:
    return {
        "type": "doc",
        "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def test_adf_to_text_flattens_paragraphs() -> None:
    assert adf_to_text(_adf("hello world")) == "hello world"


def test_issue_to_ticket_reads_summary_and_description() -> None:
    issue = {
        "key": "ITSD-5",
        "fields": {"summary": "MFA?", "description": _adf("Do I need MFA for Salesforce?")},
    }
    ticket = issue_to_ticket(issue)
    assert ticket.id == "ITSD-5"
    assert "Do I need MFA for Salesforce?" in ticket.body


def test_run_live_eval_matches_and_scores(
    corpus: PolicyCorpus, eval_tickets: list[EvalTicket]
) -> None:
    section = corpus.get_section("POL-01", "1.3")
    assert section is not None
    llm = FakeLLM(
        answer='{"answer": "Yes, MFA via Okta is required.",'
        ' "citations": [{"policy_id": "POL-01", "section": "1.3"}], "conflict": false}'
    )
    pipeline = AgentPipeline(
        triage=TriageClassifier(llm, corpus),
        retriever=FakeRetriever([RetrievedSection(section=section, score=0.9)]),
        llm=llm,
        corpus=corpus,
        settings=Settings(),
    )

    jira = FakeJira(
        existing=[
            # A seeded eval ticket (matches T-002) ...
            {
                "key": "ITSD-5",
                "fields": {
                    "summary": "Do I need MFA to log into Salesforce?",
                    "description": _adf("Do I need MFA to log into Salesforce?"),
                    "labels": ["eval-T-002"],
                },
            },
            # ... a non-eval issue (skipped) ...
            {"key": "ITSD-1", "fields": {"summary": "Task 1", "labels": []}},
            # ... and an eval label with no ground-truth match (skipped).
            {"key": "ITSD-9", "fields": {"summary": "x", "labels": ["eval-T-999"]}},
        ]
    )

    records = run_live_eval(jira, pipeline, project_key="ITSD", eval_tickets=eval_tickets)

    assert len(records) == 1
    rec = records[0]
    assert rec.ticket_id == "T-002"
    assert rec.predicted_action is ActionType.RESOLVE
    assert rec.detail_correct  # cited POL-01 §1.3
