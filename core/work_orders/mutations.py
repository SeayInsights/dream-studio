"""Work-order lifecycle mutations: task-done, block, unblock, add-tasks."""

from __future__ import annotations

import os
import re
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


def mark_task_done(
    *,
    work_order_id: str,
    task_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
    planning_root: Path | None = None,
) -> dict[str, Any]:
    db_path = _require_db(source_root, dream_studio_home)
    with _connect(db_path) as conn:
        task_row = conn.execute(
            "SELECT t.task_id, t.work_order_id, t.title, t.status, t.project_id,"
            " wo.milestone_id"
            " FROM business_tasks t"
            " LEFT JOIN business_work_orders wo ON t.work_order_id = wo.work_order_id"
            " WHERE t.task_id = ?",
            (task_id,),
        ).fetchone()
        if task_row is None:
            return {"ok": False, "error": f"Task not found: {task_id}"}

        t_id, t_wo_id, t_title, t_status, t_project_id, t_milestone_id = task_row
        if t_wo_id != work_order_id:
            return {
                "ok": False,
                "error": f"Task {task_id} does not belong to work order {work_order_id}",
            }

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE business_tasks SET status = 'complete', updated_at = ? WHERE task_id = ?",
            (now, task_id),
        )
        conn.commit()

        remaining = conn.execute(
            "SELECT COUNT(*) FROM business_tasks"
            " WHERE work_order_id = ? AND status NOT IN ('complete', 'cancelled')",
            (work_order_id,),
        ).fetchone()[0]

        task_index = (
            conn.execute(
                "SELECT COUNT(*) FROM business_tasks"
                " WHERE work_order_id = ? AND created_at <= ("
                "   SELECT created_at FROM business_tasks WHERE task_id = ?"
                ")",
                (work_order_id, task_id),
            ).fetchone()[0]
            - 1
        )

    p_root = planning_root or Path.cwd() / ".planning"
    context_path = p_root / "work-orders" / work_order_id / "context.md"
    if context_path.is_file():
        text = context_path.read_text(encoding="utf-8")
        text = text.replace(f"- [ ] {t_title}", f"- [x] {t_title}", 1)
        context_path.write_text(text, encoding="utf-8")

    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        _spool_writer.write_event(
            CanonicalEventEnvelope(
                event_type="task.completed",
                session_id=None,
                payload={
                    "task_id": task_id,
                    "work_order_id": work_order_id,
                    "tasks_remaining": remaining,
                },
                timestamp=now,
                severity="info",
                trace={
                    "domain": "sdlc",
                    "project_id": t_project_id,
                    "milestone_id": t_milestone_id,
                    "work_order_id": work_order_id,
                    "task_id": task_id,
                    "attribution_status": "fully_attributed",
                },
            ).to_dict()
        )
    except Exception:
        pass

    try:
        from core.sdlc.active_task import clear_active_task as _clear_active_task
        from core.sdlc.active_task import get_active_task as _get_active_task

        _active = _get_active_task()
        if _active is not None and _active.task_id == task_id:
            _clear_active_task()
    except Exception:
        pass

    result: dict[str, Any] = {
        "ok": True,
        "task_id": task_id,
        "work_order_id": work_order_id,
        "title": t_title,
        "status": "complete",
        "tasks_remaining": remaining,
        "task_index": task_index,
    }
    if remaining == 0:
        result["all_tasks_complete"] = True
        result["suggested_action"] = (
            f"All tasks complete. Close work order: ds work-order close {work_order_id}"
        )
    return result


