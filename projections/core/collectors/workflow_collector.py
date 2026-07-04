"""WorkflowCollector - Collects workflow execution metrics from ai_canonical_events.

WO 9f47a1a0: repointed from the write-orphaned raw_workflow_runs /
raw_workflow_nodes tables (dropped migration 141 — see
core/event_store/migrations/141_drop_orphaned_workflow_raw_tables.sql) to the
workflow.completed / workflow.node.completed canonical events emitted by
control/execution/workflow/state.py via the spool. Both event types route
AI-only (config/event_type_registry.py), so ai_canonical_events is the sole
source table. Honest-empty (zeroed/blank) when the table is absent or has no
matching rows — never fabricated data.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


class WorkflowCollector:
    """Collects and aggregates workflow metrics from workflow.completed /
    workflow.node.completed canonical events (ai_canonical_events)."""

    def __init__(self, db_path: str | None = None):
        """
        Initialize WorkflowCollector

        Args:
            db_path: Path to studio.db. If None, uses default ~/.dream-studio/state/studio.db
        """
        if db_path is None:
            self.db_path = str(Path.home() / ".dream-studio" / "state" / "studio.db")
        else:
            self.db_path = db_path

    def _has_ai_canonical_events(self, conn: sqlite3.Connection) -> bool:
        return (
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ai_canonical_events'"
            ).fetchone()
            is not None
        )

    def _completed_runs(self, conn: sqlite3.Connection, cutoff_date: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT payload FROM ai_canonical_events
            WHERE event_type = 'workflow.completed'
              AND json_extract(payload, '$.started_at') >= ?
            """,
            (cutoff_date,),
        ).fetchall()
        runs = []
        for row in rows:
            try:
                runs.append(json.loads(row["payload"]))
            except (TypeError, ValueError):
                continue
        return runs

    def collect(self, days: int = 90) -> dict[str, Any]:
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

        try:
            if not self._has_ai_canonical_events(conn):
                return {
                    "total_runs": 0,
                    "by_workflow": {},
                    "by_status": {},
                    "success_rate": 0.0,
                    "avg_completion_time_minutes": 0.0,
                    "total_nodes_executed": 0,
                }

            cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            runs = self._completed_runs(conn, cutoff_date)

            total_runs = len(runs)
            by_workflow_acc: dict[str, dict[str, Any]] = {}
            by_status: dict[str, int] = {}
            completed_durations: list[float] = []
            completed_count = 0
            run_keys: list[str] = []

            for run in runs:
                workflow = run.get("workflow") or "unknown"
                status = run.get("status") or "unknown"
                run_key = run.get("run_key")
                if run_key:
                    run_keys.append(run_key)
                by_status[status] = by_status.get(status, 0) + 1

                acc = by_workflow_acc.setdefault(
                    workflow, {"count": 0, "completed": 0, "durations": []}
                )
                acc["count"] += 1

                duration_minutes = _duration_minutes(run)
                if status == "completed":
                    acc["completed"] += 1
                    completed_count += 1
                    if duration_minutes is not None:
                        completed_durations.append(duration_minutes)
                if duration_minutes is not None:
                    acc["durations"].append(duration_minutes)

            by_workflow: dict[str, Any] = {}
            for workflow, acc in by_workflow_acc.items():
                count = acc["count"]
                success_rate = (acc["completed"] / count * 100) if count > 0 else 0.0
                avg_duration = (
                    round(sum(acc["durations"]) / len(acc["durations"]), 2)
                    if acc["durations"]
                    else 0.0
                )
                by_workflow[workflow] = {
                    "count": count,
                    "success_rate": round(success_rate, 1),
                    "avg_duration_minutes": avg_duration,
                }

            success_rate = (completed_count / total_runs * 100) if total_runs > 0 else 0.0
            avg_completion_time = (
                round(sum(completed_durations) / len(completed_durations), 2)
                if completed_durations
                else 0.0
            )

            total_nodes_executed = 0
            if run_keys:
                placeholders = ",".join("?" for _ in run_keys)
                total_nodes_executed = conn.execute(
                    f"""
                    SELECT COUNT(*) FROM ai_canonical_events
                    WHERE event_type = 'workflow.node.completed'
                      AND json_extract(payload, '$.run_key') IN ({placeholders})
                    """,
                    run_keys,
                ).fetchone()[0]

            return {
                "total_runs": total_runs,
                "by_workflow": by_workflow,
                "by_status": by_status,
                "success_rate": round(success_rate, 1),
                "avg_completion_time_minutes": avg_completion_time,
                "total_nodes_executed": total_nodes_executed,
            }

        finally:
            conn.close()

    def get_timeline(self, days: int = 30) -> list[dict[str, Any]]:
        """
        Get daily workflow execution timeline

        Args:
            days: Number of days of history

        Returns:
            List of dicts with date, runs, completions
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        try:
            if not self._has_ai_canonical_events(conn):
                return []

            cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            runs = self._completed_runs(conn, cutoff_date)

            by_date: dict[str, dict[str, int]] = {}
            for run in runs:
                started_at = run.get("started_at") or ""
                date = started_at[:10]
                if not date:
                    continue
                acc = by_date.setdefault(date, {"runs": 0, "completions": 0})
                acc["runs"] += 1
                if run.get("status") == "completed":
                    acc["completions"] += 1

            return [
                {"date": date, "runs": acc["runs"], "completions": acc["completions"]}
                for date, acc in sorted(by_date.items())
            ]

        finally:
            conn.close()

    def get_node_performance(self, workflow_name: str | None = None) -> list[dict[str, Any]]:
        """
        Analyze node execution performance

        Args:
            workflow_name: Optional workflow filter

        Returns:
            List of dicts with node_id, avg_duration, failure_rate
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        try:
            if not self._has_ai_canonical_events(conn):
                return []

            rows = conn.execute(
                "SELECT payload FROM ai_canonical_events"
                " WHERE event_type = 'workflow.node.completed'"
            ).fetchall()
            nodes = []
            for row in rows:
                try:
                    nodes.append(json.loads(row["payload"]))
                except (TypeError, ValueError):
                    continue
            if workflow_name:
                nodes = [n for n in nodes if n.get("workflow") == workflow_name]

            acc: dict[str, dict[str, Any]] = {}
            for node in nodes:
                node_id = node.get("node_id") or "unknown"
                entry = acc.setdefault(node_id, {"executions": 0, "durations": [], "failures": 0})
                entry["executions"] += 1
                duration_ms = node.get("duration_ms")
                if duration_ms is not None:
                    entry["durations"].append(duration_ms / 1000.0)
                if node.get("status") == "failed":
                    entry["failures"] += 1

            result = []
            for node_id, entry in acc.items():
                executions = entry["executions"]
                failures = entry["failures"]
                failure_rate = (failures / executions * 100) if executions > 0 else 0.0
                avg_duration_s = (
                    round(sum(entry["durations"]) / len(entry["durations"]), 2)
                    if entry["durations"]
                    else 0.0
                )
                result.append(
                    {
                        "node_id": node_id,
                        "executions": executions,
                        "avg_duration_s": avg_duration_s,
                        "failure_rate": round(failure_rate, 1),
                    }
                )
            result.sort(key=lambda r: r["executions"], reverse=True)
            return result

        finally:
            conn.close()


def _duration_minutes(run: dict[str, Any]) -> float | None:
    """Duration in minutes, preferring the payload's duration_ms, falling back
    to a started_at/finished_at diff for older or hand-built payloads."""
    duration_ms = run.get("duration_ms")
    if duration_ms is not None:
        try:
            return float(duration_ms) / 1000.0 / 60.0
        except (TypeError, ValueError):
            pass
    started = run.get("started_at")
    finished = run.get("finished_at")
    if not started or not finished:
        return None
    try:
        start = datetime.fromisoformat(started)
        end = datetime.fromisoformat(finished)
        return (end - start).total_seconds() / 60.0
    except (ValueError, TypeError):
        return None
