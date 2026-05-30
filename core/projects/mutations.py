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
            "SELECT project_id FROM business_projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if row is None:
            return {"ok": False, "error": f"Project not found: {project_id}"}
        # Collect IDs of currently-active projects before displacing them.
        displaced_ids = [
            r[0]
            for r in conn.execute(
                "SELECT project_id FROM business_projects WHERE status = 'active'",
            ).fetchall()
        ]
        # Dual-write: direct SQL for synchronous callers + events for ProjectProjection.
        conn.execute("UPDATE business_projects SET status = 'paused' WHERE status = 'active'")
        conn.execute(
            "UPDATE business_projects SET status = 'active', updated_at = ? WHERE project_id = ?",
            (now, project_id),
        )
        conn.commit()
    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        for displaced_id in displaced_ids:
            _spool_writer.write_event(
                CanonicalEventEnvelope(
                    event_type="project.deactivated",
                    session_id=None,
                    payload={"project_id": displaced_id},
                    timestamp=now,
                    severity="info",
                    trace={
                        "domain": "sdlc",
                        "project_id": displaced_id,
                        "attribution_status": "fully_attributed",
                    },
                ).to_dict()
            )
        _spool_writer.write_event(
            CanonicalEventEnvelope(
                event_type="project.activated",
                session_id=None,
                payload={"project_id": project_id},
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
            "SELECT project_id FROM business_projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if row is None:
            return {"ok": False, "error": f"Project not found: {project_id}"}
        # Dual-write: direct SQL for synchronous callers + event for ProjectProjection.
        conn.execute(
            "UPDATE business_projects SET status = 'paused', updated_at = ? WHERE project_id = ?",
            (now, project_id),
        )
        conn.commit()
    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        _spool_writer.write_event(
            CanonicalEventEnvelope(
                event_type="project.deactivated",
                session_id=None,
                payload={"project_id": project_id},
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

        now = datetime.now(timezone.utc).isoformat()

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


def _write_project_marker(
    project_path: Path,
    project_id: str,
    project_name: str,
    created_at: str,
) -> None:
    """Write the JSON .dream-studio-project marker file to project_path."""
    import json as _json
    import subprocess

    git_remote_url: str | None = None
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            cwd=str(project_path),
            timeout=5,
        )
        if result.returncode == 0:
            git_remote_url = result.stdout.strip() or None
    except Exception:
        pass

    marker_content = {
        "schema_version": 1,
        "project_id": project_id,
        "project_name": project_name,
        "created_at": created_at,
        "metadata": {
            "git_remote_url": git_remote_url,
            "registered_from_path": str(project_path.resolve()),
        },
    }
    marker_path = project_path / ".dream-studio-project"
    marker_path.write_text(_json.dumps(marker_content, indent=2), encoding="utf-8")


def register_project(
    *,
    name: str,
    description: str = "",
    project_path: Path | None = None,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Insert a new project row with status 'active'.

    When ``project_path`` is provided, writes a .dream-studio-project JSON
    marker to that directory so the CWD resolver can attribute token events
    to this project. When omitted (programmatic/test callers), logs a warning
    to the diagnostic stream.

    Returns::

        {"ok": True, "project_id": str, "name": str,
         "status": "active", "created_at": str,
         "marker_written": bool}
    """

    db_path = _require_db(source_root, dream_studio_home)
    project_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    resolved_path = str(Path(project_path).resolve()) if project_path is not None else None
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO business_projects"
            " (project_id, name, description, status, project_path, created_at, updated_at)"
            " VALUES (?, ?, ?, 'active', ?, ?, ?)",
            (project_id, name, description, resolved_path, now, now),
        )
        conn.commit()

    marker_written = False
    if project_path is not None:
        try:
            _write_project_marker(
                project_path=Path(project_path).resolve(),
                project_id=project_id,
                project_name=name,
                created_at=now,
            )
            marker_written = True
        except Exception as exc:
            try:
                from core.telemetry.diagnostics import log_diagnostic

                log_diagnostic(
                    category="failure",
                    source="register_project._write_project_marker",
                    context={"project_path": str(project_path), "project_id": project_id},
                    details={"error_type": type(exc).__name__, "error_message": str(exc)},
                )
            except Exception:
                pass
    else:
        try:
            from core.telemetry.diagnostics import log_diagnostic

            log_diagnostic(
                category="anomaly",
                source="register_project",
                context={"project_id": project_id, "name": name},
                details={
                    "error_message": (
                        "register_project called without project_path; "
                        "marker not created; CWD attribution will not work for this project"
                    )
                },
            )
        except Exception:
            pass

    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        _spool_writer.write_event(
            CanonicalEventEnvelope(
                event_type="project.created",
                session_id=None,
                payload={"name": name, "description": description, "status": "active"},
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
        "name": name,
        "status": "active",
        "created_at": now,
        "marker_written": marker_written,
    }
