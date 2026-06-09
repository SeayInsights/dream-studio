"""DuckDB-first read helpers for API routes (WO-TS3 task 6).

These helpers try the DuckDB analytics store first (lower-latency read model)
and fall back to SQLite if DuckDB is unavailable or the row is missing.

Authority boundary: DuckDB is NEVER-AUTHORITY. Callers must never use these
results for gate decisions or canonical event emission.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _get_duck_conn():
    """Return a read-only DuckDB connection, or None on any error."""
    try:
        from core.analytics.duckdb_store import connect_analytics

        return connect_analytics(read_only=True)
    except Exception:
        logger.debug("duckdb_read: DuckDB unavailable (non-fatal)", exc_info=True)
        return None


def project_exists_duckdb(project_id: str) -> bool | None:
    """Check if project_id exists in DuckDB. Returns None if DuckDB unavailable."""
    conn = _get_duck_conn()
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT 1 FROM duckdb_projects WHERE project_id = ? AND status != 'deleted' LIMIT 1",
            (project_id,),
        ).fetchone()
        return row is not None
    except Exception:
        logger.debug("duckdb_read: project_exists_duckdb query failed", exc_info=True)
        return None
    finally:
        conn.close()


def get_project_row_duckdb(project_id: str) -> dict[str, Any] | None:
    """Fetch project row from DuckDB. Returns None if unavailable or not found."""
    conn = _get_duck_conn()
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT project_id, name AS project_name, description, status, project_path,"
            " total_sessions, total_tokens, last_session_at, created_at, updated_at"
            " FROM duckdb_projects WHERE project_id = ? LIMIT 1",
            (project_id,),
        ).fetchone()
        if row is None:
            return None
        cols = [
            "project_id",
            "project_name",
            "description",
            "status",
            "project_path",
            "total_sessions",
            "total_tokens",
            "last_session_at",
            "created_at",
            "updated_at",
        ]
        return dict(zip(cols, row))
    except Exception:
        logger.debug("duckdb_read: get_project_row_duckdb query failed", exc_info=True)
        return None
    finally:
        conn.close()
