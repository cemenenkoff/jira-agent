"""Domain models shared across the agent.

Everything the pipeline passes around is a typed model so the triage, retrieval,
grounding, Jira, and eval layers all agree on shapes.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ActionType(StrEnum):
    """The two terminal dispositions for a ticket."""

    RESOLVE = "RESOLVE"
    DEFER = "DEFER"


class ReasonCode(StrEnum):
    """Why a ticket was deferred to a human. Matches the assignment's standard list."""

    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    ACTIVE_INCIDENT = "ACTIVE_INCIDENT"
    PRIVILEGED_ACCESS = "PRIVILEGED_ACCESS"
    WRONG_TENANT = "WRONG_TENANT"
    WRONG_INTENT = "WRONG_INTENT"
    PII_REQUEST = "PII_REQUEST"
    PROMPT_INJECTION = "PROMPT_INJECTION"
    SPECULATIVE = "SPECULATIVE"
    HOSTILE_TONE = "HOSTILE_TONE"
    NONEXISTENT_POLICY = "NONEXISTENT_POLICY"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    CONFLICTING_POLICIES = "CONFLICTING_POLICIES"


class Citation(BaseModel):
    """A reference to a single policy section, e.g. POL-01 §1.4."""

    model_config = {"frozen": True}

    policy_id: str
    section: str

    def __str__(self) -> str:
        return f"{self.policy_id} §{self.section}"


class PolicySection(BaseModel):
    """One numbered clause within a policy (the citable unit)."""

    policy_id: str
    section: str
    text: str

    @property
    def citation(self) -> Citation:
        return Citation(policy_id=self.policy_id, section=self.section)

    def render(self) -> str:
        return f"{self.policy_id} §{self.section}: {self.text}"


class Policy(BaseModel):
    """A full policy document (POL-XX) and its sections."""

    id: str
    title: str
    effective: str
    owner: str
    sections: list[PolicySection]

    def get_section(self, section: str) -> PolicySection | None:
        return next((s for s in self.sections if s.section == section), None)


class Ticket(BaseModel):
    """A Jira issue normalized to the fields the agent reasons over."""

    id: str
    body: str
    summary: str | None = None
    reporter: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class RetrievedSection(BaseModel):
    """A policy section returned by the retriever, with its relevance score (0..1)."""

    section: PolicySection
    score: float


class Decision(BaseModel):
    """The agent's verdict for a single ticket."""

    ticket_id: str
    action: ActionType
    answer: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    reason_code: ReasonCode | None = None
    confidence: float = 0.0
    rationale: str = ""
    retrieved: list[RetrievedSection] = Field(default_factory=list)


class EvalTicket(BaseModel):
    """A ground-truth-labeled ticket from the 50-ticket eval set."""

    id: str
    expected_action: ActionType
    body: str
    expected_citations: list[Citation] = Field(default_factory=list)
    expected_reason_code: ReasonCode | None = None
    ground_truth_raw: str = ""
    notes: str | None = None

    def to_ticket(self) -> Ticket:
        return Ticket(id=self.id, body=self.body)


class EvalRecord(BaseModel):
    """One row of the eval report: prediction vs. ground truth."""

    ticket_id: str
    expected_action: ActionType
    predicted_action: ActionType
    expected_citations: list[Citation] = Field(default_factory=list)
    predicted_citations: list[Citation] = Field(default_factory=list)
    expected_reason_code: ReasonCode | None = None
    predicted_reason_code: ReasonCode | None = None
    action_correct: bool = False
    detail_correct: bool = False  # citation-set match (RESOLVE) or reason-code match (DEFER)
    confidence: float = 0.0
    notes: str = ""
