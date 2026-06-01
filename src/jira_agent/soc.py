"""SOC notification seam for high-severity deferrals (active incidents, prompt injection).

A reason-code label alone does not page anyone, so a DEFER carrying a SOC reason code fires a
notifier. The default ``LoggingSocNotifier`` emits a structured high-severity log line that a
SIEM / log-based alerting pipeline can trigger on; set ``AGENT_SOC_WEBHOOK_URL`` to POST the
alert to a real endpoint instead. Notifiers are best-effort and must never raise into the
pipeline — a failed page should not stop the agent from processing the ticket.
"""

from __future__ import annotations

from typing import Protocol

from .config import Settings
from .logging_setup import get_logger
from .models import Decision

log = get_logger("soc")


def _reason(decision: Decision) -> str:
    return decision.reason_code.value if decision.reason_code else "UNSPECIFIED"


class SocNotifier(Protocol):
    def notify(self, decision: Decision) -> None:
        """Raise a SOC alert for a high-severity deferral. Implementations must not raise."""
        ...


class LoggingSocNotifier:
    """Default notifier: a structured WARNING that log-based alerting can page on."""

    def notify(self, decision: Decision) -> None:
        log.warning(
            "soc.alert", ticket=decision.ticket_id, reason=_reason(decision), severity="high"
        )


class WebhookSocNotifier:
    """POSTs the alert as JSON to a configured endpoint (best-effort, never raises)."""

    def __init__(self, url: str, *, dry_run: bool = False, timeout: float = 5.0) -> None:
        self._url = url
        self._dry_run = dry_run
        self._timeout = timeout

    def notify(self, decision: Decision) -> None:
        payload = {"ticket": decision.ticket_id, "reason": _reason(decision), "severity": "high"}
        if self._dry_run:
            log.warning("soc.alert.webhook_skipped", dry_run=True, **payload)
            return
        try:
            import httpx

            httpx.post(self._url, json=payload, timeout=self._timeout)
            log.warning("soc.alert", **payload)
        except Exception as exc:  # a SOC POST failure must not break the pipeline
            log.error("soc.alert.webhook_failed", error=str(exc), **payload)


def build_soc_notifier(settings: Settings) -> SocNotifier:
    """Webhook notifier when ``AGENT_SOC_WEBHOOK_URL`` is set, else structured logging."""
    if settings.agent_soc_webhook_url:
        return WebhookSocNotifier(settings.agent_soc_webhook_url, dry_run=settings.agent_dry_run)
    return LoggingSocNotifier()
