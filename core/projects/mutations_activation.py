"""Project activation/deactivation mutations.

WO-GF-CORE-DATA-split: split from core/projects/mutations.py — see
mutations_shared.py for the module-level split rationale.
"""

from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect
from .mutations_shared import _require_db


def set_active_project(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    db_path = _require_db(source_root, dream_studio_home)
    now = datetime.now(UTC).isoformat()
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
    now = datetime.now(UTC).isoformat()
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
