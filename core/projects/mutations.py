"""Project lifecycle mutations.

Skills, workflows, and hooks should import these directly instead of
shelling out to `ds project set-active` / `ds project deactivate`. Each
function returns a dict; the CLI wrapper in `interfaces/cli/ds.py` is
responsible for serialization.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
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


def set_active_project(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    db_path = _require_db(source_root, dream_studio_home)
    now = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT project_id FROM ds_projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if row is None:
            return {"ok": False, "error": f"Project not found: {project_id}"}
        conn.execute(
            "UPDATE ds_projects SET status = 'paused', updated_at = ? WHERE status = 'active'",
            (now,),
        )
        conn.execute(
            "UPDATE ds_projects SET status = 'active', updated_at = ? WHERE project_id = ?",
            (now, project_id),
        )
        conn.commit()
    return {"ok": True, "project_id": project_id, "status": "active"}


def deactivate_project(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    db_path = _require_db(source_root, dream_studio_home)
    now = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT project_id FROM ds_projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if row is None:
            return {"ok": False, "error": f"Project not found: {project_id}"}
        conn.execute(
            "UPDATE ds_projects SET status = 'paused', updated_at = ? WHERE project_id = ?",
            (now, project_id),
        )
        conn.commit()
    return {"ok": True, "project_id": project_id, "status": "paused"}


def delete_project(
    *,
    project_id: str,
    confirm: bool = False,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Delete a project. Cascades to tasks, work orders, milestones, and
    design briefs that belong to the project.

    Returns one of three shapes:

    Missing project::

        {"ok": False, "error": "Project not found: <id>"}

    Project has dependents and ``confirm`` is False (the safe default)::

        {"ok": False,
         "error": "Project <id> has dependents (... tasks, ... work orders,
                   ... milestones). Pass confirm=True to cascade delete.",
         "work_order_count": int, "milestone_count": int, "task_count": int}

    Success::

        {"ok": True, "project_id": str,
         "deleted": {"tasks": int, "work_orders": int, "milestones": int}}
    """

    db_path = _require_db(source_root, dream_studio_home)
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT project_id FROM ds_projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if row is None:
            return {"ok": False, "error": f"Project not found: {project_id}"}

        wo_count = conn.execute(
            "SELECT COUNT(*) FROM ds_work_orders WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]
        ms_count = conn.execute(
            "SELECT COUNT(*) FROM ds_milestones WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]
        task_count = conn.execute(
            "SELECT COUNT(*) FROM ds_tasks WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]

        has_dependents = wo_count > 0 or ms_count > 0 or task_count > 0
        if has_dependents and not confirm:
            return {
                "ok": False,
                "error": (
                    f"Project {project_id} has dependents "
                    f"({task_count} tasks, {wo_count} work orders, "
                    f"{ms_count} milestones). "
                    "Pass confirm=True to cascade delete."
                ),
                "work_order_count": wo_count,
                "milestone_count": ms_count,
                "task_count": task_count,
            }

        # Cascade: tasks → work_orders → milestones → design_briefs → projects
        conn.execute("DELETE FROM ds_tasks WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM ds_work_orders WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM ds_milestones WHERE project_id = ?", (project_id,))
        try:
            conn.execute("DELETE FROM ds_design_briefs WHERE project_id = ?", (project_id,))
        except Exception:
            pass  # Table may not exist in all schema versions.
        conn.execute("DELETE FROM ds_projects WHERE project_id = ?", (project_id,))
        conn.commit()

    return {
        "ok": True,
        "project_id": project_id,
        "deleted": {
            "tasks": task_count,
            "work_orders": wo_count,
            "milestones": ms_count,
        },
    }


def register_project(
    *,
    name: str,
    description: str = "",
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Insert a new project row with status 'active'.

    Returns::

        {"ok": True, "project_id": str, "name": str,
         "status": "active", "created_at": str}
    """

    db_path = _require_db(source_root, dream_studio_home)
    project_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO ds_projects"
            " (project_id, name, description, status, created_at, updated_at)"
            " VALUES (?, ?, ?, 'active', ?, ?)",
            (project_id, name, description, now, now),
        )
        conn.commit()
    return {
        "ok": True,
        "project_id": project_id,
        "name": name,
        "status": "active",
        "created_at": now,
    }
