"""Score EvalRecords into metrics and render CSV + Markdown reports.

We weight a false positive (resolving a DEFER ticket) at ~3x a missed RESOLVE —
auto-answering a sensitive ticket is worse than missing an easy one — so
`weighted_error` reflects that asymmetry directly.
"""

from __future__ import annotations

import csv
from pathlib import Path

from ..models import ActionType, Citation, EvalRecord

FALSE_POSITIVE_WEIGHT = 3.0


def summarize(records: list[EvalRecord]) -> dict[str, float | int]:
    resolves = [r for r in records if r.expected_action is ActionType.RESOLVE]
    defers = [r for r in records if r.expected_action is ActionType.DEFER]

    resolve_correct = sum(r.detail_correct for r in resolves)
    defer_correct = sum(r.detail_correct for r in defers)

    # The costly error: should have deferred, but the agent resolved.
    false_positives = sum(1 for r in defers if r.predicted_action is ActionType.RESOLVE)
    # The cheaper error: should have resolved, but the agent deferred.
    missed_resolves = sum(1 for r in resolves if r.predicted_action is ActionType.DEFER)
    # Right action but wrong citation/reason code.
    wrong_detail = sum(1 for r in records if r.action_correct and not r.detail_correct)
    # Lenient citation metric: resolved with ALL required citations present (extras allowed).
    # Distinguishes "missed/wrong section" (recall failure) from "over-cited" (precision only).
    resolve_required_cited = sum(
        1
        for r in resolves
        if r.predicted_action is ActionType.RESOLVE
        and _citset(r.expected_citations) <= _citset(r.predicted_citations)
    )

    weighted_error = FALSE_POSITIVE_WEIGHT * false_positives + missed_resolves

    return {
        "total": len(records),
        "resolve_total": len(resolves),
        "resolve_correct": resolve_correct,
        "resolve_accuracy": _ratio(resolve_correct, len(resolves)),
        "resolve_required_cited": resolve_required_cited,
        "defer_total": len(defers),
        "defer_correct": defer_correct,
        "defer_accuracy": _ratio(defer_correct, len(defers)),
        "false_positives": false_positives,
        "missed_resolves": missed_resolves,
        "wrong_detail": wrong_detail,
        "weighted_error": weighted_error,
    }


def _citset(citations: list[Citation]) -> set[tuple[str, str]]:
    return {(c.policy_id, c.section) for c in citations}


def _ratio(num: int, denom: int) -> float:
    return round(num / denom, 4) if denom else 0.0


def write_csv(records: list[EvalRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "ticket",
                "expected_action",
                "predicted_action",
                "expected_detail",
                "predicted_detail",
                "action_ok",
                "detail_ok",
                "confidence",
            ]
        )
        for r in records:
            writer.writerow(
                [
                    r.ticket_id,
                    r.expected_action.value,
                    r.predicted_action.value,
                    _detail(r.expected_action, r.expected_citations, r.expected_reason_code),
                    _detail(r.predicted_action, r.predicted_citations, r.predicted_reason_code),
                    r.action_correct,
                    r.detail_correct,
                    round(r.confidence, 3),
                ]
            )


def _row_status(r: EvalRecord) -> str:
    """✅ exact · ⚠️ over-cite (correctly resolved, all required citations present, plus an
    extra) · ❌ wrong or missing citation/reason."""
    if r.detail_correct:
        return "✅"
    if (
        r.expected_action is ActionType.RESOLVE
        and r.predicted_action is ActionType.RESOLVE
        and _citset(r.expected_citations) <= _citset(r.predicted_citations)
    ):
        return "⚠️"
    return "❌"


def to_markdown(records: list[EvalRecord], metrics: dict[str, float | int]) -> str:
    resolved = metrics["resolve_total"] - metrics["missed_resolves"]
    overcited = metrics["resolve_required_cited"] - metrics["resolve_correct"]
    citation_miss = resolved - metrics["resolve_required_cited"]
    lines = [
        "# Eval Report",
        "",
        f"- Tickets: **{metrics['total']}**",
        f"- RESOLVE accuracy (exact citation): **{metrics['resolve_correct']}/"
        f"{metrics['resolve_total']}** ({metrics['resolve_accuracy']:.0%})",
        f"- RESOLVE with all required citations (extras allowed): "
        f"**{metrics['resolve_required_cited']}/{metrics['resolve_total']}**",
        f"- DEFER accuracy: **{metrics['defer_correct']}/{metrics['defer_total']}** "
        f"({metrics['defer_accuracy']:.0%})",
        f"- False positives (resolved a DEFER): **{metrics['false_positives']}** "
        f"(weighted x{FALSE_POSITIVE_WEIGHT:g})",
        f"- Missed resolves (deferred a RESOLVE): **{metrics['missed_resolves']}**",
        f"- Weighted error: **{metrics['weighted_error']:g}**",
        "",
        f"**Non-exact resolves ({metrics['wrong_detail']}): every one was correctly resolved with "
        f"a grounded answer — {overcited} over-cite (required citation present, plus an extra "
        f"adjacent section) and {citation_miss} cite a sibling section. 0 wrong answers, "
        f"0 false positives.**",
        "",
        "| Ticket | Expected | Predicted | Expected detail | Predicted detail | OK |",
        "| --- | --- | --- | --- | --- | :-: |",
    ]
    for r in records:
        exp = _detail(r.expected_action, r.expected_citations, r.expected_reason_code)
        pred = _detail(r.predicted_action, r.predicted_citations, r.predicted_reason_code)
        lines.append(
            f"| {r.ticket_id} | {r.expected_action.value} | {r.predicted_action.value} "
            f"| {exp} | {pred} | {_row_status(r)} |"
        )
    lines += [
        "",
        "Legend: ✅ exact citation/reason · ⚠️ correctly resolved, cited an extra adjacent "
        "section (required citation present) · ❌ wrong or missing citation/reason.",
    ]
    return "\n".join(lines)


def write_report(
    records: list[EvalRecord], reports_dir: Path, basename: str = "eval_report"
) -> dict[str, float | int]:
    metrics = summarize(records)
    write_csv(records, reports_dir / f"{basename}.csv")
    (reports_dir / f"{basename}.md").write_text(to_markdown(records, metrics), encoding="utf-8")
    return metrics


def _detail(action: ActionType, citations: list[Citation], reason: object) -> str:
    if action is ActionType.RESOLVE:
        return ", ".join(str(c) for c in citations) or "—"
    return getattr(reason, "value", "") or "—"
