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
    get_ready_waves,
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


@router.get("/{prd_id}/waves/ready")
async def get_prd_ready_waves(prd_id: str) -> dict[str, Any]:
    """
    Get waves that are ready to execute (all dependencies met).

    Args:
        prd_id: PRD identifier

    Returns:
        {
            "prd_id": "unified-discovery",
            "ready_waves": [
                {
                    "wave_id": "wave-4",
                    "tasks": [
                        {"task_id": "T006", "task_name": "...", "status": "pending"},
                        ...
                    ]
                },
                ...
            ],
            "count": 2
        }
    """
    # Verify PRD exists
    prd = get_prd_by_id(prd_id)
    if not prd:
        raise HTTPException(status_code=404, detail=f"PRD '{prd_id}' not found")

    waves = get_ready_waves(prd_id)

    return {"prd_id": prd_id, "ready_waves": waves, "count": len(waves)}


@router.get("/{prd_id}/progress")
async def get_prd_progress(prd_id: str) -> dict[str, Any]:
    """
    Get PRD progress broken down by phase.

    Args:
        prd_id: PRD identifier

    Returns:
        {
            "prd_id": "unified-discovery",
            "overall": {
                "total_tasks": 14,
                "completed_tasks": 6,
                "pct_complete": 42.9
            },
            "by_phase": [
                {
                    "phase": "Phase 1: Setup",
                    "total": 3,
                    "completed": 3,
                    "pct_complete": 100.0
                },
                ...
            ]
        }
    """
    prd = get_prd_by_id(prd_id)
    if not prd:
        raise HTTPException(status_code=404, detail=f"PRD '{prd_id}' not found")

    tasks = get_tasks_by_prd(prd_id)

    # Overall progress
    overall = {
        "total_tasks": len(tasks),
        "completed_tasks": sum(1 for t in tasks if t["status"] == "completed"),
        "pct_complete": prd.get("pct_complete", 0.0),
    }

    # Progress by phase
    phases: dict[str, dict] = {}
    for task in tasks:
        phase = task.get("phase") or "No Phase"
        if phase not in phases:
            phases[phase] = {"total": 0, "completed": 0}

        phases[phase]["total"] += 1
        if task["status"] == "completed":
            phases[phase]["completed"] += 1

    by_phase = []
    for phase, stats in sorted(phases.items()):
        pct = round(100.0 * stats["completed"] / stats["total"], 1) if stats["total"] > 0 else 0.0
        by_phase.append(
            {
                "phase": phase,
                "total": stats["total"],
                "completed": stats["completed"],
                "pct_complete": pct,
            }
        )

    return {"prd_id": prd_id, "overall": overall, "by_phase": by_phase}


@router.get("/{prd_id}/handoffs")
async def get_prd_handoffs(prd_id: str, limit: int = 10) -> dict[str, Any]:
    """
    Get recent handoffs for a PRD.

    Args:
        prd_id: PRD identifier
        limit: Maximum number of handoffs to return (default: 10)

    Returns:
        {
            "prd_id": "unified-discovery",
            "handoffs": [
                {
                    "handoff_id": 199,
                    "created_at": "2026-05-05T19:00:00Z",
                    "next_action": "...",
                    "working": [...],
                    "pending_decisions": [...]
                },
                ...
            ],
            "count": 2
        }
    """
    prd = get_prd_by_id(prd_id)
    if not prd:
        raise HTTPException(status_code=404, detail=f"PRD '{prd_id}' not found")

    try:
        conn = _connect()
        rows = conn.execute(
            """
            SELECT
                handoff_id, prd_id, working, broken,
                pending_decisions, next_action, lessons_json,
                created_at
            FROM prd_handoffs
            WHERE prd_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """,
            (prd_id, limit),
        ).fetchall()
        conn.close()

        import json

        handoffs = []
        for row in rows:
            handoffs.append(
                {
                    "handoff_id": row[0],
                    "prd_id": row[1],
                    "working": json.loads(row[2]) if row[2] else [],
                    "broken": json.loads(row[3]) if row[3] else [],
                    "pending_decisions": json.loads(row[4]) if row[4] else [],
                    "next_action": row[5],
                    "lessons": json.loads(row[6]) if row[6] else [],
                    "created_at": row[7],
                }
            )

        return {"prd_id": prd_id, "handoffs": handoffs, "count": len(handoffs)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
