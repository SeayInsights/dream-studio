"""Hook execution tracking API routes for webhooks dashboard"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Query, Path

from core.config.database import get_connection
from projections.api.safety import activity_log_filter_clause
from projections.api.routes.sqlite_schema import has_columns, object_exists

router = APIRouter()


def _empty_executions(
    *,
    hook_name: Optional[str],
    status: Optional[str],
    since: Optional[str],
    limit: int,
    reason: str,
) -> Dict[str, Any]:
    return {
        "executions": [],
        "count": 0,
        "filters": {
            "hook_name": hook_name,
            "status": status,
            "since": since,
            "limit": limit,
        },
        "source_status": {
            "classification": "empty by design",
            "reason": reason,
            "derived_view": True,
            "primary_authority": False,
        },
    }


def _fallback_hook_invocations(
    conn, hook_name: Optional[str], status: Optional[str], since: Optional[str], limit: int
) -> list[dict[str, Any]]:
    if not has_columns(
        conn, "hook_invocations", ["invocation_id", "hook_id", "status", "created_at"]
    ):
        return []
    query = """
        SELECT
            invocation_id,
            project_id,
            milestone_id,
            task_id,
            process_run_id,
            event_id,
            hook_id,
            status,
            prevented_risky_action,
            purpose,
            metadata_json,
            created_at
        FROM hook_invocations
        WHERE 1=1
    """
    params: list[Any] = []
    if hook_name:
        query += " AND hook_id = ?"
        params.append(hook_name)
    if status:
        query += " AND status = ?"
        params.append(status)
    if since:
        query += " AND created_at >= ?"
        params.append(since)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    return [
        {
            "hook_exec_id": row["invocation_id"],
            "activity_id": row["event_id"],
            "hook_name": row["hook_id"],
            "hook_type": row["purpose"] or "telemetry",
            "trigger_context": row["metadata_json"],
            "started_at": row["created_at"],
            "completed_at": row["created_at"],
            "duration_ms": 0,
            "exit_code": 0 if row["status"] in ("success", "passed", "ok") else None,
            "status": row["status"],
            "output": None,
            "error_message": None,
            "cpu_time_ms": None,
            "memory_mb": None,
            "event_timestamp": row["created_at"],
            "severity": "info",
            "is_anomaly": False,
            "anomaly_score": 0,
        }
        for row in rows
    ]


@router.get("/hooks/executions")
async def list_hook_executions(
    hook_name: Optional[str] = Query(None, description="Filter by hook name"),
    status: Optional[str] = Query(
        None, description="Filter by status (success, failed, timeout, pending, running)"
    ),
    since: Optional[str] = Query(None, description="Filter by date (YYYY-MM-DD format)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
) -> Dict[str, Any]:
    """
    List recent hook executions with activity log data joined.

    Returns hook executions sorted by most recent first, with optional filters.
    """
    conn = get_connection()

    try:
        if not object_exists(conn, "hook_executions"):
            executions = _fallback_hook_invocations(conn, hook_name, status, since, limit)
            if not executions:
                return _empty_executions(
                    hook_name=hook_name,
                    status=status,
                    since=since,
                    limit=limit,
                    reason="hook_executions is absent and hook_invocations has no compatible rows.",
                )
            return {
                "executions": executions,
                "count": len(executions),
                "filters": {
                    "hook_name": hook_name,
                    "status": status,
                    "since": since,
                    "limit": limit,
                },
                "source_status": {
                    "classification": "legacy source",
                    "reason": "hook_executions is absent; using hook_invocations telemetry fallback.",
                    "source_tables": ["hook_invocations"],
                    "derived_view": True,
                    "primary_authority": False,
                },
            }

        join_activity = object_exists(conn, "activity_log")
        activity_select = (
            """
                al.event_timestamp,
                al.severity,
                al.is_anomaly,
                al.anomaly_score
        """
            if join_activity
            else """
                he.started_at as event_timestamp,
                'info' as severity,
                0 as is_anomaly,
                0 as anomaly_score
        """
        )
        activity_join = (
            "LEFT JOIN activity_log al ON he.activity_id = al.activity_id" if join_activity else ""
        )
        activity_filter = activity_log_filter_clause("al") if join_activity else ""

        # Build query with optional filters
        query = f"""
            SELECT
                he.hook_exec_id,
                he.activity_id,
                he.hook_name,
                he.hook_type,
                he.trigger_context,
                he.started_at,
                he.completed_at,
                he.duration_ms,
                he.exit_code,
                he.status,
                he.output,
                he.error_message,
                he.cpu_time_ms,
                he.memory_mb,
                {activity_select}
            FROM hook_executions he
            {activity_join}
            WHERE 1=1 {activity_filter}
        """
        params = []

        if hook_name:
            query += " AND he.hook_name = ?"
            params.append(hook_name)

        if status:
            query += " AND he.status = ?"
            params.append(status)

        if since:
            query += " AND he.started_at >= ?"
            params.append(since)

        query += " ORDER BY he.started_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()

        executions = []
        for row in rows:
            executions.append(
                {
                    "hook_exec_id": row["hook_exec_id"],
                    "activity_id": row["activity_id"],
                    "hook_name": row["hook_name"],
                    "hook_type": row["hook_type"],
                    "trigger_context": row["trigger_context"],
                    "started_at": row["started_at"],
                    "completed_at": row["completed_at"],
                    "duration_ms": row["duration_ms"],
                    "exit_code": row["exit_code"],
                    "status": row["status"],
                    "output": row["output"],
                    "error_message": row["error_message"],
                    "cpu_time_ms": row["cpu_time_ms"],
                    "memory_mb": row["memory_mb"],
                    "event_timestamp": row["event_timestamp"],
                    "severity": row["severity"],
                    "is_anomaly": bool(row["is_anomaly"]),
                    "anomaly_score": row["anomaly_score"],
                }
            )

        return {
            "executions": executions,
            "count": len(executions),
            "filters": {"hook_name": hook_name, "status": status, "since": since, "limit": limit},
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()


@router.get("/hooks/executions/{exec_id}")
async def get_hook_execution_details(
    exec_id: int = Path(..., description="Hook execution ID")
) -> Dict[str, Any]:
    """
    Get detailed information about a single hook execution, including findings.

    Returns full execution details with associated findings.
    """
    conn = get_connection()

    try:
        # Get execution details
        row = conn.execute(
            f"""
            SELECT
                he.hook_exec_id,
                he.activity_id,
                he.hook_name,
                he.hook_type,
                he.trigger_context,
                he.started_at,
                he.completed_at,
                he.duration_ms,
                he.exit_code,
                he.status,
                he.output,
                he.error_message,
                he.cpu_time_ms,
                he.memory_mb,
                al.event_timestamp,
                al.severity,
                al.is_anomaly,
                al.anomaly_score
            FROM hook_executions he
            LEFT JOIN activity_log al ON he.activity_id = al.activity_id
            WHERE he.hook_exec_id = ? {activity_log_filter_clause("al")}
        """,
            (exec_id,),
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Hook execution {exec_id} not found")

        # Get findings for this execution
        findings = conn.execute(
            """
            SELECT
                finding_id,
                finding_type,
                severity,
                message,
                context,
                recommendation,
                status,
                resolved_at,
                resolution_notes,
                created_at
            FROM hook_findings
            WHERE hook_exec_id = ?
            ORDER BY created_at DESC
        """,
            (exec_id,),
        ).fetchall()

        findings_list = []
        for f in findings:
            findings_list.append(
                {
                    "finding_id": f["finding_id"],
                    "finding_type": f["finding_type"],
                    "severity": f["severity"],
                    "message": f["message"],
                    "context": f["context"],
                    "recommendation": f["recommendation"],
                    "status": f["status"],
                    "resolved_at": f["resolved_at"],
                    "resolution_notes": f["resolution_notes"],
                    "created_at": f["created_at"],
                }
            )

        return {
            "execution": {
                "hook_exec_id": row["hook_exec_id"],
                "activity_id": row["activity_id"],
                "hook_name": row["hook_name"],
                "hook_type": row["hook_type"],
                "trigger_context": row["trigger_context"],
                "started_at": row["started_at"],
                "completed_at": row["completed_at"],
                "duration_ms": row["duration_ms"],
                "exit_code": row["exit_code"],
                "status": row["status"],
                "output": row["output"],
                "error_message": row["error_message"],
                "cpu_time_ms": row["cpu_time_ms"],
                "memory_mb": row["memory_mb"],
                "event_timestamp": row["event_timestamp"],
                "severity": row["severity"],
                "is_anomaly": bool(row["is_anomaly"]),
                "anomaly_score": row["anomaly_score"],
            },
            "findings": findings_list,
            "findings_count": len(findings_list),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()


@router.get("/hooks/findings")
async def list_hook_findings(
    severity: Optional[str] = Query(
        None, description="Filter by severity (info, warning, error, critical)"
    ),
    status: Optional[str] = Query(
        None, description="Filter by status (open, acknowledged, resolved, wont_fix)"
    ),
    since: Optional[str] = Query(None, description="Filter by date (YYYY-MM-DD format)"),
) -> Dict[str, Any]:
    """
    List hook findings with optional filters.

    Returns findings sorted by creation time (most recent first).
    """
    conn = get_connection()

    try:
        query = """
            SELECT
                hf.finding_id,
                hf.activity_id,
                hf.hook_exec_id,
                hf.finding_type,
                hf.severity,
                hf.message,
                hf.context,
                hf.recommendation,
                hf.status,
                hf.resolved_at,
                hf.resolution_notes,
                hf.created_at,
                he.hook_name,
                he.started_at as execution_started_at
            FROM hook_findings hf
            LEFT JOIN hook_executions he ON hf.hook_exec_id = he.hook_exec_id
            WHERE 1=1
        """
        params = []

        if severity:
            query += " AND hf.severity = ?"
            params.append(severity)

        if status:
            query += " AND hf.status = ?"
            params.append(status)

        if since:
            query += " AND hf.created_at >= ?"
            params.append(since)

        query += " ORDER BY hf.created_at DESC"

        rows = conn.execute(query, params).fetchall()

        findings = []
        for row in rows:
            findings.append(
                {
                    "finding_id": row["finding_id"],
                    "activity_id": row["activity_id"],
                    "hook_exec_id": row["hook_exec_id"],
                    "finding_type": row["finding_type"],
                    "severity": row["severity"],
                    "message": row["message"],
                    "context": row["context"],
                    "recommendation": row["recommendation"],
                    "status": row["status"],
                    "resolved_at": row["resolved_at"],
                    "resolution_notes": row["resolution_notes"],
                    "created_at": row["created_at"],
                    "hook_name": row["hook_name"],
                    "execution_started_at": row["execution_started_at"],
                }
            )

        return {
            "findings": findings,
            "count": len(findings),
            "filters": {"severity": severity, "status": status, "since": since},
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()


@router.get("/hooks/performance")
async def get_hook_performance() -> Dict[str, Any]:
    """
    Get hook execution performance statistics.

    Returns execution counts, durations, and failure rates by hook name.
    """
    conn = get_connection()

    try:
        if not object_exists(conn, "hook_executions"):
            invocations = _fallback_hook_invocations(conn, None, None, None, 1000)
            by_hook: dict[str, dict[str, Any]] = {}
            for item in invocations:
                hook = item["hook_name"] or "unknown"
                if hook not in by_hook:
                    by_hook[hook] = {
                        "execution_count": 0,
                        "avg_duration_ms": 0,
                        "max_duration_ms": 0,
                        "failure_count": 0,
                        "success_count": 0,
                        "success_rate": 0.0,
                    }
                by_hook[hook]["execution_count"] += 1
                failed = item["status"] in ("failed", "failure", "timeout", "error")
                by_hook[hook]["failure_count"] += 1 if failed else 0
                by_hook[hook]["success_count"] += 0 if failed else 1
            for item in by_hook.values():
                count = item["execution_count"]
                item["success_rate"] = round(item["success_count"] / count, 3) if count else 0.0
            total_executions = sum(item["execution_count"] for item in by_hook.values())
            total_failures = sum(item["failure_count"] for item in by_hook.values())
            total_successes = total_executions - total_failures
            return {
                "by_hook": by_hook,
                "summary": {
                    "total_executions": total_executions,
                    "total_successes": total_successes,
                    "total_failures": total_failures,
                    "overall_success_rate": (
                        round(total_successes / total_executions, 3) if total_executions else 0.0
                    ),
                },
                "source_status": {
                    "classification": "legacy source",
                    "reason": "hook performance is derived from hook_invocations telemetry fallback.",
                    "source_tables": ["hook_invocations"],
                    "derived_view": True,
                    "primary_authority": False,
                },
            }

        rows = conn.execute("""
            SELECT
                COALESCE(NULLIF(hook_name, ''), 'unknown') AS hook_name,
                COUNT(*) AS execution_count,
                AVG(COALESCE(duration_ms, 0)) AS avg_duration_ms,
                MAX(COALESCE(duration_ms, 0)) AS max_duration_ms,
                SUM(
                    CASE
                        WHEN status IN ('failed', 'failure', 'timeout', 'error') THEN 1
                        WHEN exit_code IS NOT NULL AND exit_code != 0 THEN 1
                        ELSE 0
                    END
                ) AS failure_count
            FROM hook_executions
            GROUP BY COALESCE(NULLIF(hook_name, ''), 'unknown')
            ORDER BY execution_count DESC, hook_name ASC
            """).fetchall()

        by_hook = {}
        total_executions = 0
        total_failures = 0

        for row in rows:
            execution_count = row["execution_count"]
            failure_count = row["failure_count"]
            success_count = execution_count - failure_count

            total_executions += execution_count
            total_failures += failure_count

            success_rate = (success_count / execution_count) if execution_count > 0 else 0.0

            by_hook[row["hook_name"]] = {
                "execution_count": execution_count,
                "avg_duration_ms": round(row["avg_duration_ms"], 2),
                "max_duration_ms": row["max_duration_ms"],
                "failure_count": failure_count,
                "success_count": success_count,
                "success_rate": round(success_rate, 3),
            }

        total_successes = total_executions - total_failures
        overall_success_rate = (total_successes / total_executions) if total_executions > 0 else 0.0

        return {
            "by_hook": by_hook,
            "summary": {
                "total_executions": total_executions,
                "total_successes": total_successes,
                "total_failures": total_failures,
                "overall_success_rate": round(overall_success_rate, 3),
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()


@router.get("/hooks/stats")
async def get_hook_stats() -> Dict[str, Any]:
    """Return dashboard-compatible hook execution summary stats.

    This is a legacy dashboard alias for the hook performance summary. Empty
    hook data is a valid dashboard state and returns zero counts.
    """

    return await get_hook_performance()


@router.get("/hooks/anomalies")
async def list_hook_anomalies() -> Dict[str, Any]:
    """
    List hooks with anomalous behavior detected.

    Returns hook executions marked as anomalies in the activity log.
    """
    conn = get_connection()

    try:
        rows = conn.execute(f"""
            SELECT
                he.hook_exec_id,
                he.activity_id,
                he.hook_name,
                he.hook_type,
                he.started_at,
                he.completed_at,
                he.duration_ms,
                he.status,
                he.error_message,
                al.event_timestamp,
                al.severity,
                al.anomaly_score,
                al.is_anomaly
            FROM hook_executions he
            JOIN activity_log al ON he.activity_id = al.activity_id
            WHERE al.activity_type = 'hook_execution'
              AND al.is_anomaly = 1
              {activity_log_filter_clause("al")}
            ORDER BY al.anomaly_score DESC, he.started_at DESC
        """).fetchall()

        anomalies = []
        for row in rows:
            anomalies.append(
                {
                    "hook_exec_id": row["hook_exec_id"],
                    "activity_id": row["activity_id"],
                    "hook_name": row["hook_name"],
                    "hook_type": row["hook_type"],
                    "started_at": row["started_at"],
                    "completed_at": row["completed_at"],
                    "duration_ms": row["duration_ms"],
                    "status": row["status"],
                    "error_message": row["error_message"],
                    "event_timestamp": row["event_timestamp"],
                    "severity": row["severity"],
                    "anomaly_score": row["anomaly_score"],
                }
            )

        return {"anomalies": anomalies, "count": len(anomalies)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()
