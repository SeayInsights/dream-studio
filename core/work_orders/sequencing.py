"""Non-executing Work Order sequence draft generation."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from collections.abc import Mapping, Sequence

from compat import UTC

from .models import WorkOrderError
from .validation import validate_work_order

DEFAULT_FORBIDDEN_ACTIONS: tuple[str, ...] = (
    "Do not mutate live installed state without an approved mutation Work Order.",
    "Do not mutate the live SQLite DB without explicit approval.",
    "Do not delete, archive, compact, or deduplicate files.",
    "Do not push, deploy, install dependencies, or start Docker.",
)


def build_work_order_sequence(
    *,
    project_name: str,
    target_path: str | Path,
    milestones: Sequence[Mapping[str, Any]],
    created_by: str = "dream-studio-sequencer",
    created_at: str | None = None,
    default_validation_commands: Sequence[str] = (),
) -> dict[str, Any]:
    """Return linked Work Order drafts for an ordered milestone list.

    The output is intentionally draft-only. Saving, approving, rendering, or
    executing the generated Work Orders remains a separate Work Order boundary.
    """

    if not milestones:
        raise WorkOrderError("at least one milestone is required.")

    timestamp = created_at or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    target = str(Path(target_path))
    drafts: list[dict[str, Any]] = []
    for index, milestone in enumerate(milestones):
        milestone_id = _required_text(milestone, "milestone_id")
        work_order_id = str(milestone.get("work_order_id") or f"wo-dream-studio-{milestone_id}")
        previous_id = drafts[index - 1]["work_order_id"] if index else None
        next_id = (
            str(
                milestones[index + 1].get("work_order_id")
                or f"wo-dream-studio-{_required_text(milestones[index + 1], 'milestone_id')}"
            )
            if index + 1 < len(milestones)
            else None
        )
        draft = {
            "work_order_id": work_order_id,
            "project_name": project_name,
            "target_path": target,
            "objective": _required_text(milestone, "objective"),
            "approval_mode": str(milestone.get("approval_mode") or "approval_required"),
            "risk_level": str(milestone.get("risk_level") or "medium"),
            "scope": {
                "include": list(milestone.get("include") or [f"milestone:{milestone_id}"]),
                "exclude": list(milestone.get("exclude") or DEFAULT_FORBIDDEN_ACTIONS),
            },
            "allowed_skills": list(milestone.get("allowed_skills") or ["ds-core"]),
            "allowed_agents": list(milestone.get("allowed_agents") or ["codex"]),
            "workflow": list(
                milestone.get("workflow")
                or [
                    "understanding_report",
                    "approval_artifact",
                    "bounded_execution",
                    "focused_validation",
                ]
            ),
            "forbidden_actions": list(
                milestone.get("forbidden_actions") or DEFAULT_FORBIDDEN_ACTIONS
            ),
            "validation_commands": list(
                milestone.get("validation_commands") or default_validation_commands
            ),
            "expected_outputs": list(
                milestone.get("expected_outputs")
                or ["work_order_evidence", "validation_evidence", "route_decision"]
            ),
            "stop_conditions": list(
                milestone.get("stop_conditions")
                or [
                    "validation fails",
                    "scope exceeds approved files",
                    "operator approval boundary reached",
                ]
            ),
            "created_by": created_by,
            "created_at": timestamp,
            "status": "draft",
            "privacy_export_classification": "local_only",
            "sequence": {
                "milestone_id": milestone_id,
                "position": index + 1,
                "total": len(milestones),
                "previous_work_order_id": previous_id,
                "next_work_order_id": next_id,
                "route_decision_on_success": (
                    "continue_internal" if next_id else "milestone_complete"
                ),
                "execution_authorized_by_sequence": False,
            },
        }
        validation = validate_work_order(draft, allow_missing_target=True)
        if not validation.ok:
            raise WorkOrderError(validation.format())
        drafts.append(validation.work_order)

    return {
        "sequence_id": f"{project_name.lower().replace(' ', '-')}-work-order-sequence",
        "project_name": project_name,
        "target_path": target,
        "created_at": timestamp,
        "draft_only": True,
        "execution_authorized": False,
        "work_orders": drafts,
    }


def _required_text(mapping: Mapping[str, Any], key: str) -> str:
    value = str(mapping.get(key) or "").strip()
    if not value:
        raise WorkOrderError(f"{key} is required.")
    return value
