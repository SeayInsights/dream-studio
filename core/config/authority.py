"""Operator-local key/value config backed by ds_config in the authority DB.

Resolution order for numeric settings like eval.friction_threshold:
  1. Environment variable (e.g. DREAM_STUDIO_FRICTION_THRESHOLD)
  2. ds_config row in SQLite authority DB  ← this module
  3. Per-row default (e.g. eval_registry.friction_threshold column, default 3)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def get_config_value(key: str, db_path: Path) -> str | None:
    """Return the stored value for *key*, or None if unset."""
    try:
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                "SELECT value FROM ds_config WHERE key = ?", (key,)
            ).fetchone()
            return row[0] if row else None
    except Exception:
        return None


def set_config_value(key: str, value: str, db_path: Path) -> None:
    """Upsert *key* = *value* in ds_config."""
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO ds_config (key, value, updated_at)"
            " VALUES (?, ?, datetime('now'))"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value,"
            "   updated_at=datetime('now')",
            (key, value),
        )


def list_config(db_path: Path) -> list[dict[str, Any]]:
    """Return all ds_config rows as a list of {key, value, updated_at} dicts."""
    try:
        with sqlite3.connect(str(db_path)) as conn:
            rows = conn.execute(
                "SELECT key, value, updated_at FROM ds_config ORDER BY key"
            ).fetchall()
            return [{"key": r[0], "value": r[1], "updated_at": r[2]} for r in rows]
    except Exception:
        return []
