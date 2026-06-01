from __future__ import annotations

from jira_agent.config import Settings
from jira_agent.models import ActionType, Decision, ReasonCode
from jira_agent.soc import LoggingSocNotifier, WebhookSocNotifier, build_soc_notifier


def _decision(reason: ReasonCode) -> Decision:
    return Decision(ticket_id="T-1", action=ActionType.DEFER, reason_code=reason)


def test_build_defaults_to_logging_notifier() -> None:
    assert isinstance(build_soc_notifier(Settings(_env_file=None)), LoggingSocNotifier)


def test_build_uses_webhook_when_url_configured() -> None:
    notifier = build_soc_notifier(Settings(_env_file=None, agent_soc_webhook_url="https://x/soc"))
    assert isinstance(notifier, WebhookSocNotifier)


def test_logging_notifier_does_not_raise() -> None:
    LoggingSocNotifier().notify(_decision(ReasonCode.ACTIVE_INCIDENT))  # smoke


def test_webhook_dry_run_skips_post(monkeypatch) -> None:
    posted = {"called": False}

    def _fake_post(*_a: object, **_k: object) -> None:
        posted["called"] = True

    monkeypatch.setattr("httpx.post", _fake_post)
    WebhookSocNotifier("https://x/soc", dry_run=True).notify(_decision(ReasonCode.PROMPT_INJECTION))
    assert posted["called"] is False


def test_webhook_posts_payload(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def _fake_post(url: str, json: dict[str, object], timeout: float) -> None:
        seen["url"] = url
        seen["json"] = json

    monkeypatch.setattr("httpx.post", _fake_post)
    WebhookSocNotifier("https://x/soc", dry_run=False).notify(_decision(ReasonCode.ACTIVE_INCIDENT))
    assert seen["url"] == "https://x/soc"
    assert seen["json"]["reason"] == "ACTIVE_INCIDENT"  # type: ignore[index]


def test_webhook_swallows_post_errors(monkeypatch) -> None:
    def _boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("network down")

    monkeypatch.setattr("httpx.post", _boom)
    # Must not raise — a failed SOC page cannot break the pipeline.
    WebhookSocNotifier("https://x/soc", dry_run=False).notify(_decision(ReasonCode.ACTIVE_INCIDENT))
