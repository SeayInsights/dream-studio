"""Project drill-down endpoints: project -> milestones -> work orders -> tasks.

WO-DASH-DRILLDOWN: a read-only hierarchy over the SQLite authority
(business_milestones / business_work_orders / business_tasks) so the dashboard's
Projects panel can drill from a project into its milestones, into each milestone's
work orders, and into each work order's tasks.

Read-only projection — no authority write, no new studio.db table, no schema change.
Every table access is object_exists-guarded so a DB snapshot missing a table
degrades to an honest empty list rather than a 500.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from projections.api.lib.project_helpers import get_db_connection
from projections.api.routes.sqlite_schema import object_exists

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/projects/{project_id}/milestones")
async def get_project_milestones(project_id: str) -> dict[str, Any]:
    """Milestones for a project (drill-down level 1)."""
    conn = get_db_connection()
    try:
        if not object_exists(conn, "business_milestones"):
            return {"project_id": project_id, "milestones": [], "count": 0}
        rows = conn.execute(
            "SELECT milestone_id, title, status FROM business_milestones"
            " WHERE project_id = ? ORDER BY created_at ASC",
            (project_id,),
        ).fetchall()
        milestones = [
            {"milestone_id": r["milestone_id"], "title": r["title"], "status": r["status"]}
            for r in rows
        ]
        return {"project_id": project_id, "milestones": milestones, "count": len(milestones)}
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error getting project milestones: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/milestones/{milestone_id}/work-orders")
async def get_milestone_work_orders(milestone_id: str) -> dict[str, Any]:
    """Work orders under a milestone (drill-down level 2)."""
    conn = get_db_connection()
    try:
        if not object_exists(conn, "business_work_orders"):
            return {"milestone_id": milestone_id, "work_orders": [], "count": 0}
        rows = conn.execute(
            "SELECT work_order_id, title, status, work_order_type FROM business_work_orders"
            " WHERE milestone_id = ? ORDER BY created_at ASC",
            (milestone_id,),
        ).fetchall()
        work_orders = [
            {
                "work_order_id": r["work_order_id"],
                "title": r["title"],
                "status": r["status"],
                "type": r["work_order_type"],
            }
            for r in rows
        ]
        return {
            "milestone_id": milestone_id,
            "work_orders": work_orders,
            "count": len(work_orders),
        }
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error getting milestone work orders: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/work-orders/{work_order_id}/tasks")
async def get_work_order_tasks(work_order_id: str) -> dict[str, Any]:
    """Tasks under a work order (drill-down level 3)."""
    conn = get_db_connection()
    try:
        if not object_exists(conn, "business_tasks"):
            return {"work_order_id": work_order_id, "tasks": [], "count": 0}
        rows = conn.execute(
            "SELECT task_id, title, status FROM business_tasks"
            " WHERE work_order_id = ? ORDER BY created_at ASC",
            (work_order_id,),
        ).fetchall()
        tasks = [
            {"task_id": r["task_id"], "title": r["title"], "status": r["status"]} for r in rows
        ]
        return {"work_order_id": work_order_id, "tasks": tasks, "count": len(tasks)}
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error getting work order tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
