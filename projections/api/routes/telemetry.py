"""Telemetry spine read-model API routes for dashboard surfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from core.config.database import get_db_path
from core.telemetry.dashboard_freshness import dashboard_data_freshness_status
from core.telemetry.read_models import (
    component_usage_summary,
    dashboard_attention_summary,
    dashboard_module_read_models,
    dashboard_module_segments,
    global_telemetry_summary,
    milestone_telemetry_summary,
    process_run_timeline,
    project_telemetry_summary,
    task_telemetry_summary,
)

router = APIRouter()

_COMPONENT_TYPES = {"agent", "skill", "workflow", "hook", "tool"}


def telemetry_db_path() -> Path:
    """Return the canonical runtime DB path for telemetry dashboard reads."""

    return get_db_path()


@router.get("/summary")
async def get_telemetry_summary() -> dict[str, Any]:
    """Return global dashboard-ready telemetry over the execution spine."""

    return _read_model(global_telemetry_summary)


@router.get("/projects")
async def list_telemetry_projects() -> dict[str, Any]:
    """Return global summary data that includes project coverage."""

    payload = _read_model(global_telemetry_summary)
    payload["surface"] = "projects"
    return payload


@router.get("/projects/{project_id}")
async def get_project_telemetry(project_id: str) -> dict[str, Any]:
    return _read_model(project_telemetry_summary, project_id)


@router.get("/milestones/{milestone_id}")
async def get_milestone_telemetry(
    milestone_id: str,
    project_id: str | None = Query(default=None),
) -> dict[str, Any]:
    return _read_model(milestone_telemetry_summary, milestone_id, project_id=project_id)


@router.get("/tasks/{task_id}")
async def get_task_telemetry(
    task_id: str,
    project_id: str | None = Query(default=None),
    milestone_id: str | None = Query(default=None),
) -> dict[str, Any]:
    return _read_model(
        task_telemetry_summary, task_id, project_id=project_id, milestone_id=milestone_id
    )


@router.get("/process-runs/{process_run_id}")
async def get_process_run_telemetry(process_run_id: str) -> dict[str, Any]:
    return _read_model(process_run_timeline, process_run_id)


@router.get("/components")
async def get_component_usage() -> dict[str, Any]:
    return _read_model(component_usage_summary)


@router.get("/components/{component_type}/{component_id}")
async def get_component_telemetry(component_type: str, component_id: str) -> dict[str, Any]:
    if component_type not in _COMPONENT_TYPES:
        raise HTTPException(
            status_code=404,
            detail=f"Unsupported telemetry component type: {component_type}",
        )
    return _read_model(component_usage_summary, component_type, component_id)


@router.get("/attention")
async def get_dashboard_attention(status: str | None = Query(default=None)) -> dict[str, Any]:
    return _read_model(dashboard_attention_summary, status=status)


@router.get("/modules")
async def get_telemetry_modules(segment: str | None = Query(default=None)) -> dict[str, Any]:
    return _dashboard_response(dashboard_module_segments(segment))


@router.get("/status")
async def get_dashboard_data_status() -> dict[str, Any]:
    """Return dashboard freshness, schema drift, and dry-run backfill status."""

    return _dashboard_response(dashboard_data_freshness_status(telemetry_db_path()))


def _read_model(func: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        payload = func(*args, db_path=telemetry_db_path(), **kwargs)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _dashboard_response(payload)


def _dashboard_response(payload: dict[str, Any]) -> dict[str, Any]:
    modules = dashboard_module_read_models()
    source_tables = list(payload.get("source_tables", []))
    return {
        **payload,
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "dashboard_consumable": True,
        "source_tables": source_tables,
        "module_availability": [
            {
                "module_id": module["module_id"],
                "enabled": module["enabled"],
                "source_tables": module["source_tables"],
                "empty_state": module["empty_state"],
            }
            for module in modules
        ],
        "authority_note": "Telemetry dashboard routes expose derived read models only; they do not decide workflow routing.",
    }
