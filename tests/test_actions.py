from __future__ import annotations

from jira_agent.config import Settings
from jira_agent.jira.actions import TicketActions
from jira_agent.models import ActionType, Citation, Decision, ReasonCode

from .fakes import FakeJira


class RecordingNotifier:
    def __init__(self) -> None:
        self.calls: list[ReasonCode | None] = []

    def notify(self, decision: Decision) -> None:
        self.calls.append(decision.reason_code)


def _settings(dry_run: bool) -> Settings:
    return Settings(_env_file=None, agent_dry_run=dry_run)


def _resolve() -> Decision:
    return Decision(
        ticket_id="ITSD-1",
        action=ActionType.RESOLVE,
        answer="MFA via Okta is required for all corporate apps.",
        citations=[Citation(policy_id="POL-01", section="1.3")],
        confidence=0.9,
    )


def _defer(reason: ReasonCode, rationale: str = "needs a person") -> Decision:
    return Decision(
        ticket_id="ITSD-2", action=ActionType.DEFER, reason_code=reason, rationale=rationale
    )


def test_dry_run_performs_no_writes() -> None:
    jira = FakeJira()
    actions = TicketActions(jira, _settings(True), notifier=RecordingNotifier())
    actions.apply(_resolve())
    actions.apply(_defer(ReasonCode.OUT_OF_SCOPE))
    assert jira.comments == []
    assert jira.labels == []
    assert jira.transitioned == []


def test_live_resolve_comments_labels_and_transitions() -> None:
    jira = FakeJira(
        transitions=[{"name": "In Progress", "id": "11"}, {"name": "Resolved", "id": "31"}]
    )
    actions = TicketActions(jira, _settings(False), notifier=RecordingNotifier())
    actions.apply(_resolve())
    assert [k for k, _ in jira.comments] == ["ITSD-1"]
    assert jira.labels == [("ITSD-1", ["auto-resolved"])]
    assert jira.transitioned == [("ITSD-1", "31")]  # first matching resolve transition wins
    body = jira.comments[0][1]
    assert "POL-01 §1.3" in body
    assert "re-open" not in body  # the false invitation was removed (audit rec 1)


def test_live_defer_labels_reason_and_never_transitions() -> None:
    jira = FakeJira()
    actions = TicketActions(jira, _settings(False), notifier=RecordingNotifier())
    actions.apply(_defer(ReasonCode.OUT_OF_SCOPE))
    assert jira.labels == [("ITSD-2", ["needs-human", "reason:OUT_OF_SCOPE"])]
    assert jira.transitioned == []  # a DEFER must never close the ticket
    assert jira.comments[0][0] == "ITSD-2"


def test_missing_resolve_transition_warns_not_raises() -> None:
    jira = FakeJira(transitions=[{"name": "Start Progress", "id": "11"}])  # nothing resolve-like
    actions = TicketActions(jira, _settings(False), notifier=RecordingNotifier())
    actions.apply(_resolve())  # must not raise
    assert jira.transitioned == []


def test_soc_notifier_fires_only_on_high_severity() -> None:
    notifier = RecordingNotifier()
    actions = TicketActions(FakeJira(), _settings(True), notifier=notifier)
    actions.apply(_defer(ReasonCode.ACTIVE_INCIDENT))
    actions.apply(_defer(ReasonCode.OUT_OF_SCOPE))
    actions.apply(_defer(ReasonCode.PROMPT_INJECTION))
    assert notifier.calls == [ReasonCode.ACTIVE_INCIDENT, ReasonCode.PROMPT_INJECTION]


def test_resolve_comment_scrubs_leaked_secret() -> None:
    jira = FakeJira()
    actions = TicketActions(jira, _settings(False), notifier=RecordingNotifier())
    d = _resolve()
    d.answer = "Rotate it; the key sk-ant-api03-ABCDEFGHIJKLMNOP1234 must never be shared."
    actions.apply(d)
    assert "sk-ant-api03" not in jira.comments[0][1]
