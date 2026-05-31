"""Citation verification — the gate that turns "the model cited X" into proof.

A RESOLVE is allowed only if every citation (a) exists in the corpus and (b) was
among the sections actually retrieved and shown to the model. This is what stops
the agent from citing a plausible-but-unsupported (or hallucinated) section.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Citation, RetrievedSection
from ..policies.loader import PolicyCorpus


@dataclass
class GroundingResult:
    ok: bool
    problems: list[str] = field(default_factory=list)


def verify_citations(
    citations: list[Citation],
    corpus: PolicyCorpus,
    retrieved: list[RetrievedSection],
) -> GroundingResult:
    problems: list[str] = []
    if not citations:
        problems.append("no citation provided")

    retrieved_keys = {(r.section.policy_id, r.section.section) for r in retrieved}
    for c in citations:
        if corpus.get_section(c.policy_id, c.section) is None:
            problems.append(f"{c} does not exist in the policy corpus")
        elif (c.policy_id, c.section) not in retrieved_keys:
            problems.append(f"{c} was not retrieved (possible hallucination)")

    return GroundingResult(ok=not problems, problems=problems)
