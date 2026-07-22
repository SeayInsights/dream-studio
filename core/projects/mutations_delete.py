"""Project deletion mutation (cascade delete).

WO-GF-CORE-DATA-split: split from core/projects/mutations.py — see
mutations_shared.py for the module-level split rationale.
"""

from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect
from .mutations_shared import _require_db


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
            "SELECT project_id FROM business_projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if row is None:
            return {"ok": False, "error": f"Project not found: {project_id}"}

        wo_count = conn.execute(
            "SELECT COUNT(*) FROM business_work_orders WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]
        ms_count = conn.execute(
            "SELECT COUNT(*) FROM business_milestones WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]
        task_count = conn.execute(
            "SELECT COUNT(*) FROM business_tasks WHERE project_id = ?",
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

        # Collect entity data for post-delete events before removing rows.
        task_rows = conn.execute(
            "SELECT t.task_id, t.work_order_id, t.project_id, wo.milestone_id"
            " FROM business_tasks t"
            " LEFT JOIN business_work_orders wo ON t.work_order_id = wo.work_order_id"
            " WHERE t.project_id = ?",
            (project_id,),
        ).fetchall()
        wo_rows = conn.execute(
            "SELECT work_order_id FROM business_work_orders WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        milestone_rows = conn.execute(
            "SELECT milestone_id FROM business_milestones WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        brief_rows: list = []
        try:
            brief_rows = conn.execute(
                "SELECT brief_id FROM business_design_briefs WHERE project_id = ?",
                (project_id,),
            ).fetchall()
        except Exception:
            pass  # Table may not exist in all schema versions.

        # Dual-write: direct SQL for synchronous callers + events for projections.
        conn.execute("DELETE FROM business_tasks WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM business_work_orders WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM business_milestones WHERE project_id = ?", (project_id,))
        try:
            conn.execute("DELETE FROM business_design_briefs WHERE project_id = ?", (project_id,))
        except Exception:
            pass  # Table may not exist in all schema versions.
        conn.execute("DELETE FROM business_projects WHERE project_id = ?", (project_id,))
        conn.commit()

    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        now = datetime.now(UTC).isoformat()

        for t_task_id, t_work_order_id, t_project_id, t_milestone_id in task_rows:
            _spool_writer.write_event(
                CanonicalEventEnvelope(
                    event_type="task.deleted",
                    session_id=None,
                    payload={
                        "deletion_context": "cascaded_from_project_delete",
                        "project_id": project_id,
                    },
                    timestamp=now,
                    severity="info",
                    trace={
                        "domain": "sdlc",
                        "project_id": t_project_id,
                        "milestone_id": t_milestone_id,
                        "work_order_id": t_work_order_id,
                        "task_id": t_task_id,
                        "attribution_status": "fully_attributed",
                    },
                ).to_dict()
            )
        for (wo_id,) in wo_rows:
            _spool_writer.write_event(
                CanonicalEventEnvelope(
                    event_type="work_order.deleted",
                    session_id=None,
                    payload={
                        "work_order_id": wo_id,
                        "project_id": project_id,
                        "deletion_context": "cascaded_from_project_delete",
                    },
                    timestamp=now,
                    severity="info",
                    trace={
                        "domain": "sdlc",
                        "project_id": project_id,
                        "work_order_id": wo_id,
                        "attribution_status": "fully_attributed",
                    },
                ).to_dict()
            )
        for (ms_id,) in milestone_rows:
            _spool_writer.write_event(
                CanonicalEventEnvelope(
                    event_type="milestone.deleted",
                    session_id=None,
                    payload={
                        "milestone_id": ms_id,
                        "project_id": project_id,
                        "deletion_context": "cascaded_from_project_delete",
                    },
                    timestamp=now,
                    severity="info",
                    trace={
                        "domain": "sdlc",
                        "project_id": project_id,
                        "milestone_id": ms_id,
                        "attribution_status": "fully_attributed",
                    },
                ).to_dict()
            )
        for (brief_id,) in brief_rows:
            _spool_writer.write_event(
                CanonicalEventEnvelope(
                    event_type="design_brief.deleted",
                    session_id=None,
                    payload={
                        "brief_id": brief_id,
                        "project_id": project_id,
                        "deletion_context": "cascaded_from_project_delete",
                    },
                    timestamp=now,
                    severity="info",
                    trace={
                        "domain": "sdlc",
                        "project_id": project_id,
                        "brief_id": brief_id,
                        "attribution_status": "fully_attributed",
                    },
                ).to_dict()
            )
        _spool_writer.write_event(
            CanonicalEventEnvelope(
                event_type="project.deleted",
                session_id=None,
                payload={
                    "cascade_milestones": ms_count,
                    "cascade_work_orders": wo_count,
                    "cascade_tasks": task_count,
                },
                timestamp=now,
                severity="info",
                trace={
                    "domain": "sdlc",
                    "project_id": project_id,
                    "attribution_status": "fully_attributed",
                },
            ).to_dict()
        )
    except Exception:
        pass

    return {
        "ok": True,
        "project_id": project_id,
        "deleted": {
            "tasks": task_count,
            "work_orders": wo_count,
            "milestones": ms_count,
        },
    }
