"""Learning promotion policy for shared-intelligence events."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from typing import Any

from core.shared_intelligence.authority import require_shared_intelligence_tables

PROMOTION_TARGETS_BY_EVENT_CLASS: dict[str, str] = {
    "skill_gap": "skill_hardening_candidate",
    "workflow_gap": "workflow_hardening_candidate",
    "hook_gap": "hook_hardening_candidate",
    "workaround": "reusable_rule_candidate",
    "failed_assumption": "reusable_rule_candidate",
    "operator_correction": "adapter_or_skill_policy_candidate",
    "validation_failure": "validation_policy_candidate",
    "route_mistake": "route_policy_candidate",
    "successful_hardening": "reusable_rule",
    "adapter_gap": "adapter_policy_candidate",
    "model_provider_gap": "model_provider_profile_review",
    "other": "manual_review_required",
}

HIGH_SEVERITY: frozenset[str] = frozenset({"high", "critical"})


def learning_promotion_decision(event: dict[str, Any]) -> dict[str, Any]:
    """Return a deterministic non-executing promotion decision for one event."""

    promotion_status = str(event.get("promotion_status") or "observed")
    event_class = str(event.get("event_class") or "other")
    severity = str(event.get("severity") or "info")
    recurrence_key = event.get("recurrence_key")
    if promotion_status == "operator_approval_required":
        target = "operator_approval_item"
        requires_operator_approval = True
    elif promotion_status == "dashboard_attention":
        target = "dashboard_attention_item"
        requires_operator_approval = False
    else:
        target = PROMOTION_TARGETS_BY_EVENT_CLASS.get(event_class, "manual_review_required")
        requires_operator_approval = severity in HIGH_SEVERITY and target in {
            "adapter_policy_candidate",
            "model_provider_profile_review",
            "route_policy_candidate",
        }

    return {
        "learning_event_id": event.get("learning_event_id"),
        "event_class": event_class,
        "severity": severity,
        "promotion_status": promotion_status,
        "component_type": event.get("component_type"),
        "component_id": event.get("component_id"),
        "recommended_target": target,
        "recurrence_key": recurrence_key,
        "recurrence_sensitive": bool(recurrence_key),
        "requires_operator_approval": requires_operator_approval,
        "promotion_execution_authorized": False,
        "requires_future_work_order": target
        not in {"dashboard_attention_item", "operator_approval_item"},
        "reason": _reason(event_class, severity, promotion_status, target, recurrence_key),
    }


def learning_promotion_policy_report(
    conn: sqlite3.Connection,
    *,
    project_id: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Return promotion decisions for learning events from SQLite authority."""

    require_shared_intelligence_tables(conn)
    where = ""
    params: list[Any] = []
    if project_id is not None:
        where = "WHERE project_id = ?"
        params.append(project_id)
    rows = conn.execute(
        f"""
        SELECT *
        FROM learning_event_records
        {where}
        ORDER BY created_at DESC, learning_event_id DESC
        LIMIT ?
        """,
        (*params, max(1, min(int(limit), 100))),
    ).fetchall()
    events = [_decode_event(row) for row in rows]
    decisions = [learning_promotion_decision(event) for event in events]
    return {
        "model_name": "shared_intelligence_learning_promotion_policy_report",
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "promotion_execution_authorized": False,
        "source_tables": ["learning_event_records"],
        "project_id": project_id,
        "decision_count": len(decisions),
        "target_counts": dict(
            sorted(Counter(decision["recommended_target"] for decision in decisions).items())
        ),
        "operator_approval_required": [
            decision for decision in decisions if decision["requires_operator_approval"]
        ],
        "decisions": decisions,
        "policy_matrix": dict(sorted(PROMOTION_TARGETS_BY_EVENT_CLASS.items())),
        "empty_state": "No learning events recorded for promotion policy evaluation.",
    }


def _decode_event(row: sqlite3.Row) -> dict[str, Any]:
    event = dict(row)
    event["source_refs"] = _loads(event.pop("source_refs_json"), [])
    event["evidence_refs"] = _loads(event.pop("evidence_refs_json"), [])
    event["metadata"] = _loads(event.pop("metadata_json"), {})
    return event


def _loads(raw: str | None, default: Any) -> Any:
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _reason(
    event_class: str,
    severity: str,
    promotion_status: str,
    target: str,
    recurrence_key: Any,
) -> str:
    parts = [
        f"event_class={event_class}",
        f"severity={severity}",
        f"promotion_status={promotion_status}",
        f"target={target}",
    ]
    if recurrence_key:
        parts.append("recurrence_key_present")
    return "; ".join(parts)
