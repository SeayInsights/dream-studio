"""Authority-backed per-session token accumulator (WO-FILESDB-P2).

Replaces the loose ``~/.dream-studio/state/session-tokens-<sid>.json`` files that
token_capture wrote and the Claude Code emitter read. Degrades to None/False when
``raw_session_token_accumulators`` is absent (migration 145 stays unreleased on
the live authority DB until ``ds migrate activate``) so callers fall back to the
legacy files during the transition.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from core.config import paths

_TABLE = "raw_session_token_accumulators"


def _resolve_db(db_path: Path | None) -> Path:
    return db_path or (paths.state_dir() / "studio.db")


def db_update_accumulator(
    session_id: str, token_payload: dict, *, db_path: Path | None = None
) -> bool:
    """Add token counts (and set model — last real value wins) for a session.

    Returns False (no-op) when the table is absent so the caller falls back to
    the legacy JSON file.
    """
    now = datetime.now(UTC).isoformat()
    try:
        conn = sqlite3.connect(str(_resolve_db(db_path)))
    except sqlite3.Error:
        return False
    try:
        conn.execute(
            f"INSERT INTO {_TABLE} (session_id, input_tokens, output_tokens,"
            " cache_creation_input_tokens, cache_read_input_tokens, model, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(session_id) DO UPDATE SET"
            " input_tokens = input_tokens + excluded.input_tokens,"
            " output_tokens = output_tokens + excluded.output_tokens,"
            " cache_creation_input_tokens = cache_creation_input_tokens"
            " + excluded.cache_creation_input_tokens,"
            " cache_read_input_tokens = cache_read_input_tokens"
            " + excluded.cache_read_input_tokens,"
            " model = COALESCE(excluded.model, model),"
            " updated_at = excluded.updated_at",
            (
                session_id,
                int(token_payload.get("input_tokens") or 0),
                int(token_payload.get("output_tokens") or 0),
                int(token_payload.get("cache_creation_input_tokens") or 0),
                int(token_payload.get("cache_read_input_tokens") or 0),
                token_payload.get("model"),
                now,
            ),
        )
        conn.commit()
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()


def db_read_accumulator(session_id: str, *, db_path: Path | None = None) -> dict | None:
    """Return the accumulated token totals for a session, or None if absent."""
    try:
        conn = sqlite3.connect(str(_resolve_db(db_path)))
    except sqlite3.Error:
        return None
    try:
        row = conn.execute(
            f"SELECT input_tokens, output_tokens, cache_creation_input_tokens,"
            f" cache_read_input_tokens, model FROM {_TABLE} WHERE session_id=?",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        result: dict = {
            "input_tokens": row[0],
            "output_tokens": row[1],
            "cache_creation_input_tokens": row[2],
            "cache_read_input_tokens": row[3],
        }
        if row[4]:
            result["model"] = row[4]
        return result
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()
