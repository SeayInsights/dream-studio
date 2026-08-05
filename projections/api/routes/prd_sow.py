"""PRD + Statement-of-Work dashboard route (WO P5).

Read-only API surface over the derived PRD+SOW panel (projections/api/lib/prd_sow_panel).
`/active` serves the active project; `/{project_id}` serves a named one. It calls the no-write
derivation, so hitting the dashboard never mutates the docstore.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from core.config.database import get_connection
from projections.api.lib.prd_sow_panel import build_prd_sow_panel

router = APIRouter()


def _active_project_id() -> str | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT project_id FROM business_projects WHERE status = 'active'"
            " ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


@router.get("/active")
async def prd_sow_active() -> dict[str, Any]:
    """The PRD+SOW panel for the active project."""
    project_id = _active_project_id()
    if not project_id:
        raise HTTPException(status_code=404, detail="No active project")
    return build_prd_sow_panel(project_id)


@router.get("/{project_id}")
async def prd_sow_for_project(project_id: str) -> dict[str, Any]:
    """The PRD+SOW panel for a named project."""
    return build_prd_sow_panel(project_id)
