"""Dashboard-ready learning and hardening views over SQLite authority."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from core.shared_intelligence.authority import require_shared_intelligence_tables
from core.shared_intelligence.feedback_loop import cross_model_learning_feedback
from core.shared_intelligence.read_models import (
    component_learning_health,
    learning_event_summary,
    learning_promotion_queue,
)
from core.shared_intelligence.skill_versioning import skill_version_evaluation_report

DASHBOARD_LEARNING_SOURCE_TABLES: tuple[str, ...] = (
    "learning_event_records",
    "hardening_candidate_records",
    "adapter_result_records",
    "model_provider_profiles",
)


def learning_hardening_dashboard_view(
    conn: sqlite3.Connection,
    *,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Compose learning, hardening, and feedback read models for dashboard use."""

    require_shared_intelligence_tables(conn)
    learning = learning_event_summary(conn, project_id=project_id, limit=100)
    promotion_queue = learning_promotion_queue(conn, project_id=project_id)
    component_health = component_learning_health(conn, project_id=project_id)
    versioning = skill_version_evaluation_report(conn, limit=100)
    feedback = cross_model_learning_feedback(conn, project_id=project_id)

    lessons = learning["recent_events"]
    recurring_failures = [
        signal for signal in learning["recurrence_signals"] if int(signal["event_count"]) > 1
    ]
    hardening_candidates = _hardening_candidates(promotion_queue, versioning)
    attention_items = _attention_items(learning, promotion_queue, versioning)

    return {
        "model_name": "shared_intelligence_learning_hardening_dashboard_view",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "dashboard_authority": False,
        "execution_authorized": False,
        "policy_mutation_authorized": False,
        "source_tables": list(DASHBOARD_LEARNING_SOURCE_TABLES),
        "module_available": True,
        "project_id": project_id,
        "sections": {
            "lessons_learned": {
                "title": "Lessons Learned",
                "count": len(lessons),
                "items": lessons,
                "empty_state": "No learning events recorded for this scope.",
            },
            "hardening_candidates": {
                "title": "Hardening Candidates",
                "count": len(hardening_candidates),
                "items": hardening_candidates,
                "empty_state": "No hardening candidates are awaiting dashboard review.",
            },
            "recurring_failures": {
                "title": "Recurring Failures",
                "count": len(recurring_failures),
                "items": recurring_failures,
                "empty_state": "No recurring failure pattern is visible in the selected scope.",
            },
            "model_comparisons": {
                "title": "Model And Adapter Comparisons",
                "preferred_adapter_candidates": feedback["preferred_adapter_candidates"],
                "recommendations": feedback["recommendations"],
                "empty_state": feedback["empty_state"],
            },
            "skill_health": {
                "title": "Skill Health",
                "items": _components(component_health, "skill"),
                "empty_state": "No skill learning health signals are recorded.",
            },
            "workflow_improvement_opportunities": {
                "title": "Workflow Improvement Opportunities",
                "items": _components(component_health, "workflow"),
                "empty_state": "No workflow improvement opportunities are recorded.",
            },
            "attention_queue": {
                "title": "Learning Attention Queue",
                "count": len(attention_items),
                "items": attention_items,
                "empty_state": "No learning or hardening attention items are pending.",
            },
        },
        "raw_read_models": {
            "learning_event_summary": learning,
            "learning_promotion_queue": promotion_queue,
            "component_learning_health": component_health,
            "skill_version_evaluation_report": versioning,
            "cross_model_learning_feedback": feedback,
        },
    }


def validate_learning_hardening_dashboard_view(report: dict[str, Any]) -> list[str]:
    """Validate dashboard view authority and non-execution boundaries."""

    errors: list[str] = []
    if report.get("derived_view") is not True:
        errors.append("derived_view must be true")
    if report.get("primary_authority") is not False:
        errors.append("primary_authority must be false")
    if report.get("routing_authority") is not False:
        errors.append("routing_authority must be false")
    if report.get("dashboard_authority") is not False:
        errors.append("dashboard_authority must be false")
    if report.get("execution_authorized") is not False:
        errors.append("execution_authorized must be false")
    if report.get("policy_mutation_authorized") is not False:
        errors.append("policy_mutation_authorized must be false")
    missing = set(DASHBOARD_LEARNING_SOURCE_TABLES) - set(report.get("source_tables", []))
    if missing:
        errors.append("missing source tables: " + ",".join(sorted(missing)))
    return errors


def _hardening_candidates(
    promotion_queue: dict[str, Any],
    versioning: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for candidate in promotion_queue["hardening_candidates"]:
        items.append(
            {
                "candidate_id": candidate["candidate_id"],
                "component_type": candidate["component_type"],
                "component_id": candidate["component_id"],
                "status": candidate["status"],
                "hardening_type": candidate["hardening_type"],
                "source": "hardening_candidate_records",
                "execution_authorized": False,
            }
        )
    for evaluation in versioning["evaluations"]:
        if evaluation["evaluation_status"] != "already_promoted":
            items.append(
                {
                    "candidate_id": evaluation["candidate_id"],
                    "component_type": evaluation["component_type"],
                    "component_id": evaluation["component_id"],
                    "status": evaluation["evaluation_status"],
                    "hardening_type": evaluation["hardening_type"],
                    "source": "skill_version_evaluation_report",
                    "requires_operator_approval": evaluation["requires_operator_approval"],
                    "execution_authorized": False,
                }
            )
    return items


def _attention_items(
    learning: dict[str, Any],
    promotion_queue: dict[str, Any],
    versioning: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for event in learning["dashboard_attention_items"]:
        items.append(
            _attention("dashboard_attention", event["learning_event_id"], event["summary"])
        )
    for event in promotion_queue["operator_approval_required"]:
        items.append(
            _attention("operator_approval_required", event["learning_event_id"], event["summary"])
        )
    for evaluation in versioning["ready_for_operator_approval"]:
        items.append(
            _attention(
                "hardening_promotion_review",
                evaluation["candidate_id"],
                evaluation["reason"],
            )
        )
    return items


def _attention(kind: str, item_id: str, summary: str | None) -> dict[str, Any]:
    return {
        "attention_type": kind,
        "item_id": item_id,
        "summary": summary,
        "requires_operator_approval": kind != "dashboard_attention",
        "execution_authorized": False,
    }


def _components(component_health: dict[str, Any], component_type: str) -> list[dict[str, Any]]:
    return [
        component
        for component in component_health["components"]
        if component["component_type"] == component_type
    ]
