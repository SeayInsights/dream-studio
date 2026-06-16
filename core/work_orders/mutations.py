"""Work-order lifecycle mutations: task-done, block, unblock."""

from __future__ import annotations

import os
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

        remaining = conn.execute(
            "SELECT COUNT(*) FROM business_tasks"
            " WHERE work_order_id = ? AND status NOT IN ('complete', 'cancelled')",
            (work_order_id,),
        ).fetchone()[0]
        # Task is being completed via event but not yet written directly; subtract 1
        # unless the projection already applied a prior completion for this task.
        if t_status not in ("complete", "cancelled"):
            remaining -= 1

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

    # Materialize the task.completed event into the business_tasks read model now,
    # mirroring create_task/create_work_order. Without this, status stays 'pending'
    # in the read model (and `ds work-order tasks`) until an unrelated sync_tick()
    # runs — the WO-TASKDONE-SYNC defect.
    try:
        from core.projections.runner import sync_tick as _sync_tick

        _sync_tick()
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

        conn.execute(
            "UPDATE business_work_orders"
            " SET status = 'blocked', blocked_at = ?, block_reason = ?,"
            " updated_at = ?, last_updated_at = ?"
            " WHERE work_order_id = ?",
            (now, reason, now, now, work_order_id),
        )

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
            "SELECT work_order_id, title, status, project_id FROM business_work_orders"
            " WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if wo_row is None:
            return {"ok": False, "error": f"Work order not found: {work_order_id}"}

        _, title, wo_status, project_id = wo_row
        if wo_status != "blocked":
            return {
                "ok": False,
                "error": f"Work order is not blocked (status: {wo_status})",
            }

        now = datetime.now(timezone.utc).isoformat()

        conn.execute(
            "UPDATE business_work_orders"
            " SET status = 'in_progress', unblocked_at = ?, block_reason = NULL,"
            " updated_at = ?, last_updated_at = ?"
            " WHERE work_order_id = ?",
            (now, now, now, work_order_id),
        )

    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        _spool_writer.write_event(
            CanonicalEventEnvelope(
                event_type="work_order.unblocked",
                session_id=None,
                payload={
                    "work_order_id": work_order_id,
                    "title": title,
                    "project_id": project_id,
                },
                timestamp=now,
                severity="info",
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

    return {
        "ok": True,
        "work_order_id": work_order_id,
        "status": "in_progress",
    }


def reopen_work_order(
    *,
    work_order_id: str,
    reason: str = "",
    source_root: Path | None = None,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Set a closed work order back to in_progress (designated business-state writer).

    Used by the outcome eval (core/eval/runner.py) when a closed WO's symptom
    regresses after close. Keeping this UPDATE in the work-order mutation layer —
    rather than writing business_work_orders from the eval layer — respects the
    authority boundary (dependency Rule 3: the work-order layer is the designated
    writer of business_* state). Emits ``work_order.reopened`` and syncs the read
    model, mirroring block/unblock.
    """
    db_path = _require_db(source_root or Path.cwd(), dream_studio_home)
    with _connect(db_path) as conn:
        wo_row = conn.execute(
            "SELECT work_order_id, title, status, project_id FROM business_work_orders"
            " WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if wo_row is None:
            return {"ok": False, "error": f"Work order not found: {work_order_id}"}

        _, title, prev_status, project_id = wo_row
        now = datetime.now(timezone.utc).isoformat()

        conn.execute(
            "UPDATE business_work_orders"
            " SET status = 'in_progress', updated_at = ?, last_updated_at = ?"
            " WHERE work_order_id = ?",
            (now, now, work_order_id),
        )

    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        _spool_writer.write_event(
            CanonicalEventEnvelope(
                event_type="work_order.reopened",
                session_id=None,
                payload={
                    "work_order_id": work_order_id,
                    "title": title,
                    "project_id": project_id,
                    "previous_status": prev_status,
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

    try:
        from core.projections.runner import sync_tick as _sync_tick

        _sync_tick()
    except Exception:
        pass

    return {
        "ok": True,
        "work_order_id": work_order_id,
        "status": "in_progress",
        "previous_status": prev_status,
    }


def create_work_order(
    *,
    project_id: str,
    milestone_id: str | None = None,
    title: str,
    description: str = "",
    work_order_type: str | None = None,
    originating_symptom: str | None = None,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Emit a work_order.created event; WorkOrderProjection materializes the row.

    Pure event emitter — no direct INSERT to business_work_orders. The
    WorkOrderProjection daemon (5-second poll or synchronous tick) materializes
    the row from the canonical event. Cross-session reads are unaffected; the
    daemon runs between scope and start sessions.

    Returns::

        {"ok": True, "work_order_id": str, "project_id": str,
         "milestone_id": str | None, "title": str, "status": "created"}

    or on missing project::

        {"ok": False, "error": "Project not found: <id>"}
    """

    if milestone_id is None:
        return {
            "ok": False,
            "error": "milestone_id is required: every work order must belong to a milestone",
        }

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
        ms_row = conn.execute(
            "SELECT milestone_id FROM business_milestones WHERE milestone_id = ?",
            (milestone_id,),
        ).fetchone()
        if ms_row is None:
            return {"ok": False, "error": f"Milestone not found: {milestone_id}"}

    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        _payload: dict[str, Any] = {
            "title": title,
            "status": "created",
            "type": work_order_type or "",
        }
        if originating_symptom is not None:
            _payload["originating_symptom"] = originating_symptom
        _spool_writer.write_event(
            CanonicalEventEnvelope(
                event_type="work_order.created",
                session_id=None,
                payload=_payload,
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

    try:
        from core.projections.runner import sync_tick as _sync_tick

        _sync_tick()
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
    acceptance_criteria: str | None = None,
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
        if wo_row is not None:
            milestone_id = wo_row[1]
        # If wo_row is None the work order was just emitted as an event but not yet
        # materialized by the ProjectionRunner. Proceed with milestone_id=None — it
        # enriches the trace only and does not affect task creation correctness.

    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        _spool_writer.write_event(
            CanonicalEventEnvelope(
                event_type="task.created",
                session_id=None,
                payload={
                    "title": title,
                    "description": description,
                    "acceptance_criteria": acceptance_criteria,
                    "status": "created",
                },
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

    try:
        from core.projections.runner import sync_tick as _sync_tick

        _sync_tick()
    except Exception:
        pass

    result: dict[str, Any] = {
        "ok": True,
        "task_id": task_id,
        "work_order_id": work_order_id,
        "title": title,
        "status": "pending",
    }
    if acceptance_criteria is not None:
        result["acceptance_criteria"] = acceptance_criteria
    return result


def set_originating_symptom(
    *,
    work_order_id: str,
    symptom: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Set or update the originating_symptom on an existing work order.

    Direct UPDATE — used for post-creation backfills and defect WOs registered
    before the symptom was known. Emits no spool event (the field is metadata,
    not a lifecycle transition).

    Returns ``{"ok": True, "work_order_id": str}`` or ``{"ok": False, "error": ...}``.
    """
    db_path = _require_db(source_root, dream_studio_home)
    now = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT work_order_id FROM business_work_orders WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if row is None:
            return {"ok": False, "error": f"Work order not found: {work_order_id}"}
        conn.execute(
            "UPDATE business_work_orders SET originating_symptom = ?, updated_at = ?"
            " WHERE work_order_id = ?",
            (symptom, now, work_order_id),
        )
    return {"ok": True, "work_order_id": work_order_id}


def _settings_path_for_todowrite(source_root: Path) -> Path:
    return source_root / ".claude" / "settings.json"


def todowrite_should_emit(source_root: Path) -> bool:
    """Whether to emit a TodoWrite update payload (only inside Claude Code)."""

    return (
        bool(os.environ.get("CLAUDE_CODE")) or _settings_path_for_todowrite(source_root).is_file()
    )
