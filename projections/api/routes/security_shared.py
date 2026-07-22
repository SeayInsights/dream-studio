"""Cross-cutting helpers used by 3+ security route groups.

WO-GF-API-ROUTES: split out of security.py. `_count_group` and `_count_since`
are dead (no callers) — relocated verbatim, not re-exported by the facade.
"""

from __future__ import annotations

from typing import Any

from core.findings.current_status import FINDINGS_CURRENT_STATUS_SQL, security_spine_present
from projections.api.routes.sqlite_schema import has_columns


def _security_empty(filters: dict[str, Any]) -> dict[str, Any]:
    return {
        "findings": [],
        "count": 0,
        "filters": filters,
        "source_status": {
            "classification": "empty by design",
            "reason": "No compatible security finding source tables are available.",
            "derived_view": True,
            "primary_authority": False,
        },
    }


def _security_fallback_findings(
    conn,
    *,
    severity: str | None,
    status: str | None,
    since: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Return findings derived from security_events (spine, WO-Y / AD-10).

    findings_current_status (the old materialized read-model) was dropped in
    migration 140 (WO dff23cb0); current status is now derived from
    security_events at read time (core/findings/current_status.py). Falls
    back to empty list if the spine tables are not yet present.
    """
    findings: list[dict[str, Any]] = []

    if not security_spine_present(conn):
        # Pre-migration install: spine not yet present; return empty (not an error).
        return findings

    query = (
        "SELECT fcs.finding_id, fcs.project_id, fcs.severity,"
        "       fcs.file_path, fcs.line_number,"
        "       COALESCE(se.title, '') AS message,"
        "       fcs.current_status AS status, fcs.scanner_type AS tool,"
        "       fcs.created_at"
        f" FROM ({FINDINGS_CURRENT_STATUS_SQL}) fcs"
        " LEFT JOIN security_events se ON se.event_id = fcs.finding_id"
        " WHERE 1=1"
    )
    params: list[Any] = []
    if severity:
        query += " AND fcs.severity = ?"
        params.append(severity)
    if status:
        query += " AND fcs.current_status = ?"
        params.append(status)
    if since:
        query += " AND fcs.created_at >= ?"
        params.append(since)
    query += " ORDER BY fcs.created_at DESC LIMIT ?"
    params.append(limit)

    try:
        for row in conn.execute(query, params).fetchall():
            findings.append(
                {
                    "type": "spine",
                    "id": row["finding_id"],
                    "project_id": row["project_id"],
                    "tool": row["tool"],
                    "severity": row["severity"],
                    "file_path": row["file_path"],
                    "line_number": row["line_number"],
                    "message": row["message"],
                    "status": row["status"],
                    "created_at": row["created_at"],
                }
            )
    except Exception:
        pass

    return findings


def _count_group(conn, table: str, column: str, cutoff: str) -> dict[str, int]:
    if not has_columns(conn, table, [column, "created_at"]):
        return {}
    rows = conn.execute(
        f"SELECT {column} as key, COUNT(*) as count FROM {table} WHERE created_at >= ? GROUP BY {column}",
        (cutoff,),
    ).fetchall()
    return {str(row["key"]): int(row["count"]) for row in rows if row["key"] is not None}


def _security_finding_count_group(conn, column: str, cutoff: str) -> dict[str, int]:
    """Like _count_group, but over the security_events-derived findings view
    (findings_current_status dropped migration 140, WO dff23cb0 — see
    core/findings/current_status.py) instead of a real table name."""
    if not security_spine_present(conn):
        return {}
    rows = conn.execute(
        f"SELECT {column} as key, COUNT(*) as count"
        f" FROM ({FINDINGS_CURRENT_STATUS_SQL})"
        f" WHERE created_at >= ? GROUP BY {column}",
        (cutoff,),
    ).fetchall()
    return {str(row["key"]): int(row["count"]) for row in rows if row["key"] is not None}


def _count_since(conn, table: str, cutoff: str) -> int:
    if not has_columns(conn, table, ["created_at"]):
        return 0
    return int(
        conn.execute(
            f"SELECT COUNT(*) as count FROM {table} WHERE created_at >= ?", (cutoff,)
        ).fetchone()["count"]
        or 0
    )
