"""Capability route recommendation, model-provider, and AI usage accounting
routes.

WO-GF-API-ROUTES: split out of shared_intelligence.py.
"""

from __future__ import annotations

from typing import Any

from fastapi import Query

from core.shared_intelligence.capability_routing import recommend_capability_route
from core.shared_intelligence.model_registry import (
    model_provider_capability_matrix,
    model_provider_registry_summary,
)
from core.shared_intelligence.usage_accounting import adapter_usage_accounting_summary

from .shared_intelligence_router import router
from .shared_intelligence_shared import _with_connection

# GET /capability-routes (get_capability_routes / capability_route_summary): removed
# migration 147 (WO-SCHEMALEAN) — it read the dropped capability_route_records table and
# was permanently empty. The recommendation preview below is kept (persist-free).


@router.get("/capability-routes/recommendation")
async def preview_capability_route(
    task_class: str = Query(default="code"),
    required_capabilities: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
    risk_level: str = Query(default="medium"),
    cost_sensitivity: str = Query(default="medium"),
    min_context_tokens: int | None = Query(default=None, ge=1),
) -> dict[str, Any]:
    """Preview a capability route without persisting or authorizing execution."""

    capabilities = [
        item.strip() for item in (required_capabilities or "").split(",") if item.strip()
    ]
    route_id = f"dry-run-{task_class}-{project_id or 'global'}"
    return _with_connection(
        lambda conn: recommend_capability_route(
            conn,
            capability_route_id=route_id,
            task_class=task_class,
            required_capabilities=capabilities,
            project_id=project_id,
            risk_level=risk_level,
            cost_sensitivity=cost_sensitivity,
            min_context_tokens=min_context_tokens,
            persist=False,
        )
    )


@router.get("/model-providers")
async def get_model_provider_summary() -> dict[str, Any]:
    """Return model/provider registry summary from recorded SQLite facts."""

    return _with_connection(model_provider_registry_summary)


@router.get("/model-providers/capability-matrix")
async def get_model_provider_capability_matrix(
    required_capabilities: str | None = Query(default=None),
    min_context_tokens: int | None = Query(default=None, ge=1),
    provider: str | None = Query(default=None),
) -> dict[str, Any]:
    """Return recorded model/provider profiles matching requested capabilities."""

    capabilities = [
        item.strip() for item in (required_capabilities or "").split(",") if item.strip()
    ]
    return _with_connection(
        lambda conn: model_provider_capability_matrix(
            conn,
            required_capabilities=capabilities,
            min_context_tokens=min_context_tokens,
            provider=provider,
        )
    )


@router.get("/ai-usage-accounting")
async def get_ai_usage_accounting(
    project_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """Return honest AI adapter usage and operational value telemetry."""

    return _with_connection(
        lambda conn: adapter_usage_accounting_summary(conn, project_id=project_id)
    )
