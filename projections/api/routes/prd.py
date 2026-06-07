"""PRD (Product Requirements Document) API routes."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

# Add hooks to path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hooks"))

from core.event_store.studio_db import (  # noqa: E402
    get_prd_by_id,
    get_tasks_by_prd,
    _connect,
)
from projections.api.routes.sqlite_schema import object_exists

router = APIRouter(prefix="/api/prd", tags=["prd"])


@router.get("/list")
async def list_prds() -> dict[str, Any]:
    """
    List all PRDs with status and progress.

    Returns:
        {
            "prds": [
                {
                    "prd_id": "unified-discovery",
                    "title": "Unified Discovery System",
                    "status": "approved",
                    "total_tasks": 14,
                    "completed_tasks": 6,
                    "pct_complete": 42.9,
                    "created_at": "2026-05-05T19:00:00Z"
                },
                ...
            ],
            "count": 5
        }
    """
    try:
        conn = _connect()
        if not object_exists(conn, "prd_documents"):
            conn.close()
            return {
                "prds": [],
                "count": 0,
                "source_status": {
                    "classification": "empty by design",
                    "reason": "prd_documents is absent in this installed DB; the dashboard treats PRD lists as an empty state.",
                    "missing": ["prd_documents"],
                    "derived_view": True,
                    "primary_authority": False,
                },
            }

        rows = conn.execute("""
            SELECT
                prd_id, title, status, project_id,
                created_at, approved_at, completed_at,
                total_tasks, completed_tasks,
                ROUND(100.0 * completed_tasks / NULLIF(total_tasks, 0), 1) AS pct_complete
            FROM prd_documents
            ORDER BY created_at DESC
        """).fetchall()
        conn.close()

        prds = []
        for row in rows:
            prds.append(
                {
                    "prd_id": row[0],
                    "title": row[1],
                    "status": row[2],
                    "project_id": row[3],
                    "created_at": row[4],
                    "approved_at": row[5],
                    "completed_at": row[6],
                    "total_tasks": row[7],
                    "completed_tasks": row[8],
                    "pct_complete": row[9],
                }
            )

        return {"prds": prds, "count": len(prds)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{prd_id}")
async def get_prd(prd_id: str) -> dict[str, Any]:
    """
    Get PRD details including tasks.

    Args:
        prd_id: PRD identifier (e.g., "unified-discovery")

    Returns:
        {
            "prd": {
                "prd_id": "unified-discovery",
                "title": "Unified Discovery System",
                "status": "approved",
                ...
            },
            "tasks": [
                {
                    "task_id": "T001",
                    "task_name": "Create migration SQL",
                    "status": "completed",
                    ...
                },
                ...
            ],
            "stats": {
                "total": 14,
                "completed": 6,
                "in_progress": 2,
                "pending": 6
            }
        }
    """
    try:
        prd = get_prd_by_id(prd_id)
    except Exception as exc:
        if "prd_documents" in str(exc):
            raise HTTPException(status_code=404, detail=f"PRD '{prd_id}' not found") from exc
        raise
    if not prd:
        raise HTTPException(status_code=404, detail=f"PRD '{prd_id}' not found")

    tasks = get_tasks_by_prd(prd_id)

    # Calculate stats
    stats = {
        "total": len(tasks),
        "completed": sum(1 for t in tasks if t["status"] == "completed"),
        "in_progress": sum(1 for t in tasks if t["status"] == "in_progress"),
        "pending": sum(1 for t in tasks if t["status"] == "pending"),
        "blocked": sum(1 for t in tasks if t["status"] == "blocked"),
    }

    return {"prd": prd, "tasks": tasks, "stats": stats}
