"""Authority-backed singleton runtime state (WO-FILESDB-P2; consolidated WO-FILESDB-REVET).

Stores the singleton ``active_skill`` / ``active_task`` / ``platform`` runtime state
that used to live in loose ``~/.dream-studio/state/*.json`` files. These are keyed
JSON singletons — structurally identical to the pre-existing ``ds_config`` table
``(key, value, updated_at)`` — so they are stored there under a ``runtime.`` key
namespace rather than in a dedicated ``raw_runtime_state`` table (dropped in
migration 150 as a ds_config duplicate). Callers pass a bare key
(``active_skill``); this module namespaces it. Degrades to None/False when
``ds_config`` is absent so callers fall back to the legacy JSON files.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

_TABLE = "ds_config"
_KEY_PREFIX = "runtime."


def _k(key: str) -> str:
    """Namespace a bare runtime-state key into the ds_config key space."""
    return f"{_KEY_PREFIX}{key}"


def _resolve_db(db_path: Path | None) -> Path:
    if db_path is not None:
        return db_path
    # Use the canonical resolver (honors DREAM_STUDIO_DB_PATH) so runtime state
    # lives in the SAME authority DB the callers (active_task SDLC-chain query,
    # etc.) use, not a divergent state_dir()/studio.db under test overrides.
    from core.config.database import _default_db_path

    return _default_db_path()


def db_write_runtime_state(key: str, value: dict, *, db_path: Path | None = None) -> bool:
    """Upsert one runtime-state row (``value`` stored as JSON).

    Returns False (no-op) when the table is absent so the caller falls back to the
    legacy JSON file.
    """
    now = datetime.now(UTC).isoformat()
    try:
        conn = sqlite3.connect(str(_resolve_db(db_path)))
    except sqlite3.Error:
        return False
    try:
        conn.execute(
            f"INSERT INTO {_TABLE} (key, value, updated_at) VALUES (?, ?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value,"
            " updated_at = excluded.updated_at",
            (_k(key), json.dumps(value), now),
        )
        conn.commit()
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()


def db_read_runtime_state(key: str, *, db_path: Path | None = None) -> dict | None:
    """Return the JSON value dict for a runtime-state key, or None if absent
    (table missing, no row, or unparseable)."""
    try:
        conn = sqlite3.connect(str(_resolve_db(db_path)))
    except sqlite3.Error:
        return None
    try:
        row = conn.execute(f"SELECT value FROM {_TABLE} WHERE key = ?", (_k(key),)).fetchone()
        if not row:
            return None
        try:
            data = json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return None
        return data if isinstance(data, dict) else None
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()


def db_clear_runtime_state(key: str, *, db_path: Path | None = None) -> bool:
    """Delete a runtime-state row. Returns True if the row existed and was
    removed, False otherwise (table absent, no row, or DB unavailable)."""
    try:
        conn = sqlite3.connect(str(_resolve_db(db_path)))
    except sqlite3.Error:
        return False
    try:
        cur = conn.execute(f"DELETE FROM {_TABLE} WHERE key = ?", (_k(key),))
        conn.commit()
        return cur.rowcount > 0
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()
