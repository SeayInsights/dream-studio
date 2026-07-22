"""Small utilities, stack JSON parsing, and DB connection helpers.

WO-GF-API-ROUTES: split out of project_helpers.py. Leaf module in the
project_helpers DAG — no imports from sibling project_helpers_* modules.
"""

from __future__ import annotations

import ast
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SENSITIVE_PATH_PARTS = {
    ".git",
    ".claude",
    ".codex",
    ".env",
    ".venv",
    "secrets",
    "credentials",
    "node_modules",
}


# ── Small utilities ──────────────────────────────────────────────────────────


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _json_list(raw: Any) -> list[Any]:
    if raw in (None, ""):
        return []
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, str):
        return [raw]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return [raw]
    return parsed if isinstance(parsed, list) else [parsed]


def _optional_column_expr(
    columns: set[str],
    column: str,
    *,
    table_alias: str = "p",
    alias: str | None = None,
) -> str:
    output = alias or column
    return f"{table_alias}.{column} AS {output}" if column in columns else f"NULL AS {output}"


def _optional_count_expr(table: str, where_column: str, *, condition: str | None = None) -> str:
    base = f"(SELECT COUNT(*) FROM {table} WHERE {where_column} = p.project_id"
    if condition:
        base += f" AND {condition}"
    return base + ")"


def _project_path_exists(project_path: str | None) -> bool:
    if not project_path:
        return False
    path = Path(project_path)
    if not path.is_absolute():
        path = Path.home() / "builds" / project_path
    return path.exists()


# ── Stack JSON ───────────────────────────────────────────────────────────────


def _parse_stack_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(raw)
        except (SyntaxError, ValueError):
            return {}
    return parsed if isinstance(parsed, dict) else {}


# ── DB connection helpers ────────────────────────────────────────────────────


def get_db_path() -> str:
    """Get database path"""
    from core.config.database import get_db_path as _canonical

    return str(_canonical())


def get_db_connection():
    """Get database connection with row factory"""
    import sqlite3 as _sqlite3

    from core.config.database import get_connection

    conn = get_connection()
    conn.row_factory = _sqlite3.Row
    return conn


# ── Active project filter ────────────────────────────────────────────────────


def _active_project_where(conn) -> str:
    """Filter out quarantined/temp project records.

    reg_projects deleted in migration 084; this function is retained for callers
    that have not yet been updated. Returns a WHERE clause for business_projects.
    """
    # business_projects: status IN ('active', 'paused', 'deleted') — exclude deleted
    return "p.status != 'deleted'"
