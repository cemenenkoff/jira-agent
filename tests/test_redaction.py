from __future__ import annotations

from jira_agent.redaction import redact, redact_secrets


def test_redacts_api_keys_and_tokens() -> None:
    assert "sk-ant-" not in redact("my key is sk-ant-api03-abcdefABCDEF1234567890abcd")
    assert "[REDACTED:secret]" in redact("token=ghp_abcdefghijklmnopqrstuvwxyz0123456789")
    assert "AKIA" not in redact("aws AKIAIOSFODNN7EXAMPLE here")


def test_redacts_password_assignment_but_not_prose() -> None:
    assert "[REDACTED:secret]" in redact("password: hunter2")
    # Ordinary mention of the word "password" must survive (no key=value).
    body = "I forgot my password and got locked out after 3 tries."
    assert redact(body) == body


def test_redacts_email_and_phone_inbound() -> None:
    out = redact("contact john.doe@acme.com or call 415-555-0199")
    assert "john.doe@acme.com" not in out
    assert "415-555-0199" not in out


def test_redact_secrets_keeps_policy_contacts() -> None:
    # Outbound (policy-grounded) text keeps a contact email/hotline but still strips secrets.
    out = redact_secrets("report to security@helix.example; key sk-ant-api03-ABCDEFGHIJKLMNOP1234")
    assert "security@helix.example" in out
    assert "sk-ant" not in out
