"""Project Intelligence API routes for health scores, analysis runs, and real-time progress"""
import logging
import sqlite3
import uuid
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pathlib import Path
from typing import Dict, Any, List, Optional

from ..websocket.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)

router = APIRouter()

# Global connection manager instance for project intelligence subscriptions
pi_connection_manager = ConnectionManager()


def get_db_path() -> str:
    """Get database path"""
    return str(Path.home() / ".dream-studio" / "state" / "studio.db")


def get_db_connection():
    """Get database connection with row factory"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# ── HTTP Endpoints ───────────────────────────────────────────────────────────

@router.get("")
async def list_projects(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
) -> Dict[str, Any]:
    """
    List all analyzed projects with their latest health scores.

    Returns projects sorted by last_analyzed (most recent first).
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Get total count of distinct projects
        count_query = "SELECT COUNT(DISTINCT project_path) as total FROM reg_projects WHERE project_name IS NOT NULL"
        total = cursor.execute(count_query).fetchone()["total"]

        # Get projects with pagination (deduplicated by path, prioritizing entries with most sessions)
        query = """
        WITH ranked_projects AS (
            SELECT
                *,
                ROW_NUMBER() OVER (
                    PARTITION BY project_path
                    ORDER BY total_sessions DESC, last_analyzed DESC
                ) as rn
            FROM reg_projects
            WHERE project_name IS NOT NULL
        )
        SELECT
            project_id,
            project_name,
            project_path,
            stack_detected,
            health_score,
            security_score,
            maintainability_score,
            total_files,
            lines_of_code,
            first_analyzed,
            last_analyzed,
            total_sessions
        FROM ranked_projects
        WHERE rn = 1
        ORDER BY total_sessions DESC, last_analyzed DESC
        LIMIT ? OFFSET ?
        """

        rows = cursor.execute(query, (limit, offset)).fetchall()
        projects = [dict(row) for row in rows]

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "projects": projects
        }

    except Exception as e:
        logger.error(f"Error listing projects: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/projects/{project_id}/health")
async def get_project_health(project_id: str) -> Dict[str, Any]:
    """
    Get detailed health metrics for a specific project.

    Returns:
    - Current health score, security score, maintainability score
    - Violation counts by severity
    - Bug counts by severity
    - Improvement suggestions count
    - Latest analysis run info
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Get project details
        project_query = """
        SELECT
            project_id,
            project_name,
            project_path,
            stack_detected,
            stack_json,
            health_score,
            security_score,
            maintainability_score,
            total_files,
            lines_of_code,
            first_analyzed,
            last_analyzed
        FROM reg_projects
        WHERE project_id = ?
        """

        project_row = cursor.execute(project_query, (project_id,)).fetchone()

        if not project_row:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        project = dict(project_row)

        # Get violation counts by severity
        violations_query = """
        SELECT severity, COUNT(*) as count
        FROM pi_violations
        WHERE project_id = ? AND status != 'resolved'
        GROUP BY severity
        """
        violations = {row["severity"]: row["count"] for row in cursor.execute(violations_query, (project_id,))}

        # Get bug counts by severity
        bugs_query = """
        SELECT severity, COUNT(*) as count
        FROM pi_bugs
        WHERE project_id = ? AND status != 'fixed'
        GROUP BY severity
        """
        bugs = {row["severity"]: row["count"] for row in cursor.execute(bugs_query, (project_id,))}

        # Get improvement counts by priority
        improvements_query = """
        SELECT
            CASE
                WHEN priority_score >= 8 THEN 'high'
                WHEN priority_score >= 5 THEN 'medium'
                ELSE 'low'
            END as priority,
            COUNT(*) as count
        FROM pi_improvements
        WHERE project_id = ? AND status != 'implemented'
        GROUP BY priority
        """
        improvements = {row["priority"]: row["count"] for row in cursor.execute(improvements_query, (project_id,))}

        # Get latest analysis run
        run_query = """
        SELECT
            run_id,
            run_type,
            started_at,
            completed_at,
            duration_seconds,
            status,
            violations_found,
            bugs_found,
            improvements_suggested
        FROM pi_analysis_runs
        WHERE project_id = ?
        ORDER BY started_at DESC
        LIMIT 1
        """
        latest_run_row = cursor.execute(run_query, (project_id,)).fetchone()
        latest_run = dict(latest_run_row) if latest_run_row else None

        return {
            "project": project,
            "health": {
                "overall_score": project["health_score"],
                "security_score": project["security_score"],
                "maintainability_score": project["maintainability_score"]
            },
            "violations": violations,
            "bugs": bugs,
            "improvements": improvements,
            "latest_run": latest_run
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting project health: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/projects/{project_id}/history")
async def get_project_history(
    project_id: str,
    limit: int = Query(20, ge=1, le=100)
) -> Dict[str, Any]:
    """
    Get analysis run history for a project.

    Returns recent analysis runs with health score trends.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        query = """
        SELECT
            run_id,
            run_type,
            started_at,
            completed_at,
            duration_seconds,
            status,
            violations_found,
            bugs_found,
            improvements_suggested
        FROM pi_analysis_runs
        WHERE project_id = ?
        ORDER BY started_at DESC
        LIMIT ?
        """

        rows = cursor.execute(query, (project_id, limit)).fetchall()
        runs = [dict(row) for row in rows]

        return {
            "project_id": project_id,
            "runs": runs,
            "total_runs": len(runs)
        }

    except Exception as e:
        logger.error(f"Error getting project history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/analysis-runs/{run_id}")
