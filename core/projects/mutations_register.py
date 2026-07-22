"""Project registration mutation + marker-file helper.

WO-GF-CORE-DATA-split: split from core/projects/mutations.py — see
mutations_shared.py for the module-level split rationale.
"""

from __future__ import annotations

import uuid
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect
from .mutations_shared import _require_db


def _write_project_marker(
    project_path: Path,
    project_id: str,
    project_name: str,
    created_at: str,
    db_path: Path | None = None,
) -> None:
    """Write the JSON .dream-studio-project marker file to project_path.

    Guards:
    1. Refuses to overwrite an existing marker for a DIFFERENT project.
    2. When db_path is provided, refuses to write if project_id is not found
       in business_projects (prevents ghost markers from deleted or phantom projects).
    """
    import json as _json
    import subprocess

    marker_path = project_path / ".dream-studio-project"

    # Guard: refuse to write a marker for a project that doesn't exist in the authority.
    if db_path is not None:
        import sqlite3 as _sqlite3

        try:
            conn = _sqlite3.connect(str(db_path), timeout=2.0)
            try:
                row = conn.execute(
                    "SELECT 1 FROM business_projects WHERE project_id = ?",
                    (project_id,),
                ).fetchone()
            finally:
                conn.close()
        except Exception as _exc:
            row = None
            try:
                from core.telemetry.diagnostics import log_diagnostic

                log_diagnostic(
                    category="anomaly",
                    source="_write_project_marker",
                    context={"project_path": str(project_path), "project_id": project_id},
                    details={"error_message": f"DB read failed during existence check: {_exc}"},
                )
            except Exception:
                pass
        if row is None:
            raise ValueError(
                f"Cannot write marker for project {project_id} to {project_path}: "
                "project_id does not exist in business_projects. "
                "Register the project before writing its marker."
            )

    # Guard: refuse to overwrite a marker for a DIFFERENT project.
    if marker_path.exists():
        try:
            existing_raw = marker_path.read_text(encoding="utf-8").strip()
            existing_data = _json.loads(existing_raw) if existing_raw.startswith("{") else {}
            existing_id = existing_data.get("project_id") or (
                existing_raw.splitlines()[0].strip() if existing_raw else ""
            )
        except (OSError, _json.JSONDecodeError):
            existing_id = ""  # unreadable or malformed — allow write to overwrite
        if existing_id and existing_id != project_id:
            try:
                from core.telemetry.diagnostics import log_diagnostic

                log_diagnostic(
                    category="anomaly",
                    source="_write_project_marker",
                    context={"project_path": str(project_path), "project_id": project_id},
                    details={
                        "error_message": "Refusing to overwrite existing marker for a different project",
                        "existing_project_id": existing_id,
                        "new_project_id": project_id,
                    },
                )
            except Exception:
                pass
            raise ValueError(
                f"Cannot write marker for project {project_id} to {project_path}: "
                f"path already has a marker for project {existing_id}. "
                "Delete the existing marker manually if this is intentional."
            )

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
    marker_path.write_text(_json.dumps(marker_content, indent=2), encoding="utf-8")


def register_project(
    *,
    name: str,
    description: str = "",
    project_path: Path | None = None,
    write_marker: bool = True,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Insert a new project row with status 'active'.

    When ``project_path`` is provided and ``write_marker=True`` (default),
    writes a .dream-studio-project JSON marker so the CWD resolver can
    attribute token events. Set ``write_marker=False`` for brownfield
    one-time scans (no-marker default) — project_path is still stored in
    business_projects for the SQLite path-fallback resolver.

    Returns::

        {"ok": True, "project_id": str, "name": str,
         "status": "active", "created_at": str,
         "marker_written": bool}
    """

    db_path = _require_db(source_root, dream_studio_home)
    project_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    resolved_path = str(Path(project_path).resolve()) if project_path is not None else None
    with _connect(db_path) as conn:
        # Idempotency: return existing project when same project_path already registered.
        if resolved_path is not None:
            existing = conn.execute(
                "SELECT project_id, name, status, created_at FROM business_projects"
                " WHERE project_path = ? AND status != 'archived'"
                " ORDER BY created_at ASC LIMIT 1",
                (resolved_path,),
            ).fetchone()
            if existing is not None:
                return {
                    "ok": True,
                    "project_id": existing["project_id"],
                    "name": existing["name"],
                    "status": existing["status"],
                    "created_at": existing["created_at"],
                    "marker_written": False,
                    "idempotent": True,
                }
        conn.execute(
            "INSERT INTO business_projects"
            " (project_id, name, description, status, project_path, created_at, updated_at)"
            " VALUES (?, ?, ?, 'active', ?, ?, ?)",
            (project_id, name, description, resolved_path, now, now),
        )
        conn.commit()

    marker_written = False
    if project_path is not None and write_marker:
        try:
            _write_project_marker(
                project_path=Path(project_path).resolve(),
                project_id=project_id,
                project_name=name,
                created_at=now,
                db_path=db_path,
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
