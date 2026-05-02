"""WorkflowCollector - Collects workflow execution metrics from studio.db"""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional


class WorkflowCollector:
    """Collects and aggregates workflow metrics from raw_workflow_runs and raw_workflow_nodes tables"""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize WorkflowCollector

        Args:
            db_path: Path to studio.db. If None, uses default ~/.dream-studio/state/studio.db
        """
        if db_path is None:
            self.db_path = str(Path.home() / ".dream-studio" / "state" / "studio.db")
        else:
            self.db_path = db_path

    def collect(self, days: int = 90) -> Dict[str, Any]:
        """
        Collect workflow metrics

        Args:
            days: Number of days of history to collect (default: 90)

        Returns:
            Dict containing:
                - total_runs: int
                - by_workflow: Dict[workflow -> {count, success_rate, avg_duration}]
                - by_status: Dict[status -> count]
                - success_rate: float
                - avg_completion_time: float (minutes)
                - total_nodes_executed: int
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            # Total runs
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM raw_workflow_runs
                WHERE started_at >= ?
            """, (cutoff_date,))
            total_runs = cursor.fetchone()["total"]

            # By workflow with success rate and duration
            cursor.execute("""
                SELECT
                    workflow,
                    COUNT(*) as count,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                    AVG(
                        CASE
                            WHEN finished_at IS NOT NULL AND started_at IS NOT NULL
                            THEN (julianday(finished_at) - julianday(started_at)) * 24 * 60
                            ELSE NULL
                        END
                    ) as avg_duration_minutes
                FROM raw_workflow_runs
                WHERE started_at >= ?
                GROUP BY workflow
                ORDER BY count DESC
            """, (cutoff_date,))

            by_workflow = {}
            for row in cursor.fetchall():
                workflow = row["workflow"]
                count = row["count"]
                completed = row["completed"] or 0
                success_rate = (completed / count * 100) if count > 0 else 0.0

                by_workflow[workflow] = {
                    "count": count,
                    "success_rate": round(success_rate, 1),
                    "avg_duration_minutes": round(row["avg_duration_minutes"], 2) if row["avg_duration_minutes"] else 0.0
                }

            # By status
            cursor.execute("""
                SELECT status, COUNT(*) as count
                FROM raw_workflow_runs
                WHERE started_at >= ?
                GROUP BY status
                ORDER BY count DESC
            """, (cutoff_date,))
            by_status = {row["status"]: row["count"] for row in cursor.fetchall()}

            # Overall success rate
            cursor.execute("""
                SELECT
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                    COUNT(*) as total
                FROM raw_workflow_runs
                WHERE started_at >= ?
            """, (cutoff_date,))
            result = cursor.fetchone()
            success_rate = (result["completed"] / result["total"] * 100) if result["total"] > 0 else 0.0

            # Average completion time
            cursor.execute("""
                SELECT
                    AVG(
                        (julianday(finished_at) - julianday(started_at)) * 24 * 60
                    ) as avg_completion_minutes
                FROM raw_workflow_runs
                WHERE started_at >= ?
                AND finished_at IS NOT NULL
                AND status = 'completed'
            """, (cutoff_date,))
            result = cursor.fetchone()
            avg_completion_time = round(result["avg_completion_minutes"], 2) if result["avg_completion_minutes"] else 0.0

            # Total nodes executed
            cursor.execute("""
                SELECT COUNT(*) as total_nodes
                FROM raw_workflow_nodes n
                JOIN raw_workflow_runs r ON n.run_key = r.run_key
                WHERE r.started_at >= ?
            """, (cutoff_date,))
            total_nodes = cursor.fetchone()["total_nodes"]

            return {
                "total_runs": total_runs,
                "by_workflow": by_workflow,
                "by_status": by_status,
                "success_rate": round(success_rate, 1),
                "avg_completion_time_minutes": avg_completion_time,
                "total_nodes_executed": total_nodes
            }

        finally:
            conn.close()

    def get_timeline(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get daily workflow execution timeline

        Args:
            days: Number of days of history

        Returns:
            List of dicts with date, runs, completions
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            cursor.execute("""
                SELECT
                    DATE(started_at) as date,
                    COUNT(*) as runs,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completions
                FROM raw_workflow_runs
                WHERE started_at >= ?
                GROUP BY DATE(started_at)
                ORDER BY date ASC
            """, (cutoff_date,))

            return [dict(row) for row in cursor.fetchall()]

        finally:
            conn.close()

    def get_node_performance(self, workflow_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Analyze node execution performance

        Args:
            workflow_name: Optional workflow filter

        Returns:
            List of dicts with node_id, avg_duration, failure_rate
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            if workflow_name:
                cursor.execute("""
                    SELECT
                        n.node_id,
                        COUNT(*) as executions,
                        AVG(n.duration_s) as avg_duration_s,
                        SUM(CASE WHEN n.status = 'failed' THEN 1 ELSE 0 END) as failures
                    FROM raw_workflow_nodes n
                    JOIN raw_workflow_runs r ON n.run_key = r.run_key
                    WHERE r.workflow = ?
                    GROUP BY n.node_id
                    ORDER BY executions DESC
                """, (workflow_name,))
            else:
                cursor.execute("""
                    SELECT
                        node_id,
                        COUNT(*) as executions,
                        AVG(duration_s) as avg_duration_s,
                        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failures
                    FROM raw_workflow_nodes
                    GROUP BY node_id
                    ORDER BY executions DESC
                """)

            result = []
            for row in cursor.fetchall():
                executions = row["executions"]
                failures = row["failures"] or 0
                failure_rate = (failures / executions * 100) if executions > 0 else 0.0

                result.append({
                    "node_id": row["node_id"],
                    "executions": executions,
                    "avg_duration_s": round(row["avg_duration_s"], 2) if row["avg_duration_s"] else 0.0,
                    "failure_rate": round(failure_rate, 1)
                })

            return result

        finally:
            conn.close()
