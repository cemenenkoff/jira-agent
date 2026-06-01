"""Best-effort redaction of secrets and PII before text reaches the LLM, Jira, or logs.

These are heuristic regexes, not a guarantee — the goal is defense-in-depth so that a leaked
credential or a third-party email/phone pasted into a ticket is never sent verbatim to the
model, echoed into a Jira comment, or written to logs. Inbound (untrusted) ticket text is
scrubbed with ``redact`` (secrets AND PII); outbound comment text is scrubbed with
``redact_secrets`` (credentials/card/SSN only), which preserves legitimate policy contacts an
answer may quote (e.g. an SOC email or hotline from a grounded section).
"""

from __future__ import annotations

import re

# Secrets / high-sensitivity values that are NEVER legitimate in a policy-grounded answer, so
# they are stripped both inbound and outbound.
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # API keys / tokens (Anthropic/OpenAI/Stripe-style, GitHub, AWS, JWT).
    ("secret", re.compile(r"\b(?:sk|pk|rk)-(?:ant-)?[A-Za-z0-9]{2,}-?[A-Za-z0-9_-]{16,}\b")),
    ("secret", re.compile(r"\bgh[posru]_[A-Za-z0-9]{20,}\b")),
    ("secret", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("secret", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    # key: value / key=value for credential-ish keys.
    (
        "secret",
        re.compile(
            r"(?i)\b(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|bearer)\b"
            r"\s*[:=]\s*\S+"
        ),
    ),
    ("card", re.compile(r"\b(?:\d[ -]?){13,16}\b")),  # credit-card-ish digit run
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),  # US SSN
]

# PII that is fine in a grounded answer (policy contacts) but should not leak from an untrusted
# ticket — stripped inbound only.
_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    (
        "phone",
        re.compile(r"(?<!\w)(?:\+?\d{1,2}[ .-]?)?(?:\(\d{3}\)|\d{3})[ .-]?\d{3}[ .-]?\d{4}(?!\w)"),
    ),
]


def _apply(text: str, patterns: list[tuple[str, re.Pattern[str]]]) -> str:
    for kind, pat in patterns:
        text = pat.sub(f"[REDACTED:{kind}]", text)
    return text


def redact_secrets(text: str) -> str:
    """Strip credentials / card / SSN only — safe for policy-grounded outbound text."""
    return _apply(text, _SECRET_PATTERNS) if text else text


def redact(text: str) -> str:
    """Strip secrets AND PII (email/phone) — for untrusted inbound ticket text."""
    return _apply(redact_secrets(text), _PII_PATTERNS) if text else text
