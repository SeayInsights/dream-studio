"""Design-brief mutations: field updates and design-system selection."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect

VALID_DESIGN_SYSTEMS: frozenset[str] = frozenset(
    [
        "tech-minimal",
        "editorial-modern",
        "brutalist-bold",
        "playful-rounded",
        "executive-clean",
    ]
)

BRIEF_UPDATABLE_FIELDS: frozenset[str] = frozenset(
    [
        "purpose",
        "audience",
        "tone",
        "design_system",
        "font_pairing",
        "brand_tokens",
        "raw_output",
    ]
)


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


def update_design_brief_field(
    *,
    brief_id: str,
    field: str,
    value: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    if field not in BRIEF_UPDATABLE_FIELDS:
        return {
            "ok": False,
            "error": (f"Unknown field: {field}. Valid fields: {sorted(BRIEF_UPDATABLE_FIELDS)}"),
        }
    db_path = _require_db(source_root, dream_studio_home)
    now = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT status FROM ds_design_briefs WHERE brief_id = ?",
            (brief_id,),
        ).fetchone()
        if row is None:
            return {"ok": False, "error": f"Brief not found: {brief_id}"}
        if row[0] == "locked":
            return {"ok": False, "error": "Brief is locked and cannot be updated"}
        conn.execute(
            f"UPDATE ds_design_briefs SET {field} = ?, updated_at = ? WHERE brief_id = ?",
            (value, now, brief_id),
        )
        conn.commit()
    return {"ok": True, "brief_id": brief_id, "field": field, "value": value}


def set_design_system(
    *,
    brief_id: str,
    system_name: str,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    if system_name not in VALID_DESIGN_SYSTEMS:
        return {
            "ok": False,
            "error": (
                f"Invalid design system: {system_name}. "
                f"Valid values: {sorted(VALID_DESIGN_SYSTEMS)}"
            ),
        }
    db_path = _require_db(source_root, dream_studio_home)
    now = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT status FROM ds_design_briefs WHERE brief_id = ?",
            (brief_id,),
        ).fetchone()
        if row is None:
            return {"ok": False, "error": f"Brief not found: {brief_id}"}
        if row[0] == "locked":
            return {"ok": False, "error": "Brief is locked and cannot be updated"}
        conn.execute(
            "UPDATE ds_design_briefs SET design_system = ?, updated_at = ? WHERE brief_id = ?",
            (system_name, now, brief_id),
        )
        conn.commit()
    return {"ok": True, "brief_id": brief_id, "design_system": system_name}
