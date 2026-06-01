"""Parse the drop-in Markdown policy files into a queryable corpus.

Policy file format (see data/policies/POL-01.md):

    ---
    id: POL-01
    title: Password & Authentication Policy
    effective: "2025-09-01"
    owner: Identity & Access Management team
    ---

    ### 1.1
    <section text>

    ### 1.2
    ...

Onboarding policy #11 = drop a POL-11.md file here. No code changes.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from ..models import Policy, PolicySection

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_SECTION_RE = re.compile(r"^###\s+(\S+)\s*$", re.MULTILINE)


def parse_policy(path: Path) -> Policy:
    raw = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        raise ValueError(f"{path.name}: missing or malformed YAML front-matter")
    meta = yaml.safe_load(match.group(1)) or {}
    body = match.group(2)

    headers = list(_SECTION_RE.finditer(body))
    if not headers:
        raise ValueError(f"{path.name}: no '### <section>' headers found")

    sections: list[PolicySection] = []
    for i, header in enumerate(headers):
        start = header.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(body)
        sections.append(
            PolicySection(
                policy_id=meta["id"],
                section=header.group(1),
                text=body[start:end].strip(),
            )
        )

    return Policy(
        id=meta["id"],
        title=meta["title"],
        effective=str(meta["effective"]),
        owner=meta["owner"],
        sections=sections,
    )


def load_policies(policies_dir: Path) -> PolicyCorpus:
    paths = sorted(policies_dir.glob("*.md"))
    if not paths:
        raise FileNotFoundError(f"No policy .md files found in {policies_dir}")
    return PolicyCorpus([parse_policy(p) for p in paths])


class PolicyCorpus:
    """In-memory index over all loaded policies, with section lookups."""

    def __init__(self, policies: list[Policy]) -> None:
        self.policies = policies
        self._by_id = {p.id: p for p in policies}

    @property
    def sections(self) -> list[PolicySection]:
        return [s for p in self.policies for s in p.sections]

    def get_policy(self, policy_id: str) -> Policy | None:
        return self._by_id.get(policy_id)

    def get_section(self, policy_id: str, section: str) -> PolicySection | None:
        policy = self._by_id.get(policy_id)
        return policy.get_section(section) if policy else None

    def __len__(self) -> int:
        return len(self.policies)
