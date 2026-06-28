"""Memory taint utilities for LLM Guard Phase 2.

Standalone module (no control.research imports) so tests can import it
without requiring the full dream-studio runtime dependency chain.
"""

from __future__ import annotations

import os
from pathlib import Path


def _studio_db_path() -> Path:
    """Resolve studio.db path from env or default location."""
    env_path = os.environ.get("DREAM_STUDIO_DB_PATH")
    if env_path:
        return Path(env_path)
    return Path.home() / ".dream-studio" / "state" / "studio.db"


def get_tainted_paths(db_path: Path | None = None) -> set[str]:
    """Return set of memory entry source paths where tainted=1.

    Returns empty set if studio.db doesn't exist, lacks taint columns
    (pre-migration 091), or any other error (graceful degradation).
    """
    try:
        path = db_path or _studio_db_path()
        if not path.exists():
            return set()
        import sqlite3

        conn = sqlite3.connect(str(path))
        try:
            rows = conn.execute("SELECT source FROM memory_entries WHERE tainted = 1").fetchall()
            return {r[0] for r in rows}
        except Exception:
            return set()
        finally:
            conn.close()
    except Exception:
        return set()


def emit_memory_skip_event(
    skipped_path: str,
    project_id: str | None = None,
    db_path: Path | None = None,
) -> None:
    """No-op: guard_events dropped in migration 133 (test-only writer — no production caller).

    Function retained to avoid import errors in any external callers; body is a no-op.
    """
    # guard_events table dropped in migration 133. The table had no production writer
    # (emit_memory_skip_event was only called from tests/unit/test_guard_phase2.py;
    # runtime/hooks/meta/on-memory-retrieve.py never imported this function).
    pass


def taint_project_memory(
    project_id: str,
    taint_reason: str,
    db_path: Path | None = None,
) -> int:
    """Mark memory_entries sourced from project_id as tainted=1.

    Returns number of rows updated.
    """
    import datetime

    try:
        path = db_path or _studio_db_path()
        if not path.exists():
            return 0
        import sqlite3

        conn = sqlite3.connect(str(path))
        try:
            now = datetime.datetime.now(datetime.UTC).isoformat()
            cur = conn.execute(
                """UPDATE memory_entries
                   SET tainted = 1, taint_reason = ?, taint_timestamp = ?
                   WHERE source_repo_id = ? AND tainted = 0""",
                (taint_reason, now, project_id),
            )
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()
    except Exception:
        return 0
