"""Report-only next-work-order continuation for work-order close.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/close.py``. Holds
``_apply_report_only_continuation`` — a NEW function whose body is extracted
verbatim from ``close_work_order``'s former inline WO-CLOSE-REPORT-ONLY
block. No logic changes — mutates ``result`` in place and never starts
anything.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _apply_report_only_continuation(
    result: dict[str, Any],
    *,
    verify_ran: bool,
    verify_result: dict[str, Any] | None,
    project_id_for_autostart: str | None,
    has_gaps: bool,
    title: str,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> None:
    """Report-only continuation (WO-CLOSE-REPORT-ONLY): advertise the next ready WO
    (or the registered remediation WOs) so the operator — or the execute-work-orders
    workflow's next-iteration node — can start it. Close deliberately does NOT
    auto-start anything: the old auto-start piled up dangling in_progress WOs on
    every directed close. The autonomous loop now starts the next WO explicitly in
    its next-iteration node, so nothing depends on this being a side effect.
    """
    if verify_ran and verify_result is not None and project_id_for_autostart:
        if has_gaps:
            # Report the registered remediation WO(s); do not start them.
            spawned = verify_result.get("spawned_work_orders", [])
            if spawned:
                first_gap = spawned[0]
                gap_wo_id = first_gap["work_order_id"]
                gap_wo_title = first_gap["title"]
                gaps_list = verify_result.get("gaps", [])
                tasks_str = "\n".join(f"  - {g.get('title', '')}" for g in gaps_list)
                _sep = "=" * 42
                result["gaps_block"] = (
                    f"\n{_sep}\n"
                    f"=== GAPS FOUND IN {title} ===\n"
                    f"Registered: REMEDIATION WO {gap_wo_id} with {len(gaps_list)} tasks\n"
                    f"Tasks:\n{tasks_str}\n"
                    f"Run: py -m interfaces.cli.ds work-order start {gap_wo_id} to begin remediation.\n"
                    f"Main session: review "
                    f".planning/work-orders/{work_order_id}/review-verdict.json for full detail.\n"
                    f"{_sep}\n"
                )
                result["spawned_work_orders"] = spawned
                result["next_command"] = f"ds work-order start {gap_wo_id}"
                result["next_block"] = (
                    f"NEXT WORK ORDER (remediation): {gap_wo_title}"
                    f" / ID: {gap_wo_id}"
                    f" / Run: py -m interfaces.cli.ds work-order start {gap_wo_id}"
                )
        else:
            # Verify passed — advertise the authoritative project-wide ready-set pick
            # (get_next_work_order respects cross-milestone ordering, dependencies, and
            # startability, unlike the naive same-milestone next_wo computed above), but
            # do NOT start it. Starting is an explicit operator / workflow action.
            from core.projects.queries import get_next_work_order as _get_next

            _next_result = _get_next(
                project_id=project_id_for_autostart,
                source_root=source_root,
                dream_studio_home=dream_studio_home,
            )
            _next_wo = _next_result.get("work_order") if _next_result.get("ok") else None
            if _next_wo:
                _next_id = _next_wo["work_order_id"]
                _next_title = _next_wo["title"]
                result["next_work_order"] = {
                    "work_order_id": _next_id,
                    "title": _next_title,
                    "type": _next_wo.get("type") or _next_wo.get("work_order_type"),
                    "sequence_order": _next_wo.get("sequence_order"),
                    "next_command": f"ds work-order start {_next_id}",
                }
                result["next_command"] = f"ds work-order start {_next_id}"
                result["next_block"] = (
                    f"NEXT WORK ORDER: {_next_title}"
                    f" / ID: {_next_id}"
                    f" / Run: py -m interfaces.cli.ds work-order start {_next_id}"
                )
            else:
                result["next_block"] = "NO NEXT WORK ORDER FOUND / MILESTONE COMPLETE"