async def get_analysis_run(run_id: str) -> Dict[str, Any]:
    """
    Get detailed information about a specific analysis run.

    Returns full run details including progress and findings.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        query = """
        SELECT
            run_id,
            project_id,
            run_type,
            started_at,
            completed_at,
            duration_seconds,
            discovery_completed,
            research_completed,
            audit_completed,
            bug_analysis_completed,
            synthesis_completed,
            status,
            violations_found,
            bugs_found,
            improvements_suggested,
            error_message
        FROM pi_analysis_runs
        WHERE run_id = ?
        """

        row = cursor.execute(query, (run_id,)).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Analysis run {run_id} not found")

        run = dict(row)

        # Calculate progress percentage
        phases = [
            run["discovery_completed"],
            run["research_completed"],
            run["audit_completed"],
            run["bug_analysis_completed"],
            run["synthesis_completed"]
        ]
        completed_phases = sum(1 for p in phases if p)
        progress = (completed_phases / len(phases)) * 100 if phases else 0

        run["progress_percent"] = progress
        run["phases_complete"] = completed_phases
        run["phases_total"] = len(phases)

        return run

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting analysis run: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ── WebSocket Endpoints ──────────────────────────────────────────────────────

@router.websocket("/ws/project-health/{project_id}")
async def websocket_project_health(websocket: WebSocket, project_id: str):
    """
    WebSocket endpoint for real-time project health updates.

    Clients subscribe to a specific project and receive updates when:
    - Analysis runs complete
    - Health score changes
    - New violations/bugs detected
    - Improvements implemented

    Message protocol:
    - Server sends: {"type": "health_update", "data": {...}}
    """
    client_id = str(uuid.uuid4())

    try:
        # Connect the client
        await pi_connection_manager.connect(client_id, websocket)

        # Subscribe to project health updates
        pi_connection_manager.subscribe(client_id, [f"project_health_{project_id}"])

        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "client_id": client_id,
            "project_id": project_id,
            "message": f"Subscribed to health updates for project {project_id}"
        })

        # Send current health data immediately
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            query = """
            SELECT health_score, security_score, maintainability_score, last_analyzed
            FROM reg_projects
            WHERE project_id = ?
            """
            row = cursor.execute(query, (project_id,)).fetchone()

            if row:
                await websocket.send_json({
                    "type": "health_update",
                    "data": dict(row)
                })
        finally:
            conn.close()

        # Keep connection alive and handle incoming messages
        while True:
            try:
                message = await websocket.receive_json()
                # Echo back for now (could add commands later)
                await websocket.send_json({
                    "type": "ack",
                    "message": message
                })
            except ValueError as e:
                logger.error(f"Invalid JSON from client {client_id}: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON format"
                })

    except WebSocketDisconnect:
        logger.info(f"Client {client_id} disconnected from project health stream")

    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {e}")

    finally:
        pi_connection_manager.disconnect(client_id)


@router.websocket("/ws/analysis-progress/{run_id}")
async def websocket_analysis_progress(websocket: WebSocket, run_id: str):
    """
    WebSocket endpoint for real-time analysis progress updates.

    Streams progress updates during an analysis run:
    - Phase completions (discovery, research, audit, bugs, synthesis)
    - Partial findings counts
    - ETA updates

    Message protocol:
    - Server sends: {"type": "progress_update", "phase": "...", "percent": ..., "data": {...}}
    """
    client_id = str(uuid.uuid4())

    try:
        # Connect the client
        await pi_connection_manager.connect(client_id, websocket)

        # Subscribe to analysis progress
        pi_connection_manager.subscribe(client_id, [f"analysis_progress_{run_id}"])

        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "client_id": client_id,
            "run_id": run_id,
            "message": f"Subscribed to progress updates for analysis run {run_id}"
        })

        # Send current progress immediately
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            query = """
            SELECT
                discovery_completed,
                research_completed,
                audit_completed,
                bug_analysis_completed,
                synthesis_completed,
                status
            FROM pi_analysis_runs
            WHERE run_id = ?
            """
            row = cursor.execute(query, (run_id,)).fetchone()

            if row:
                data = dict(row)
                phases = [
                    data["discovery_completed"],
                    data["research_completed"],
                    data["audit_completed"],
                    data["bug_analysis_completed"],
                    data["synthesis_completed"]
                ]
                progress = (sum(1 for p in phases if p) / len(phases)) * 100

                await websocket.send_json({
                    "type": "progress_update",
                    "percent": progress,
                    "data": data
                })
        finally:
            conn.close()

        # Keep connection alive
        while True:
            try:
                message = await websocket.receive_json()
                await websocket.send_json({
                    "type": "ack",
                    "message": message
                })
            except ValueError as e:
                logger.error(f"Invalid JSON from client {client_id}: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON format"
                })

    except WebSocketDisconnect:
        logger.info(f"Client {client_id} disconnected from analysis progress stream")

    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {e}")

    finally:
        pi_connection_manager.disconnect(client_id)


# ── Helper function for broadcasting updates ─────────────────────────────────

async def broadcast_health_update(project_id: str, data: Dict[str, Any]):
    """
    Broadcast health update to all subscribers of a project.

    Called by the analysis engine when a run completes.
    """
    await pi_connection_manager.send_to_subscribers(
        f"project_health_{project_id}",
        {
            "type": "health_update",
            "project_id": project_id,
            "data": data
        }
    )


async def broadcast_progress_update(run_id: str, phase: str, percent: float, data: Dict[str, Any]):
    """
    Broadcast progress update to all subscribers of an analysis run.

    Called by the analysis engine during phase completions.
    """
    await pi_connection_manager.send_to_subscribers(
        f"analysis_progress_{run_id}",
        {
            "type": "progress_update",
            "run_id": run_id,
            "phase": phase,
            "percent": percent,
            "data": data
        }
    )
