"""The 12 DEFER reason codes and their human-readable descriptions.

Kept in one place so the triage prompt, the Jira defer comment, and the eval
report all draw from the same source of truth.
"""

from __future__ import annotations

from .models import ReasonCode

REASON_CODE_DESCRIPTIONS: dict[ReasonCode, str] = {
    ReasonCode.OUT_OF_SCOPE: "Question is not about IT (HR, Finance, Facilities, etc.).",
    ReasonCode.ACTIVE_INCIDENT: "User describes a possible breach, malware, or account compromise.",
    ReasonCode.PRIVILEGED_ACCESS: (
        "Request to grant or change elevated access without proper workflow."
    ),
    ReasonCode.WRONG_TENANT: "Question references a different company's policies.",
    ReasonCode.WRONG_INTENT: "Question is troubleshooting/support, not a policy question.",
    ReasonCode.PII_REQUEST: "Asking for personal data about another employee.",
    ReasonCode.PROMPT_INJECTION: (
        "User attempts to override the agent's instructions or bypass policy."
    ),
    ReasonCode.SPECULATIVE: (
        "Question is about future or hypothetical policy that doesn't exist today."
    ),
    ReasonCode.HOSTILE_TONE: "Ticket contains abuse, threats, or profanity directed at staff.",
    ReasonCode.NONEXISTENT_POLICY: "User cites a policy that isn't in the knowledge base.",
    ReasonCode.LOW_CONFIDENCE: "Retrieval/answer confidence below the agent's threshold.",
    ReasonCode.CONFLICTING_POLICIES: "Two policies appear to give contradictory guidance.",
}

# Reason codes the deterministic pipeline assigns post-retrieval (no LLM triage needed).
RETRIEVAL_REASON_CODES = {ReasonCode.LOW_CONFIDENCE, ReasonCode.CONFLICTING_POLICIES}
