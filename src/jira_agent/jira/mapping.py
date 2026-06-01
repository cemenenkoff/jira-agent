"""Map a raw Jira issue (REST v3 JSON) to the agent's Ticket model.

Shared by the live runner and the live-eval so both exercise the same read path
(field selection + Atlassian Document Format flattening).
"""

from __future__ import annotations

from typing import Any

from ..models import Ticket


def issue_to_ticket(issue: dict[str, Any]) -> Ticket:
    fields = issue.get("fields", {})
    desc = fields.get("description")
    body = adf_to_text(desc) if isinstance(desc, dict) else (desc or "")
    summary = fields.get("summary")
    full = f"{summary}\n\n{body}".strip() if summary else body
    reporter = (fields.get("reporter") or {}).get("displayName")
    return Ticket(id=issue["key"], body=full, summary=summary, reporter=reporter, raw=issue)


def adf_to_text(node: object) -> str:
    """Best-effort flatten of an Atlassian Document Format node to plain text."""
    if isinstance(node, dict):
        if node.get("type") == "text":
            return str(node.get("text", ""))
        return "".join(adf_to_text(c) for c in node.get("content", []))
    if isinstance(node, list):
        return "".join(adf_to_text(c) for c in node)
    return ""
