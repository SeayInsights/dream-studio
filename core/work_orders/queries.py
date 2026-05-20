"""Read-only work-order queries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect


def _require_db(source_root: Path, dream_studio_home: Path | None) -> Path:
    # Lazy import via ds.py — see core.projects.queries._require_db for rationale.
    from interfaces.cli.ds import resolve_installed_runtime_paths

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing. Run rehearsal-install first.")
    return paths.sqlite_path


def list_work_orders(
    *,
    project_id: str | None = None,
    status_filter: str | None = None,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    db_path = _require_db(source_root, dream_studio_home)

    conditions: list[str] = []
    params: list[Any] = []
    if project_id:
        conditions.append("wo.project_id = ?")
        params.append(project_id)
    if status_filter:
        conditions.append("wo.status = ?")
        params.append(status_filter)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    query = (
        "SELECT wo.work_order_id, wo.title, wo.work_order_type, wo.status,"
        " m.title AS milestone_title"
        " FROM ds_work_orders wo"
        " LEFT JOIN ds_milestones m ON wo.milestone_id = m.milestone_id"
        f" {where}"
        " ORDER BY wo.created_at ASC"
    )

    with _connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()

    work_orders = [
        {
            "id": r[0],
            "title": r[1],
            "type": r[2] or "",
            "status": r[3],
            "milestone": r[4] or "",
        }
        for r in rows
    ]
    return {"ok": True, "work_orders": work_orders}


def list_tasks(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    db_path = _require_db(source_root, dream_studio_home)
    with _connect(db_path) as conn:
        wo_row = conn.execute(
            "SELECT work_order_id, title FROM ds_work_orders WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if wo_row is None:
            return {"ok": False, "error": f"Work order not found: {work_order_id}"}
        rows = conn.execute(
            "SELECT task_id, title, status FROM ds_tasks"
            " WHERE work_order_id = ? ORDER BY created_at ASC",
            (work_order_id,),
        ).fetchall()

    tasks: list[dict[str, Any]] = []
    for row in rows:
        t_id, t_title, t_status = row
        if t_status == "complete":
            indicator = "[x]"
        elif t_status == "in_progress":
            indicator = "[~]"
        else:
            indicator = "[ ]"
        tasks.append(
            {
                "task_id": t_id,
                "title": t_title,
                "status": t_status,
                "indicator": indicator,
            }
        )

    return {"ok": True, "work_order_id": work_order_id, "tasks": tasks}
