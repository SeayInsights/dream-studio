"""Read-only profile queries (migration 159)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

_COLUMNS = (
    "profile_id",
    "client_id",
    "name",
    "claude_config_dir",
    "mcp_client_name",
    "status",
    "created_at",
    "updated_at",
)


def _resolve_db(db_path: Path | None) -> Path:
    if db_path is not None:
        return Path(db_path)
    from core.config.database import _default_db_path

    return _default_db_path()


def list_profiles(
    *, include_archived: bool = False, db_path: Path | None = None
) -> list[dict[str, Any]]:
    """List profiles, most-recently-updated first. Excludes archived unless asked."""
    conn = sqlite3.connect(str(_resolve_db(db_path)))
    conn.row_factory = sqlite3.Row
    try:
        sql = f"SELECT {', '.join(_COLUMNS)} FROM business_profiles"
        if not include_archived:
            sql += " WHERE status != 'archived'"
        sql += " ORDER BY updated_at DESC"
        return [dict(r) for r in conn.execute(sql)]
    finally:
        conn.close()


def active_profile(*, db_path: Path | None = None) -> dict[str, Any] | None:
    """Return the active profile, or None if none has ever been created/activated.

    Defensive ``ORDER BY updated_at DESC LIMIT 1`` in case more than one row reads
    status='active' (the same tolerance business_projects has for its own active
    singleton -- see core.profiles.mutations.create_profile's docstring): the
    most-recently-updated one wins.
    """
    conn = sqlite3.connect(str(_resolve_db(db_path)))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM business_profiles"
            " WHERE status = 'active' ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_profile(profile_id: str, *, db_path: Path | None = None) -> dict[str, Any] | None:
    conn = sqlite3.connect(str(_resolve_db(db_path)))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM business_profiles WHERE profile_id = ?",
            (profile_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
