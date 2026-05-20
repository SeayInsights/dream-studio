"""Project lifecycle mutations.

Skills, workflows, and hooks should import these directly instead of
shelling out to `ds project set-active` / `ds project deactivate`. Each
function returns a dict; the CLI wrapper in `interfaces/cli/ds.py` is
responsible for serialization.
"""

from __future__ import annotations

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
