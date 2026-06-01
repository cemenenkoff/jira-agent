"""Map a raw Jira issue (REST v3 JSON) to the agent's Ticket model.

Shared by the live runner and the live-eval so both exercise the same read path
(field selection + Atlassian Document Format flattening).
"""

from __future__ import annotations

from typing import Any

from ..models import Ticket

# Block-level ADF node types whose boundaries should become newlines, so adjacent
# paragraphs / list items don't run together in the text the agent reasons over.
_ADF_BLOCK_TYPES = frozenset(
    {
        "paragraph",
        "heading",
        "blockquote",
        "listItem",
        "bulletList",
        "orderedList",
        "codeBlock",
        "panel",
        "rule",
    }
)


def issue_to_ticket(issue: dict[str, Any]) -> Ticket:
    # Attachments / inline media are intentionally ignored: we read only the text of
    # `description` (+ `summary`). OCR'ing screenshots would widen the prompt-injection
    # surface, and an image-only ticket arrives near-empty and defers safely. See the
    # README "Scope & deliberate limitations".
    fields = issue.get("fields", {})
    desc = fields.get("description")
    body = adf_to_text(desc) if isinstance(desc, dict) else (desc or "")
    summary = fields.get("summary")
    full = f"{summary}\n\n{body}".strip() if summary else body.strip()
    reporter = (fields.get("reporter") or {}).get("displayName")
    return Ticket(id=issue["key"], body=full, summary=summary, reporter=reporter, raw=issue)


def adf_to_text(node: object) -> str:
    """Best-effort flatten of an Atlassian Document Format node to plain text.

    Text nodes contribute their text and ``hardBreak`` becomes a newline; block-level
    nodes (paragraphs, headings, list items, …) are separated by newlines so their
    content does not concatenate. Media / attachment nodes carry no text child, so they
    flatten to "" — attachments are intentionally ignored (see ``issue_to_ticket``).
    The result is stripped of leading/trailing whitespace.
    """
    return _adf_flatten(node).strip()


def _adf_flatten(node: object) -> str:
    if isinstance(node, dict):
        ntype = node.get("type")
        if ntype == "text":
            return str(node.get("text", ""))
        if ntype == "hardBreak":
            return "\n"
        inner = "".join(_adf_flatten(c) for c in node.get("content", []))
        return f"{inner}\n" if ntype in _ADF_BLOCK_TYPES else inner
    if isinstance(node, list):
        return "".join(_adf_flatten(c) for c in node)
    return ""
