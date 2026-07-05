"""ds_config API route — exposes key/value config table for the dashboard."""

from typing import Any

from fastapi import APIRouter

from core.config.database import get_connection

router = APIRouter()


def _has_table(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


@router.get("/config")
async def get_config() -> list[dict[str, Any]]:
    """Return all rows from ds_config as a list of {key, value, updated_at}."""
    conn = get_connection()
    try:
        if not _has_table(conn, "ds_config"):
            return []
        rows = conn.execute("SELECT key, value, updated_at FROM ds_config ORDER BY key").fetchall()
        return [{"key": r["key"], "value": r["value"], "updated_at": r["updated_at"]} for r in rows]
    finally:
        conn.close()
