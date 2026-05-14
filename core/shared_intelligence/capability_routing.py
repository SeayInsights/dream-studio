"""Capability-based route recommendations from shared-intelligence facts."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from typing import Any

from core.shared_intelligence.adapter_alignment import adapter_alignment_summary
from core.shared_intelligence.authority import (
    record_capability_route,
    require_shared_intelligence_tables,
)
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
    persist: bool = True,
) -> dict[str, Any]:
    """Recommend and optionally persist a non-executing capability route."""

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
            "capability_route_records",
        ],
    }
    if persist:
        record_capability_route(
            conn,
            capability_route_id=capability_route_id,
            project_id=project_id,
            milestone_id=milestone_id,
            task_id=task_id,
            process_run_id=process_run_id,
            task_class=task_class,
            selected_adapter_id=selected_adapter_id,
            selected_model_profile_id=selected_model_profile_id,
            route_basis=route_basis,
            risk_level=risk_level,
            cost_sensitivity=cost_sensitivity,
            validation_required=True,
            operator_approval_required=operator_approval_required,
            source_refs=["sqlite:capability_route_records"],
            evidence_refs=["wo-dream-studio-capability-based-routing-maturation"],
        )
    return recommendation


def capability_route_summary(
    conn: sqlite3.Connection,
    *,
    project_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Return persisted capability route recommendations as a derived view."""

    require_shared_intelligence_tables(conn)
    where = ""
    params: list[Any] = []
    if project_id is not None:
        where = "WHERE project_id = ?"
        params.append(project_id)
    rows = conn.execute(
        f"""
        SELECT *
        FROM capability_route_records
        {where}
        ORDER BY created_at DESC, capability_route_id DESC
        LIMIT ?
        """,
        (*params, max(1, min(int(limit), 100))),
    ).fetchall()
    routes = [_decode_route(row) for row in rows]
    return {
        "model_name": "shared_intelligence_capability_route_summary",
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "policy_mutation_authorized": False,
        "execution_authorized": False,
        "source_tables": ["capability_route_records"],
        "project_id": project_id,
        "route_count": len(routes),
        "adapter_counts": dict(
            sorted(Counter(route["selected_adapter_id"] for route in routes).items())
        ),
        "operator_approval_required_count": sum(
            1 for route in routes if route["operator_approval_required"]
        ),
        "routes": routes,
        "empty_state": "No capability route recommendations recorded for the selected scope.",
    }


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


def _decode_route(row: sqlite3.Row) -> dict[str, Any]:
    route = dict(row)
    route["route_basis"] = _loads(route.pop("route_basis_json"), {})
    route["source_refs"] = _loads(route.pop("source_refs_json"), [])
    route["evidence_refs"] = _loads(route.pop("evidence_refs_json"), [])
    route["validation_required"] = bool(route["validation_required"])
    route["operator_approval_required"] = bool(route["operator_approval_required"])
    return route


def _loads(raw: str | None, default: Any) -> Any:
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default
