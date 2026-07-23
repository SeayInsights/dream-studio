"""WO-GF-TELEMETRY-SPLIT: read_models dashboard module declarations.

Extracted verbatim from core/telemetry/read_models.py (see read_models.py
facade). MODULE_SEGMENTS, dashboard_module_read_models, dashboard_module_segments.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.telemetry.execution_spine import dashboard_module_declarations

from .read_models_shared import CORE_TABLES

MODULE_SEGMENTS: Mapping[str, tuple[str, ...]] = {
    "security_only": ("security_analytics",),
    "token_only": ("token_analytics",),
    "component_only": (
        "agent_analytics",
        "skill_analytics",
        "workflow_analytics",
        "hook_analytics",
        "tool_analytics",
    ),
    "validation_only": ("validation_analytics",),
    "research_decision_only": ("research_decision_analytics",),
    # artifact_only removed: artifact_analytics module dropped in migration 130
    "route_attention_only": ("route_milestone_analytics",),
}


def dashboard_module_read_models() -> list[dict[str, Any]]:
    """Return modular dashboard read-model declarations with authority metadata."""

    modules: list[dict[str, Any]] = []
    for module in dashboard_module_declarations():
        source_tables = list(module["source_tables"])
        modules.append(
            {
                "module_id": module["module_id"],
                "module_name": module["module_name"],
                "module_type": module["module_type"],
                "enabled": True,
                "source_tables": source_tables,
                "required_core_tables": list(CORE_TABLES),
                "optional_tables": [
                    table for table in module.get("owns_tables", []) if table not in source_tables
                ],
                "empty_state": module["empty_state"],
                "dashboard_cards": list(module["dashboard_cards"]),
                "drilldown_paths": list(module["drilldown_paths"]),
                "validation_requirements": [
                    "source_tables_exist",
                    "query_returns_empty_state_when_no_rows",
                    "derived_view_metadata_present",
                ],
                "derived_view": True,
                "primary_authority": False,
                "authority_note": "Dashboard modules are derived views over SQLite telemetry facts.",
            }
        )
    modules.append(
        {
            "module_id": "tool_analytics",
            "module_name": "Tool Analytics",
            "module_type": "dashboard_projection",
            "enabled": True,
            "source_tables": ["execution_events"],
            "required_core_tables": list(CORE_TABLES),
            "optional_tables": [],
            "empty_state": "No tool invocations recorded for the selected scope.",
            "dashboard_cards": ["tool_usage", "tool_outcomes"],
            "drilldown_paths": ["project", "milestone", "task", "process_run", "tool"],
            "validation_requirements": [
                "source_tables_exist",
                "query_returns_empty_state_when_no_rows",
                "derived_view_metadata_present",
            ],
            "derived_view": True,
            "primary_authority": False,
            "authority_note": "Dashboard modules are derived views over SQLite telemetry facts.",
        }
    )
    return modules


def dashboard_module_segments(segment: str | None = None) -> dict[str, Any]:
    """Return dashboard modules grouped for independently enabled surfaces."""

    modules = dashboard_module_read_models()
    by_id = {module["module_id"]: module for module in modules}
    segments: dict[str, Any] = {}
    for segment_id, module_ids in MODULE_SEGMENTS.items():
        segment_modules = [by_id[module_id] for module_id in module_ids if module_id in by_id]
        segments[segment_id] = {
            "segment_id": segment_id,
            "enabled": True,
            "module_ids": [module["module_id"] for module in segment_modules],
            "modules": segment_modules,
            "empty_state": "No enabled modules or telemetry facts for this segment.",
            "derived_view": True,
            "primary_authority": False,
        }
    selected = segments.get(segment) if segment else None
    return {
        "model_name": "dashboard_module_segments",
        "segments": segments,
        "active_segment": segment,
        "modules": selected["modules"] if selected else modules,
        "segment_available": selected is not None if segment else True,
        "derived_view": True,
        "primary_authority": False,
        "source_tables": [],
        "empty_state_behavior": "Segments return enabled module declarations and empty states independently.",
    }
