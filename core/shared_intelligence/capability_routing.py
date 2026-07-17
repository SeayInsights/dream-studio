"""Capability-based route recommendations from shared-intelligence facts."""

from __future__ import annotations

import sqlite3
from typing import Any

from core.shared_intelligence.adapter_alignment import adapter_alignment_summary
from core.shared_intelligence.authority import require_shared_intelligence_tables
from core.shared_intelligence.feedback_loop import cross_model_learning_feedback
from core.shared_intelligence.model_registry import model_provider_capability_matrix

HIGH_RISK_LEVELS: frozenset[str] = frozenset({"high", "critical"})


def recommend_capability_route(
    conn: sqlite3.Connection,
    *,
    capability_route_id: str,
    task_class: str,
    required_capabilities: list[str] | tuple[str, ...],
    project_id: str | None = None,
    milestone_id: str | None = None,
    task_id: str | None = None,
    process_run_id: str | None = None,
    risk_level: str = "medium",
    cost_sensitivity: str = "medium",
    min_context_tokens: int | None = None,
) -> dict[str, Any]:
    """Recommend a non-executing capability route (preview only, never persisted).

    WO-SCHEMALEAN (migration 147): the persist path + capability_route_records were
    removed as a dead persist=False writer; this function is now preview-only.
    """

    require_shared_intelligence_tables(conn)
    adapters = adapter_alignment_summary(conn)
    model_matrix = model_provider_capability_matrix(
        conn,
        required_capabilities=required_capabilities,
        min_context_tokens=min_context_tokens,
    )
    feedback = cross_model_learning_feedback(conn, project_id=project_id)
    selected_adapter_id = _select_adapter(task_class, adapters, feedback)
    selected_model_profile_id = (
        str(model_matrix["matches"][0]["model_profile_id"]) if model_matrix["matches"] else None
    )
    route_basis = {
        "required_capabilities": sorted(str(item) for item in required_capabilities),
        "task_class": task_class,
        "adapter_selection": "feedback_preferred_or_task_class_fallback",
        "model_selection": "first_recorded_profile_matching_constraints",
        "min_context_tokens": min_context_tokens,
        "policy_mutation_authorized": False,
        "execution_authorized": False,
        "model_matches": [match["model_profile_id"] for match in model_matrix["matches"]],
    }
    operator_approval_required = str(risk_level).lower() in HIGH_RISK_LEVELS
    recommendation = {
        "model_name": "shared_intelligence_capability_route_recommendation",
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "policy_mutation_authorized": False,
        "execution_authorized": False,
        "capability_route_id": capability_route_id,
        "project_id": project_id,
        "milestone_id": milestone_id,
        "task_id": task_id,
        "process_run_id": process_run_id,
        "task_class": task_class,
        "selected_adapter_id": selected_adapter_id,
        "selected_model_profile_id": selected_model_profile_id,
        "route_basis": route_basis,
        "risk_level": risk_level,
        "cost_sensitivity": cost_sensitivity,
        "validation_required": True,
        "operator_approval_required": operator_approval_required,
        "source_tables": [
            "adapter_authority_profiles",
            "model_provider_profiles",
            "adapter_result_records",
            "learning_event_records",
        ],
    }
    return recommendation


# capability_route_summary + _decode_route + _loads: removed migration 147
# (WO-SCHEMALEAN) — they read the dropped capability_route_records table.


def _select_adapter(
    task_class: str,
    adapters: dict[str, Any],
    feedback: dict[str, Any],
) -> str | None:
    registered = set(adapters["registered_adapter_ids"])
    for candidate in feedback.get("preferred_adapter_candidates", []):
        adapter_id = str(candidate["adapter_id"])
        if adapter_id in registered:
            return adapter_id
    task = task_class.lower()
    preferred_by_task = [
        ("research", "chatgpt"),
        ("validation", "shell"),
        ("command", "shell"),
        ("tool", "mcp"),
        ("code", "codex"),
        ("implementation", "codex"),
    ]
    for keyword, adapter_id in preferred_by_task:
        if keyword in task and adapter_id in registered:
            return adapter_id
    return sorted(registered)[0] if registered else None
