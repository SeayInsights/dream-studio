"""Aggregate security-finding statistics endpoint.

WO-GF-API-ROUTES: split out of security.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException, Query

from core.config.database import get_connection
from projections.api.routes.sqlite_schema import has_columns, object_exists

from .security_router import router
from .security_shared import _security_finding_count_group


@router.get("/security/stats")
async def get_security_stats(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze")
) -> dict[str, Any]:
    """
    Get aggregate statistics for security findings.

    Returns:
    - findings_by_severity: {critical: N, high: N, medium: N, low: N, info: N}
    - findings_by_source: {sarif: N, cve: N, manual_review: N, hook_check: N}
    - findings_by_status: {open: N, mitigated: N, false_positive: N, ...}
    - trend_last_N_days: [{date: '2026-05-01', count: 5}, ...]
    """
    conn = get_connection()

    try:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        # Aggregate findings derived from security_events (WO-Y / AD-10 spine;
        # findings_current_status dropped migration 140, WO dff23cb0).
        findings_by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        for sev, count in _security_finding_count_group(conn, "severity", cutoff).items():
            if sev in findings_by_severity:
                findings_by_severity[sev] += count

        # Count by source (scanner_type from security_events spine)
        findings_by_source: dict[str, int] = {}
        if object_exists(conn, "security_events"):
            rows = conn.execute(
                "SELECT COALESCE(scanner_type, 'unknown') AS src, COUNT(*) AS cnt"
                " FROM security_events"
                " WHERE event_kind = 'finding.recorded' AND created_at >= ?"
                " GROUP BY src",
                (cutoff,),
            ).fetchall()
            for row in rows:
                findings_by_source[row["src"]] = int(row["cnt"])

        # Count by status
        findings_by_status = {}
        for item_status, count in _security_finding_count_group(
            conn, "current_status", cutoff
        ).items():
            findings_by_status[item_status] = findings_by_status.get(item_status, 0) + count

        # Trend over last N days — events recorded per day on the spine
        trend_data = []
        spine_ok = has_columns(conn, "security_events", ["created_at"])
        for i in range(days):
            date = (datetime.now() - timedelta(days=days - i - 1)).strftime("%Y-%m-%d")
            next_date = (datetime.now() - timedelta(days=days - i - 2)).strftime("%Y-%m-%d")
            if spine_ok:
                count = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM security_events"
                        " WHERE event_kind = 'finding.recorded'"
                        "   AND created_at >= ? AND created_at < ?",
                        (date, next_date),
                    ).fetchone()[0]
                    or 0
                )
            else:
                count = 0
            trend_data.append({"date": date, "count": count})

        # findings_current_status dropped migration 140 (WO dff23cb0) — derived
        # from security_events at read time, not a schema object.
        source_tables = [
            name for name in ("security_events", "vw_security_summary") if object_exists(conn, name)
        ]

        return {
            "findings_by_severity": findings_by_severity,
            "findings_by_source": findings_by_source,
            "findings_by_status": findings_by_status,
            "trend_last_30_days": trend_data,
            "days_analyzed": days,
            "source_status": {
                "classification": "fresh" if source_tables else "empty by design",
                "reason": (
                    "Security stats derive findings from the security_events spine at read time (WO-Y / AD-10; WO dff23cb0)."
                    if source_tables
                    else "No security spine tables present in this DB snapshot."
                ),
                "source_tables": source_tables,
                "derived_view": True,
                "primary_authority": False,
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()
