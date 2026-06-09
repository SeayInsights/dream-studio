"""Milestone mutations: create milestone.

Skills, workflows, and hooks should import these directly instead of
shelling out to raw SQL or CLI commands. Each function returns a dict;
the CLI wrapper in `interfaces/cli/ds.py` is responsible for serialization.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect


def _require_db(source_root: Path, dream_studio_home: Path | None) -> Path:
    from interfaces.cli.ds import resolve_installed_runtime_paths

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing. Run rehearsal-install first.")
    return paths.sqlite_path


def create_milestone(
    *,
    project_id: str,
    title: str,
    description: str = "",
    order_index: int = 0,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Insert a new milestone row for a project.

    Returns::

        {"ok": True, "milestone_id": str, "project_id": str,
         "title": str, "status": "pending"}

    or on missing project::

        {"ok": False, "error": "Project not found: <id>"}
    """

    db_path = _require_db(source_root, dream_studio_home)
    milestone_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT project_id FROM business_projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if row is None:
            return {"ok": False, "error": f"Project not found: {project_id}"}
    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        _spool_writer.write_event(
            CanonicalEventEnvelope(
                event_type="milestone.created",
                session_id=None,
                payload={
                    "title": title,
                    "description": description,
                    "order_index": order_index,
                    "status": "pending",
                },
                timestamp=now,
                severity="info",
                trace={
                    "domain": "sdlc",
                    "project_id": project_id,
                    "milestone_id": milestone_id,
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
        "milestone_id": milestone_id,
        "project_id": project_id,
        "title": title,
        "status": "pending",
    }
