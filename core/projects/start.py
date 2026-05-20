"""Project-start composer: activate a project + auto-start its next open WO.

This module replaces the monolithic `_project_start` handler that lived in
`interfaces/cli/ds.py`. It is a thin composer over three pieces that
already exist as importable functions after A1, A2.1, and A2.2:

- `core.projects.mutations.set_active_project` — demote any other active
  project to ``paused`` and mark this one ``active``.
- `core.projects.queries.get_next_work_order` — pick the next WO to start
  (in-progress first, then the first open WO in the earliest milestone).
- `core.work_orders.start.start_work_order` — the A2.1 composer that
  writes context.md, mutates to in_progress, and emits the
  ``work_order.started`` spool event.

The pure path returns a single compound dict — no `print()`, no
`sys.exit`. Skills/workflows should call `start_project` directly; the
CLI wrapper in `ds.py` is the only caller that converts the dict into
the human-readable operator output (project name, "Starting: ..." line,
"No open work orders" message).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect
from core.projects.mutations import set_active_project
from core.projects.queries import get_next_work_order
from core.work_orders.start import start_work_order


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


def _lookup_project_name(db_path: Path, project_id: str) -> str | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT name FROM ds_projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
    return row[0] if row else None


def _count_tasks_in_context(context_path: Path) -> int:
    if not context_path.is_file():
        return 0
    return context_path.read_text(encoding="utf-8").count("- [ ]")


def start_project(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
    planning_root: Path | None = None,
    accept_no_brief: bool = False,
) -> dict[str, Any]:
    """Activate a project and start its next open work order.

    Returns one of three shapes:

    Project not found::

        {"ok": False, "error": "Project not found: <id>"}

    No open work orders (project still gets activated)::

        {
            "ok": True,
            "project_id": str,
            "project_name": str,
            "project_status": "active",
            "no_open_work_orders": True,
        }

    Work order successfully started::

        {
            "ok": True,
            "project_id": str,
            "project_name": str,
            "project_status": "active",
            "next_work_order": {
                "work_order_id": str,
                "title": str,
                "work_order_type": str,
                "milestone": str,
                "next_command": str,
            },
            "work_order_start": {...},   # full start_work_order dict
            "context_path": str | None,
            "tasks_count": int,
        }

    If `start_work_order` itself returns ``ok: False`` (e.g. UI WO blocked
    on a missing brief, or earlier-milestone WOs incomplete), the failed
    dict is propagated as-is so the caller can decide how to handle it.
    """

    db_path = _require_db(source_root, dream_studio_home)

    set_result = set_active_project(
        project_id=project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not set_result.get("ok"):
        return set_result

    project_name = _lookup_project_name(db_path, project_id) or project_id

    next_result = get_next_work_order(
        project_id=project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not next_result.get("ok"):
        return next_result

    next_wo = next_result.get("work_order")
    if next_wo is None:
        return {
            "ok": True,
            "project_id": project_id,
            "project_name": project_name,
            "project_status": "active",
            "no_open_work_orders": True,
        }

    start_result = start_work_order(
        work_order_id=next_wo["work_order_id"],
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        planning_root=planning_root,
        accept_no_brief=accept_no_brief,
    )
    if not start_result.get("ok"):
        return start_result

    context_path_str = start_result.get("context_path")
    tasks_count = 0
    if context_path_str:
        tasks_count = _count_tasks_in_context(Path(context_path_str))

    return {
        "ok": True,
        "project_id": project_id,
        "project_name": project_name,
        "project_status": "active",
        "next_work_order": next_wo,
        "work_order_start": start_result,
        "context_path": context_path_str,
        "tasks_count": tasks_count,
    }
