"""End-to-end goal-to-release validation packet helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

REQUIRED_LOOP_STAGES = (
    "goal",
    "milestones",
    "work_orders",
    "execution",
    "telemetry",
    "dashboard",
    "validation",
    "release",
    "approval_boundaries",
)


def build_goal_to_release_validation_packet(
    *,
    goal: str,
    milestones: Sequence[Mapping[str, Any]],
    work_orders: Sequence[Mapping[str, Any]],
    telemetry_refs: Sequence[str],
    dashboard_refs: Sequence[str],
    validation_refs: Sequence[str],
    release_refs: Sequence[str],
    approval_boundaries: Sequence[str],
) -> dict[str, Any]:
    """Build a structured proof packet for the full local-first loop."""

    present = {
        "goal": bool(goal.strip()),
        "milestones": bool(milestones),
        "work_orders": bool(work_orders),
        "execution": any(_truthy(item.get("executed")) for item in work_orders),
        "telemetry": bool(telemetry_refs),
        "dashboard": bool(dashboard_refs),
        "validation": bool(validation_refs),
        "release": bool(release_refs),
        "approval_boundaries": bool(approval_boundaries),
    }
    missing = [stage for stage in REQUIRED_LOOP_STAGES if not present[stage]]
    return {
        "packet_type": "goal_to_release_validation",
        "derived_view": True,
        "primary_authority": False,
        "goal": goal,
        "loop_stages": present,
        "missing_stages": missing,
        "validated": not missing,
        "milestones": [_summary(item) for item in milestones],
        "work_orders": [_summary(item) for item in work_orders],
        "telemetry_refs": [str(ref) for ref in telemetry_refs],
        "dashboard_refs": [str(ref) for ref in dashboard_refs],
        "validation_refs": [str(ref) for ref in validation_refs],
        "release_refs": [str(ref) for ref in release_refs],
        "approval_boundaries": [str(item) for item in approval_boundaries],
        "forbidden_actions_executed": False,
        "push_or_deploy_executed": False,
    }


def validate_goal_to_release_validation_packet(packet: Mapping[str, Any]) -> list[str]:
    """Return completeness or boundary violations for a goal-to-release packet."""

    issues: list[str] = []
    missing = packet.get("missing_stages") or []
    if missing:
        issues.append(f"missing_loop_stages:{','.join(str(item) for item in missing)}")
    if _truthy(packet.get("primary_authority")):
        issues.append("packet_must_not_be_primary_authority")
    if _truthy(packet.get("forbidden_actions_executed")):
        issues.append("forbidden_actions_must_not_execute")
    if _truthy(packet.get("push_or_deploy_executed")):
        issues.append("push_or_deploy_must_not_execute")
    return issues


def _summary(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or item.get("work_order_id") or "unknown"),
        "status": str(item.get("status") or "unknown"),
        "evidence_ref": str(item.get("evidence_ref") or ""),
        "executed": _truthy(item.get("executed")),
    }


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "present", "passed"}
    return bool(value)