def block_work_order(
    *,
    work_order_id: str,
    reason: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    db_path = _require_db(source_root, dream_studio_home)
    with _connect(db_path) as conn:
        wo_row = conn.execute(
            "SELECT work_order_id, title, project_id FROM business_work_orders WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if wo_row is None:
            return {"ok": False, "error": f"Work order not found: {work_order_id}"}

        _, title, project_id = wo_row
        now = datetime.now(timezone.utc).isoformat()

        try:
            import spool.writer as _spool_writer

            from canonical.events.envelope import CanonicalEventEnvelope

            _spool_writer.write_event(
                CanonicalEventEnvelope(
                    event_type="work_order.blocked",
                    session_id=None,
                    payload={
                        "work_order_id": work_order_id,
                        "title": title,
                        "project_id": project_id,
                        "reason": reason,
                    },
                    timestamp=now,
                    severity="warning",
                    trace={
                        "domain": "sdlc",
                        "work_order_id": work_order_id,
                        "project_id": project_id,
                        "attribution_status": "fully_attributed",
                    },
                ).to_dict()
            )
        except Exception:
            pass

        conn.execute(
            "UPDATE business_work_orders SET status = 'blocked', block_reason = ?, updated_at = ?"
            " WHERE work_order_id = ?",
            (reason, now, work_order_id),
        )
        conn.commit()

    return {
        "ok": True,
        "work_order_id": work_order_id,
        "status": "blocked",
        "block_reason": reason,
    }


def unblock_work_order(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    db_path = _require_db(source_root, dream_studio_home)
    with _connect(db_path) as conn:
        wo_row = conn.execute(
            "SELECT work_order_id, title, status FROM business_work_orders WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if wo_row is None:
            return {"ok": False, "error": f"Work order not found: {work_order_id}"}

        _, _, wo_status = wo_row
        if wo_status != "blocked":
            return {
                "ok": False,
                "error": f"Work order is not blocked (status: {wo_status})",
            }

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE business_work_orders SET status = 'in_progress', block_reason = NULL,"
            " updated_at = ? WHERE work_order_id = ?",
            (now, work_order_id),
        )
        conn.commit()

    return {
        "ok": True,
        "work_order_id": work_order_id,
        "status": "in_progress",
    }


def add_tasks_from_file(
    *,
    work_order_id: str,
    tasks_file: Path,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Parse a numbered-list tasks.md file and insert tasks into business_tasks."""

    if not tasks_file.is_file():
        return {"ok": False, "error": f"File not found: {tasks_file}"}

    db_path = _require_db(source_root, dream_studio_home)
    with _connect(db_path) as conn:
        wo_row = conn.execute(
            "SELECT work_order_id, project_id, milestone_id FROM business_work_orders"
            " WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if wo_row is None:
            return {"ok": False, "error": f"Work order not found: {work_order_id}"}
        project_id = wo_row[1]
        milestone_id = wo_row[2]

        text = tasks_file.read_text(encoding="utf-8").replace("\r\n", "\n")
        items = re.findall(
            r"^\s*\d+\.\s+(.+?)(?=\n\s*\d+\.|\Z)",
            text,
            re.MULTILINE | re.DOTALL,
        )
        if not items:
            return {"ok": False, "error": "No numbered list items found in file"}

        now = datetime.now(timezone.utc).isoformat()
        inserted: list[dict[str, Any]] = []
        for raw in items:
            lines = [ln.strip() for ln in raw.strip().splitlines() if ln.strip()]
            if not lines:
                continue
            t_title = lines[0]
            t_desc = " ".join(lines[1:]) if len(lines) > 1 else ""
            t_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO business_tasks"
                " (task_id, work_order_id, project_id, title, description, status,"
                " created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
                (t_id, work_order_id, project_id, t_title, t_desc, now, now),
            )
            inserted.append({"task_id": t_id, "title": t_title, "description": t_desc})
        conn.commit()

    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        emit_now = datetime.now(timezone.utc).isoformat()
        for task in inserted:
            _spool_writer.write_event(
                CanonicalEventEnvelope(
                    event_type="task.created",
                    session_id=None,
                    payload={
                        "title": task["title"],
                        "description": task["description"],
                        "status": "created",
                    },
                    timestamp=emit_now,
                    severity="info",
                    trace={
                        "domain": "sdlc",
                        "project_id": project_id,
                        "milestone_id": milestone_id,
                        "work_order_id": work_order_id,
                        "task_id": task["task_id"],
                        "attribution_status": "fully_attributed",
                    },
                ).to_dict()
            )
    except Exception:
        pass

    return {
        "ok": True,
        "work_order_id": work_order_id,
        "tasks_inserted": len(inserted),
        "tasks": [{"task_id": t["task_id"], "title": t["title"]} for t in inserted],
    }


def create_work_order(
    *,
    project_id: str,
    milestone_id: str | None = None,
    title: str,
    description: str = "",
    work_order_type: str | None = None,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Insert a new work order row with status 'created'.

    Returns::

        {"ok": True, "work_order_id": str, "project_id": str,
         "milestone_id": str | None, "title": str, "status": "created"}

    or on missing project::

        {"ok": False, "error": "Project not found: <id>"}
    """

    db_path = _require_db(source_root, dream_studio_home)
    work_order_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT project_id FROM business_projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if row is None:
            return {"ok": False, "error": f"Project not found: {project_id}"}
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, 'created', ?, ?, ?)",
            (
                work_order_id,
                project_id,
                milestone_id,
                title,
                description,
                work_order_type,
                now,
                now,
            ),
        )
        conn.commit()

    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        _spool_writer.write_event(
            CanonicalEventEnvelope(
                event_type="work_order.created",
                session_id=None,
                payload={
                    "title": title,
                    "status": "created",
                    "type": work_order_type or "",
                },
                timestamp=now,
                severity="info",
                trace={
                    "domain": "sdlc",
                    "project_id": project_id,
                    "milestone_id": milestone_id,
                    "work_order_id": work_order_id,
                    "attribution_status": "fully_attributed",
                },
            ).to_dict()
        )
    except Exception:
        pass

    return {
        "ok": True,
        "work_order_id": work_order_id,
        "project_id": project_id,
        "milestone_id": milestone_id,
        "title": title,
        "status": "created",
    }


def create_task(
    *,
    work_order_id: str,
    project_id: str,
    title: str,
    description: str = "",
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Insert a new task row with status 'pending'.

    Returns::

        {"ok": True, "task_id": str, "work_order_id": str,
         "title": str, "status": "pending"}

    or on missing work order::

        {"ok": False, "error": "Work order not found: <id>"}
    """

    db_path = _require_db(source_root, dream_studio_home)
    task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    milestone_id: str | None = None
    with _connect(db_path) as conn:
        wo_row = conn.execute(
            "SELECT work_order_id, milestone_id FROM business_work_orders WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if wo_row is None:
            return {"ok": False, "error": f"Work order not found: {work_order_id}"}
        milestone_id = wo_row[1]
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, description, status,"
            " created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
            (task_id, work_order_id, project_id, title, description, now, now),
        )
        conn.commit()

    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        _spool_writer.write_event(
            CanonicalEventEnvelope(
                event_type="task.created",
                session_id=None,
                payload={"title": title, "description": description, "status": "created"},
                timestamp=now,
                severity="info",
                trace={
                    "domain": "sdlc",
                    "project_id": project_id,
                    "milestone_id": milestone_id,
                    "work_order_id": work_order_id,
                    "task_id": task_id,
                    "attribution_status": "fully_attributed",
                },
            ).to_dict()
        )
    except Exception:
        pass

    return {
        "ok": True,
        "task_id": task_id,
        "work_order_id": work_order_id,
        "title": title,
        "status": "pending",
    }


def _settings_path_for_todowrite(source_root: Path) -> Path:
    return source_root / ".claude" / "settings.json"


def todowrite_should_emit(source_root: Path) -> bool:
    """Whether to emit a TodoWrite update payload (only inside Claude Code)."""

    return (
        bool(os.environ.get("CLAUDE_CODE")) or _settings_path_for_todowrite(source_root).is_file()
    )
