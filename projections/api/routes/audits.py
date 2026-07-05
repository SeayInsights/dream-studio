"""Audit tracking API routes for comprehensive dashboard"""

from datetime import datetime, timedelta
from typing import Any
from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel

from core.config.database import transaction, get_connection

router = APIRouter()


class AuditRunCreate(BaseModel):
    """Request body for creating a new audit run"""

    audit_id: str
    audit_type: str  # code_quality, security, performance, architecture, compliance
    audit_scope: str  # project, prd, task, skill, file, function
    target_id: str
    target_type: str  # project, prd, task, skill, file, function, module
    activity_id: int | None = None
    summary: str | None = None


@router.get("/audits/runs")
async def list_audit_runs(
    audit_type: str | None = Query(
        None,
        description="Filter by audit type (code_quality, security, performance, architecture, compliance)",
    ),
    target_id: str | None = Query(None, description="Filter by target ID"),
    status: str | None = Query(
        None, description="Filter by status (running, completed, failed, cancelled)"
    ),
    since: str | None = Query(None, description="Filter by date (YYYY-MM-DD format)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
) -> dict[str, Any]:
    """
    List audit runs with optional filters.

    Returns audit runs sorted by most recent first.
    """
    conn = get_connection()

    try:
        # Build query with optional filters
        query = """
            SELECT
                ar.audit_id,
                ar.activity_id,
                ar.audit_type,
                ar.audit_scope,
                ar.target_id,
                ar.target_type,
                ar.status,
                ar.findings_count,
                ar.critical_count,
                ar.high_count,
                ar.medium_count,
                ar.low_count,
                ar.report_path,
                ar.summary,
                ar.started_at,
                ar.completed_at,
                ar.duration_s,
                ar.started_at AS event_timestamp,
                'info' AS severity,
                0 AS is_anomaly,
                0.0 AS anomaly_score
            FROM audit_runs ar
            WHERE 1=1
        """
        params = []

        if audit_type:
            query += " AND ar.audit_type = ?"
            params.append(audit_type)

        if target_id:
            query += " AND ar.target_id = ?"
            params.append(target_id)

        if status:
            query += " AND ar.status = ?"
            params.append(status)

        if since:
            query += " AND ar.started_at >= ?"
            params.append(since)

        query += " ORDER BY ar.started_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()

        runs = []
        for row in rows:
            runs.append(
                {
                    "audit_id": row["audit_id"],
                    "activity_id": row["activity_id"],
                    "audit_type": row["audit_type"],
                    "audit_scope": row["audit_scope"],
                    "target_id": row["target_id"],
                    "target_type": row["target_type"],
                    "status": row["status"],
                    "findings_count": row["findings_count"],
                    "critical_count": row["critical_count"],
                    "high_count": row["high_count"],
                    "medium_count": row["medium_count"],
                    "low_count": row["low_count"],
                    "report_path": row["report_path"],
                    "summary": row["summary"],
                    "started_at": row["started_at"],
                    "completed_at": row["completed_at"],
                    "duration_s": row["duration_s"],
                    "event_timestamp": row["event_timestamp"],
                    "severity": row["severity"],
                    "is_anomaly": (
                        bool(row["is_anomaly"]) if row["is_anomaly"] is not None else None
                    ),
                    "anomaly_score": row["anomaly_score"],
                }
            )

        return {
            "runs": runs,
            "count": len(runs),
            "filters": {
                "audit_type": audit_type,
                "target_id": target_id,
                "status": status,
                "since": since,
                "limit": limit,
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()


@router.get("/audits/runs/{audit_id}")
async def get_audit_run_details(
    audit_id: str = Path(..., description="Audit run ID")
) -> dict[str, Any]:
    """
    Get detailed information about a single audit run.

    Returns full audit details with associated activity log data.
    For security audits, findings would be available via activity_id joins
    to security tables when they exist.
    """
    conn = get_connection()

    try:
        # Get audit run details
        row = conn.execute(
            """
            SELECT
                ar.audit_id,
                ar.activity_id,
                ar.audit_type,
                ar.audit_scope,
                ar.target_id,
                ar.target_type,
                ar.status,
                ar.findings_count,
                ar.critical_count,
                ar.high_count,
                ar.medium_count,
                ar.low_count,
                ar.report_path,
                ar.summary,
                ar.started_at,
                ar.completed_at,
                ar.duration_s,
                ar.started_at AS event_timestamp,
                ar.audit_type AS event_type,
                'info' AS severity,
                0 AS is_anomaly,
                0.0 AS anomaly_score,
                NULL AS error_message
            FROM audit_runs ar
            WHERE ar.audit_id = ?
        """,
            (audit_id,),
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Audit run {audit_id} not found")

        result = {
            "audit": {
                "audit_id": row["audit_id"],
                "activity_id": row["activity_id"],
                "audit_type": row["audit_type"],
                "audit_scope": row["audit_scope"],
                "target_id": row["target_id"],
                "target_type": row["target_type"],
                "status": row["status"],
                "findings_count": row["findings_count"],
                "critical_count": row["critical_count"],
                "high_count": row["high_count"],
                "medium_count": row["medium_count"],
                "low_count": row["low_count"],
                "report_path": row["report_path"],
                "summary": row["summary"],
                "started_at": row["started_at"],
                "completed_at": row["completed_at"],
                "duration_s": row["duration_s"],
                "event_timestamp": row["event_timestamp"],
                "event_type": row["event_type"],
                "severity": row["severity"],
                "is_anomaly": bool(row["is_anomaly"]) if row["is_anomaly"] is not None else None,
                "anomaly_score": row["anomaly_score"],
                "error_message": row["error_message"],
            }
        }

        # Note: When security tables (sec_sarif_findings, sec_cve_matches, etc.) exist,
        # they would be joined here via activity_id to return findings data.
        # For now, findings data is summarized in the audit_runs table itself.

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()


@router.post("/audits/runs")
async def create_audit_run(body: AuditRunCreate) -> dict[str, Any]:
    """
    Create a new audit run.

    Accepts JSON body with audit metadata and inserts into audit_runs table.
    Returns the created audit record.
    """
    # Validate enum values
    valid_audit_types = ["code_quality", "security", "performance", "architecture", "compliance"]
    valid_audit_scopes = ["project", "prd", "task", "skill", "file", "function"]
    valid_target_types = ["project", "prd", "task", "skill", "file", "function", "module"]

    if body.audit_type not in valid_audit_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid audit_type. Must be one of: {', '.join(valid_audit_types)}",
        )

    if body.audit_scope not in valid_audit_scopes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid audit_scope. Must be one of: {', '.join(valid_audit_scopes)}",
        )

    if body.target_type not in valid_target_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid target_type. Must be one of: {', '.join(valid_target_types)}",
        )

    try:
        # Insert audit run in transaction
        with transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO audit_runs (
                    audit_id,
                    activity_id,
                    audit_type,
                    audit_scope,
                    target_id,
                    target_type,
                    summary,
                    status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'running')
            """,
                (
                    body.audit_id,
                    body.activity_id,
                    body.audit_type,
                    body.audit_scope,
                    body.target_id,
                    body.target_type,
                    body.summary,
                ),
            )

        # Retrieve the created record
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT
                    audit_id,
                    activity_id,
                    audit_type,
                    audit_scope,
                    target_id,
                    target_type,
                    status,
                    findings_count,
                    critical_count,
                    high_count,
                    medium_count,
                    low_count,
                    report_path,
                    summary,
                    started_at,
                    completed_at,
                    duration_s
                FROM audit_runs
                WHERE audit_id = ?
            """,
                (body.audit_id,),
            ).fetchone()

        return {
            "audit": {
                "audit_id": row["audit_id"],
                "activity_id": row["activity_id"],
                "audit_type": row["audit_type"],
                "audit_scope": row["audit_scope"],
                "target_id": row["target_id"],
                "target_type": row["target_type"],
                "status": row["status"],
                "findings_count": row["findings_count"],
                "critical_count": row["critical_count"],
                "high_count": row["high_count"],
                "medium_count": row["medium_count"],
                "low_count": row["low_count"],
                "report_path": row["report_path"],
                "summary": row["summary"],
                "started_at": row["started_at"],
                "completed_at": row["completed_at"],
                "duration_s": row["duration_s"],
            },
            "created": True,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/audits/stats")
async def get_audit_stats(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze")
) -> dict[str, Any]:
    """
    Get aggregate statistics for audit runs.

    Returns:
    - runs_by_type: Count of runs grouped by audit type
    - runs_by_status: Count of runs grouped by status
    - findings_trend: Daily findings counts by severity (last N days)
    - avg_duration_by_type: Average duration in seconds by audit type
    """
    conn = get_connection()

    try:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        # Runs by type
        type_rows = conn.execute(
            """
            SELECT
                audit_type,
                COUNT(*) as count
            FROM audit_runs
            WHERE started_at >= ?
            GROUP BY audit_type
        """,
            (cutoff,),
        ).fetchall()

        runs_by_type = {row["audit_type"]: row["count"] for row in type_rows}

        # Ensure all types are present (even if 0)
        for audit_type in ["code_quality", "security", "performance", "architecture", "compliance"]:
            if audit_type not in runs_by_type:
                runs_by_type[audit_type] = 0

        # Runs by status
        status_rows = conn.execute(
            """
            SELECT
                status,
                COUNT(*) as count
            FROM audit_runs
            WHERE started_at >= ?
            GROUP BY status
        """,
            (cutoff,),
        ).fetchall()

        runs_by_status = {row["status"]: row["count"] for row in status_rows}

        # Ensure all statuses are present
        for status in ["running", "completed", "failed", "cancelled"]:
            if status not in runs_by_status:
                runs_by_status[status] = 0

        # Average duration by type (only completed audits)
        duration_rows = conn.execute(
            """
            SELECT
                audit_type,
                AVG(duration_s) as avg_duration_s,
                MIN(duration_s) as min_duration_s,
                MAX(duration_s) as max_duration_s,
                COUNT(*) as count
            FROM audit_runs
            WHERE started_at >= ?
                AND status = 'completed'
                AND duration_s IS NOT NULL
            GROUP BY audit_type
        """,
            (cutoff,),
        ).fetchall()

        avg_duration_by_type = {}
        for row in duration_rows:
            avg_duration_by_type[row["audit_type"]] = {
                "avg_duration_s": round(row["avg_duration_s"], 2) if row["avg_duration_s"] else 0,
                "min_duration_s": round(row["min_duration_s"], 2) if row["min_duration_s"] else 0,
                "max_duration_s": round(row["max_duration_s"], 2) if row["max_duration_s"] else 0,
                "completed_count": row["count"],
            }

        # Findings trend - daily aggregates for last N days
        # Group by date (extract date from started_at), sum severity counts
        trend_rows = conn.execute(
            """
            SELECT
                DATE(started_at) as date,
                SUM(critical_count) as critical,
                SUM(high_count) as high,
                SUM(medium_count) as medium,
                SUM(low_count) as low,
                SUM(findings_count) as total
            FROM audit_runs
            WHERE started_at >= ?
                AND status = 'completed'
            GROUP BY DATE(started_at)
            ORDER BY date ASC
        """,
            (cutoff,),
        ).fetchall()

        findings_trend = []
        for row in trend_rows:
            findings_trend.append(
                {
                    "date": row["date"],
                    "critical": row["critical"] or 0,
                    "high": row["high"] or 0,
                    "medium": row["medium"] or 0,
                    "low": row["low"] or 0,
                    "total": row["total"] or 0,
                }
            )

        # Overall summary
        summary_row = conn.execute(
            """
            SELECT
                COUNT(*) as total_runs,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_runs,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_runs,
                SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) as running_runs,
                SUM(findings_count) as total_findings,
                SUM(critical_count) as total_critical,
                SUM(high_count) as total_high,
                SUM(medium_count) as total_medium,
                SUM(low_count) as total_low
            FROM audit_runs
            WHERE started_at >= ?
        """,
            (cutoff,),
        ).fetchone()

        total_runs = summary_row["total_runs"] or 0
        completed_runs = summary_row["completed_runs"] or 0

        return {
            "runs_by_type": runs_by_type,
            "runs_by_status": runs_by_status,
            "avg_duration_by_type": avg_duration_by_type,
            "findings_trend": findings_trend,
            "summary": {
                "total_runs": total_runs,
                "completed_runs": completed_runs,
                "failed_runs": summary_row["failed_runs"] or 0,
                "running_runs": summary_row["running_runs"] or 0,
                "completion_rate": round(completed_runs / total_runs, 3) if total_runs > 0 else 0,
                "total_findings": summary_row["total_findings"] or 0,
                "total_critical": summary_row["total_critical"] or 0,
                "total_high": summary_row["total_high"] or 0,
                "total_medium": summary_row["total_medium"] or 0,
                "total_low": summary_row["total_low"] or 0,
                "days_analyzed": days,
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()


@router.get("/audits/findings/{audit_id}")
async def get_audit_findings(
    audit_id: str = Path(..., description="Audit run ID")
) -> dict[str, Any]:
    """
    Get findings for a specific audit run.

    For now, returns aggregated finding counts from the audit_runs table.
    When security tables (sec_sarif_findings, sec_cve_matches, etc.) exist,
    this endpoint will join via activity_id to return detailed findings
    grouped by severity.
    """
    conn = get_connection()

    try:
        # Get audit run
        row = conn.execute(
            """
            SELECT
                audit_id,
                audit_type,
                target_id,
                target_type,
                status,
                findings_count,
                critical_count,
                high_count,
                medium_count,
                low_count,
                summary,
                report_path,
                started_at,
                completed_at
            FROM audit_runs
            WHERE audit_id = ?
        """,
            (audit_id,),
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Audit run {audit_id} not found")

        # Currently, we only have aggregated counts in audit_runs
        # When security tables exist, we would join here:
        # SELECT * FROM sec_sarif_findings sf
        # JOIN audit_runs ar ON sf.activity_id = ar.activity_id
        # WHERE ar.audit_id = ?

        findings_by_severity = {
            "critical": {
                "count": row["critical_count"] or 0,
                "findings": [],  # Placeholder for future detailed findings
            },
            "high": {"count": row["high_count"] or 0, "findings": []},
            "medium": {"count": row["medium_count"] or 0, "findings": []},
            "low": {"count": row["low_count"] or 0, "findings": []},
        }

        return {
            "audit_id": row["audit_id"],
            "audit_type": row["audit_type"],
            "target_id": row["target_id"],
            "target_type": row["target_type"],
            "status": row["status"],
            "total_findings": row["findings_count"] or 0,
            "findings_by_severity": findings_by_severity,
            "summary": row["summary"],
            "report_path": row["report_path"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "note": "Detailed findings will be available when security tables are implemented. Join via activity_id to sec_sarif_findings, sec_cve_matches, etc.",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()
