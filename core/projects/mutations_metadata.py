"""Project vision/path metadata mutations.

WO-GF-CORE-DATA-split: split from core/projects/mutations.py — see
mutations_shared.py for the module-level split rationale.
"""

from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path
from typing import Any


def set_project_vision(project_id: str, vision_statement: str) -> dict:
    """Persist intended vision onto the business_projects entity (AD-10).

    Stores vision directly on the project row — not in prd_* tables (retired).
    Emits a project.vision_set canonical event for audit trail.

    Returns {"ok": True} on success, {"ok": False, "error": ...} on failure.
    """
    from core.event_store.studio_db import _connect

    now = datetime.now(UTC).isoformat()
    try:
        with _connect() as conn:
            rows = conn.execute(
                "UPDATE business_projects SET vision_statement = ?, updated_at = ? WHERE project_id = ?",
                (vision_statement.strip(), now, project_id),
            ).rowcount
            conn.commit()

        if rows == 0:
            return {"ok": False, "error": f"project not found: {project_id}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        _spool_writer.write_event(
            CanonicalEventEnvelope(
                event_type="project.vision_set",
                session_id=None,
                payload={"vision_statement": vision_statement},
                timestamp=now,
                severity="info",
                trace={"domain": "sdlc", "project_id": project_id},
            ).to_dict()
        )
    except Exception:
        pass

    return {"ok": True, "project_id": project_id}


def update_project_path(
    project_id: str,
    project_path: Path | str,
) -> dict[str, Any]:
    """Set or update project_path on an already-registered project.

    Use this instead of raw SQL to backfill project_path for projects that were
    registered without a local directory (e.g. via early CLI or bulk brownfield
    import). Emits project.path_set for audit trail so the operation is
    reproducible via the event flow.

    Returns {"ok": True, "project_id": str, "project_path": str}
            or {"ok": False, "error": str}.
    """
    from core.event_store.studio_db import _connect

    resolved = str(Path(project_path).resolve())
    now = datetime.now(UTC).isoformat()

    try:
        with _connect() as conn:
            rows = conn.execute(
                "UPDATE business_projects"
                " SET project_path = ?, updated_at = ?"
                " WHERE project_id = ?",
                (resolved, now, project_id),
            ).rowcount
            conn.commit()
        if rows == 0:
            return {"ok": False, "error": f"project not found: {project_id}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        _spool_writer.write_event(
            CanonicalEventEnvelope(
                event_type="project.path_set",
                session_id=None,
                payload={"project_path": resolved},
                timestamp=now,
                severity="info",
                trace={"domain": "sdlc", "project_id": project_id},
            ).to_dict()
        )
    except Exception:
        pass

    return {"ok": True, "project_id": project_id, "project_path": resolved}
