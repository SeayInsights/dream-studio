"""Learning/hardening dashboard, adapter projection, and context-packet
preview routes.

WO-GF-API-ROUTES: split out of shared_intelligence.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Query

from core.shared_intelligence.adapter_config_projection import (
    adapter_config_projection_report,
)
from core.shared_intelligence.adapter_staleness import adapter_staleness_report
from core.shared_intelligence.context_packets import generate_shared_context_packet
from core.shared_intelligence.dashboard_views import learning_hardening_dashboard_view

from .shared_intelligence_router import router
from .shared_intelligence_shared import _with_connection


@router.get("/learning-dashboard")
async def get_learning_dashboard(project_id: str | None = Query(default=None)) -> dict[str, Any]:
    """Return learning, hardening, skill-health, and feedback dashboard sections."""

    return _with_connection(
        lambda conn: learning_hardening_dashboard_view(conn, project_id=project_id)
    )


@router.get("/adapters/projections")
async def get_adapter_projection_report(
    project_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """Return adapter config projections without writing adapter config files."""

    return _with_connection(
        lambda conn: adapter_config_projection_report(conn, project_id=project_id)
    )


@router.get("/adapters/staleness")
async def get_adapter_staleness_report(
    project_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """Return adapter projection staleness using the repo root as config root."""

    repo_root = Path(__file__).resolve().parents[3]
    return _with_connection(
        lambda conn: adapter_staleness_report(
            conn,
            config_root=repo_root,
            project_id=project_id,
        )
    )


@router.get("/context-packets/{adapter_id}")
async def preview_context_packet(
    adapter_id: str,
    project_id: str | None = Query(default=None),
    milestone_id: str | None = Query(default=None),
    task_id: str | None = Query(default=None),
    packet_type: str = Query(default="resume"),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """Preview an adapter context packet without persisting it."""

    packet_id = "dry-run-" + "-".join(
        item for item in (adapter_id, project_id or "global", packet_type) if item
    )
    return _with_connection(
        lambda conn: generate_shared_context_packet(
            conn,
            packet_id=packet_id,
            adapter_id=adapter_id,
            packet_type=packet_type,
            project_id=project_id,
            milestone_id=milestone_id,
            task_id=task_id,
            limit=limit,
            persist=False,
        )
    )
