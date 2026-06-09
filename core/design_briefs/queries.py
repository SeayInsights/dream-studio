"""Read-only design-brief queries."""

from __future__ import annotations

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
        raise RuntimeError("Dream Studio SQLite authority is missing.")
    return paths.sqlite_path


def get_design_brief(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    """Return the most recent design brief for a project, or a sentinel dict."""

    db_path = _require_db(source_root, dream_studio_home)
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT brief_id, status, purpose, audience, tone, design_system,"
            " font_pairing, brand_tokens, raw_output, created_at, updated_at"
            " FROM business_design_briefs WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
            (project_id,),
        ).fetchone()
    if row is None:
        return {
            "ok": True,
            "project_id": project_id,
            "brief": None,
            "message": (
                f"No design brief. Create one for project {project_id} via ds-project:brief."
            ),
        }
    (
        brief_id,
        status,
        purpose,
        audience,
        tone,
        design_system,
        font_pairing,
        brand_tokens,
        _raw_output,
        created_at,
        updated_at,
    ) = row
    status_label = "LOCKED" if status == "locked" else "DRAFT — not yet locked"
    return {
        "ok": True,
        "brief_id": brief_id,
        "project_id": project_id,
        "status": f"Status: {status_label}",
        "purpose": purpose,
        "audience": audience,
        "tone": tone,
        "design_system": design_system,
        "font_pairing": font_pairing,
        "brand_tokens": brand_tokens,
        "created_at": created_at,
        "updated_at": updated_at,
    }
