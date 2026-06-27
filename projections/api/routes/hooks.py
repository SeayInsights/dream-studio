"""Hook execution tracking API routes for webhooks dashboard"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, Path

from core.config.database import get_connection
from core.analytics.duckdb_store import connect_analytics
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
        conn, "execution_events", ["event_id", "hook_id", "outcome_status", "created_at"]
    ):
        return []
    # hook.tool_activity is emitted by the hook execution system (5000+ rows in execution_events).
    # The DuckDB hook_executions view is the primary source; this SQLite execution_events
    # fallback is used only when the DuckDB events_fact is empty (e.g. fresh install).
    query = """
        SELECT
            event_id,
            project_id,
            milestone_id,
            task_id,
            process_run_id,
            hook_id,
            tool_id,
            outcome_status,
            created_at
        FROM execution_events
        WHERE event_type = 'hook.tool_activity'
          AND hook_id IS NOT NULL
    """
    params: list[Any] = []
    if hook_name:
        query += " AND hook_id = ?"
        params.append(hook_name)
    if status:
        query += " AND outcome_status = ?"
        params.append(status)
    if since:
        query += " AND created_at >= ?"
        params.append(since)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    return [
        {
            "hook_exec_id": row["event_id"],
            "activity_id": row["event_id"],
            "hook_name": row["hook_id"],
            "hook_type": "telemetry",
            "trigger_context": None,
            "started_at": row["created_at"],
            "completed_at": row["created_at"],
            "duration_ms": 0,
            "exit_code": (
                0 if row["outcome_status"] in ("success", "passed", "ok", "completed") else None
            ),
            "status": row["outcome_status"],
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
    Reads from DuckDB aggregate_metrics.db (derived from canonical events via events_fact).
    """
    conn = connect_analytics(read_only=True)

    try:
        # Build query with optional filters — DuckDB views always exist; no object_exists needed
        query = """
            SELECT
                hook_exec_id,
                activity_id,
                hook_name,
                hook_type,
                trigger_context,
                started_at,
                completed_at,
                duration_ms,
                exit_code,
                status,
                output,
                error_message,
                cpu_time_ms,
                memory_mb,
                started_at AS event_timestamp,
                'info' AS severity,
                false AS is_anomaly,
                0 AS anomaly_score
            FROM hook_executions
            WHERE 1=1
        """
        params = []

        if hook_name:
            query += " AND hook_name = ?"
            params.append(hook_name)

        if status:
            query += " AND status = ?"
            params.append(status)

        if since:
            query += " AND started_at >= ?"
            params.append(since)

        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()

        executions = [
            {
                "hook_exec_id": r[0],
                "activity_id": r[1],
                "hook_name": r[2],
                "hook_type": r[3],
                "trigger_context": r[4],
                "started_at": r[5],
                "completed_at": r[6],
                "duration_ms": r[7],
                "exit_code": r[8],
                "status": r[9],
                "output": r[10],
                "error_message": r[11],
                "cpu_time_ms": r[12],
                "memory_mb": r[13],
                "event_timestamp": r[14],
                "severity": r[15],
                "is_anomaly": bool(r[16]),
                "anomaly_score": r[17],
            }
            for r in rows
        ]

        # DuckDB returns 0 rows when events_fact is empty — surface a fallback status
        # if no DuckDB rows found; still try execution_events in SQLite for telemetry
        if not executions:
            sql_conn = get_connection()
            try:
                fb = _fallback_hook_invocations(sql_conn, hook_name, status, since, limit)
            finally:
                sql_conn.close()
            if fb:
                return {
                    "executions": fb,
                    "count": len(fb),
                    "filters": {
                        "hook_name": hook_name,
                        "status": status,
                        "since": since,
                        "limit": limit,
                    },
                    "source_status": {
                        "classification": "unified source",
                        "reason": "DuckDB events_fact empty; using execution_events telemetry fallback.",
                        "source_tables": ["execution_events"],
                        "derived_view": True,
                        "primary_authority": False,
                    },
                }
            return _empty_executions(
                hook_name=hook_name,
                status=status,
                since=since,
                limit=limit,
                reason="No hook_executions in DuckDB events_fact and no execution_events rows.",
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
    exec_id: str = Path(..., description="Hook execution ID (event_id UUID)")
) -> Dict[str, Any]:
    """
    Get detailed information about a single hook execution.

    Reads from the DuckDB hook_executions view (derived from canonical events via
    events_fact). The view's hook_exec_id is the canonical event_id (a UUID string).

    Findings are no longer attached: hook_findings was a SQLite-only projection table
    dropped in migration 129 (WO-READMODELS-DUCKDB) — it carried no data and has no
    canonical-event source. The response keeps an empty findings list for shape stability.
    """
    conn = connect_analytics(read_only=True)

    try:
        # DuckDB view: hook_exec_id = event_id (TEXT UUID). Positional row access.
        row = conn.execute(
            """
            SELECT
                hook_exec_id,
                activity_id,
                hook_name,
                hook_type,
                trigger_context,
                started_at,
                completed_at,
                duration_ms,
                exit_code,
                status,
                output,
                error_message,
                cpu_time_ms,
                memory_mb,
                started_at AS event_timestamp
            FROM hook_executions
            WHERE hook_exec_id = ?
        """,
            [exec_id],
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Hook execution {exec_id} not found")

        return {
            "execution": {
                "hook_exec_id": row[0],
                "activity_id": row[1],
                "hook_name": row[2],
                "hook_type": row[3],
                "trigger_context": row[4],
                "started_at": row[5],
                "completed_at": row[6],
                "duration_ms": row[7],
                "exit_code": row[8],
                "status": row[9],
                "output": row[10],
                "error_message": row[11],
                "cpu_time_ms": row[12],
                "memory_mb": row[13],
                "event_timestamp": row[14],
                "severity": "info",
                "is_anomaly": False,
                "anomaly_score": 0.0,
            },
            # hook_findings dropped in migration 129; no canonical-event source exists.
            "findings": [],
            "findings_count": 0,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()


@router.get("/hooks/performance")
async def get_hook_performance() -> Dict[str, Any]:
    """
    Get hook execution performance statistics.

    Returns execution counts, durations, and failure rates by hook name.
    Reads from DuckDB aggregate_metrics.db (derived from canonical events via events_fact).
    """
    conn = connect_analytics(read_only=True)

    try:
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
            execution_count = row[1]
            failure_count = row[4]
            success_count = execution_count - failure_count

            total_executions += execution_count
            total_failures += failure_count

            success_rate = (success_count / execution_count) if execution_count > 0 else 0.0

            by_hook[row[0]] = {
                "execution_count": execution_count,
                "avg_duration_ms": round(row[2], 2) if row[2] is not None else 0,
                "max_duration_ms": row[3],
                "failure_count": failure_count,
                "success_count": success_count,
                "success_rate": round(success_rate, 3),
            }

        # DuckDB returned no rows — fall back to execution_events in SQLite
        if not by_hook:
            sql_conn = get_connection()
            try:
                invocations = _fallback_hook_invocations(sql_conn, None, None, None, 1000)
            finally:
                sql_conn.close()
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
    Anomaly detection was retired when activity_log was dropped (migration 063).
    Returns an empty result set.
    """
    return {"anomalies": [], "count": 0}


# ── Previously-invisible table surfaces (Dashboard Wiring Fix WO-A) ─────────
# These three tables had substantial data but no dashboard surface.
# These endpoints make them visible to the operator.


@router.get("/hooks/tool-activity")
async def list_tool_activity(limit: int = Query(default=50, le=200)) -> Dict[str, Any]:
    """Tool invocation telemetry — every tool Claude used.

    Reads from execution_events (unified spine) filtered by tool_id IS NOT NULL.
    """
    conn = get_connection()
    try:
        conn.row_factory = __import__("sqlite3").Row
        if not object_exists(conn, "execution_events"):
            return {"invocations": [], "count": 0, "top_tools": {}}
        rows = conn.execute(
            "SELECT tool_id, outcome_status AS status, project_id, created_at "
            "FROM execution_events WHERE tool_id IS NOT NULL "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        invocations = [dict(r) for r in rows]
        # Top tools by frequency
        top = {}
        for r in invocations:
            t = r.get("tool_id") or "unknown"
            top[t] = top.get(t, 0) + 1
        total = conn.execute(
            "SELECT COUNT(*) FROM execution_events WHERE tool_id IS NOT NULL"
        ).fetchone()[0]
        return {"invocations": invocations, "count": total, "top_tools": top}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))
    finally:
        conn.close()


@router.get("/hooks/validation-failures")
async def list_validation_failures(limit: int = Query(default=50, le=200)) -> Dict[str, Any]:
    """Event validation failures — events that failed schema/constraint validation.

    Previously invisible: 443+ rows in validation_failures with no dashboard surface.
    These are events that were rejected by the validation pipeline.
    Reads from DuckDB aggregate_metrics.db (derived from canonical events).
    """
    conn = connect_analytics(read_only=True)
    try:
        rows = conn.execute(
            "SELECT event_id, event_type, errors, attempted_at "
            "FROM validation_failures ORDER BY attempted_at DESC LIMIT ?",
            [limit],
        ).fetchall()
        failures = [
            {
                "event_id": r[0],
                "event_type": r[1],
                "errors": r[2],
                "attempted_at": r[3],
            }
            for r in rows
        ]
        by_type = {}
        for r in failures:
            t = r.get("event_type") or "unknown"
            by_type[t] = by_type.get(t, 0) + 1
        total = conn.execute("SELECT COUNT(*) FROM validation_failures").fetchone()[0]
        return {"failures": failures, "count": total, "by_event_type": by_type}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))
    finally:
        conn.close()


@router.get("/hooks/raw-events")
async def list_raw_events(limit: int = Query(default=30, le=100)) -> Dict[str, Any]:
    """Raw canonical events from the Claude Code event ingestor.

    Previously invisible: 6,500+ rows in raw_claude_code_events with no surface.
    Shows the raw event stream before it's processed into canonical_events.
    """
    conn = get_connection()
    try:
        conn.row_factory = __import__("sqlite3").Row
        if not object_exists(conn, "raw_claude_code_events"):
            return {"events": [], "count": 0, "by_event_type": {}}
        rows = conn.execute(
            "SELECT event_id, event_type, received_at, session_id, project_id "
            "FROM raw_claude_code_events ORDER BY received_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        events = [dict(r) for r in rows]
        by_type = {}
        for r in events:
            t = r.get("event_type") or "unknown"
            by_type[t] = by_type.get(t, 0) + 1
        total = conn.execute("SELECT COUNT(*) FROM raw_claude_code_events").fetchone()[0]
        return {"events": events, "count": total, "by_event_type": by_type}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))
    finally:
        conn.close()
