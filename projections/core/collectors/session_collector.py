"""SessionCollector - Collects session metrics from studio.db"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
from core.config.database import get_connection
from projections.api.routes.sqlite_schema import (
    has_columns,
    object_exists,
    source_status,
    table_columns,
)


class SessionCollector:
    """Collects and aggregates session metrics from raw_sessions table"""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize SessionCollector

        Args:
            db_path: Path to studio.db. If None, uses default ~/.dream-studio/state/studio.db
        """
        if db_path is None:
            self.db_path = str(Path.home() / ".dream-studio" / "state" / "studio.db")
        else:
            self.db_path = db_path

    def collect(self, days: int = 90) -> Dict[str, Any]:
        """
        Collect session metrics

        Args:
            days: Number of days of history to collect (default: 90)

        Returns:
            Dict containing:
                - total_sessions: int
                - by_project: Dict[project -> count]
                - timeline: List[Dict] with date and count
                - day_of_week: Dict[weekday -> count]
                - outcomes: Dict[outcome -> count]
                - avg_duration_minutes: float
        """
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Calculate cutoff date
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            if not object_exists(conn, "raw_sessions"):
                return self._empty_metrics(
                    source_status(
                        "missing because live DB schema is behind repo migrations",
                        "raw_sessions is not available; session metrics are represented as an empty state.",
                        source_tables=["raw_sessions"],
                        missing=["raw_sessions"],
                    )
                )

            columns = table_columns(conn, "raw_sessions")
            timestamp_column = (
                "started_at"
                if "started_at" in columns
                else "created_at" if "created_at" in columns else None
            )
            if timestamp_column is None:
                return self._empty_metrics(
                    source_status(
                        "broken",
                        "raw_sessions exists but has no usable timestamp column.",
                        source_tables=["raw_sessions"],
                        missing=["started_at", "created_at"],
                    )
                )

            required_columns = {"session_id", "project_id", "started_at", "ended_at", "outcome"}
            missing_required = sorted(required_columns - columns)
            if missing_required:
                return self._empty_metrics(
                    source_status(
                        "missing because live DB schema is behind repo migrations",
                        "raw_sessions exists but is missing current session authority columns.",
                        source_tables=["raw_sessions"],
                        missing=missing_required,
                    )
                )

            project_expr = "project_id"
            outcome_expr = "outcome"
            ended_available = has_columns(conn, "raw_sessions", [timestamp_column, "ended_at"])

            # Total sessions
            cursor.execute(
                f"""
                SELECT COUNT(*) as total
                FROM raw_sessions
                WHERE {timestamp_column} >= ?
            """,
                (cutoff_date,),
            )
            total_sessions = cursor.fetchone()["total"]

            # By project
            cursor.execute(
                f"""
                SELECT {project_expr} as project_id, COUNT(*) as count
                FROM raw_sessions
                WHERE {timestamp_column} >= ?
                GROUP BY project_id
                ORDER BY count DESC
            """,
                (cutoff_date,),
            )
            by_project = {row["project_id"]: row["count"] for row in cursor.fetchall()}

            # Timeline (daily)
            cursor.execute(
                f"""
                SELECT DATE({timestamp_column}) as date, COUNT(*) as count
                FROM raw_sessions
                WHERE {timestamp_column} >= ?
                GROUP BY DATE({timestamp_column})
                ORDER BY date ASC
            """,
                (cutoff_date,),
            )
            timeline = [{"date": row["date"], "count": row["count"]} for row in cursor.fetchall()]

            # Day of week (0=Monday, 6=Sunday)
            cursor.execute(
                f"""
                SELECT
                    CAST(strftime('%w', {timestamp_column}) AS INTEGER) as dow,
                    COUNT(*) as count
                FROM raw_sessions
                WHERE {timestamp_column} >= ?
                GROUP BY dow
                ORDER BY dow
            """,
                (cutoff_date,),
            )
            day_of_week_data = cursor.fetchall()

            # Convert SQLite weekday (0=Sunday) to Python weekday (0=Monday)
            weekday_names = [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ]
            day_of_week = {}
            for row in day_of_week_data:
                sqlite_dow = row["dow"]  # 0=Sunday in SQLite
                python_dow = (sqlite_dow + 6) % 7  # Convert to 0=Monday
                day_of_week[weekday_names[python_dow]] = row["count"]

            # Outcomes
            cursor.execute(
                f"""
                SELECT {outcome_expr} as outcome, COUNT(*) as count
                FROM raw_sessions
                WHERE {timestamp_column} >= ?
                GROUP BY outcome
                ORDER BY count DESC
            """,
                (cutoff_date,),
            )
            outcomes = {row["outcome"]: row["count"] for row in cursor.fetchall()}

            # Average duration
            if ended_available:
                cursor.execute(
                    f"""
                    SELECT AVG(
                        (julianday(ended_at) - julianday({timestamp_column})) * 24 * 60
                    ) as avg_duration_minutes
                    FROM raw_sessions
                    WHERE {timestamp_column} >= ?
                    AND ended_at IS NOT NULL
                    AND ended_at > {timestamp_column}
                """,
                    (cutoff_date,),
                )
                result = cursor.fetchone()
                avg_duration_minutes = (
                    round(result["avg_duration_minutes"], 2)
                    if result["avg_duration_minutes"]
                    else 0.0
                )
            else:
                avg_duration_minutes = 0.0

            completed = outcomes.get("completed", 0)
            success_rate = round(completed / total_sessions, 3) if total_sessions > 0 else 0.0

            return {
                "total_sessions": total_sessions,
                "by_project": by_project,
                "timeline": timeline,
                "day_of_week": day_of_week,
                "outcomes": outcomes,
                "avg_duration_minutes": avg_duration_minutes,
                "success_rate": success_rate,
                "source_status": source_status(
                    "fresh" if total_sessions else "empty by design",
                    "Session metrics are derived from the current raw_sessions authority table.",
                    source_tables=["raw_sessions"],
                    missing=[],
                ),
            }

        finally:
            conn.close()

    def get_recent_sessions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get most recent sessions with details

        Args:
            limit: Number of sessions to return

        Returns:
            List of session dicts with id, project, started_at, outcome
        """
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            if not object_exists(conn, "raw_sessions"):
                return []

            columns = table_columns(conn, "raw_sessions")
            timestamp_column = (
                "started_at"
                if "started_at" in columns
                else "created_at" if "created_at" in columns else None
            )
            if timestamp_column is None:
                return []

            select_fields = [
                "session_id",
                "project_id" if "project_id" in columns else "'unknown' as project_id",
                f"{timestamp_column} as started_at",
                "ended_at" if "ended_at" in columns else "NULL as ended_at",
                "outcome" if "outcome" in columns else "'unknown' as outcome",
            ]
            cursor.execute(
                f"""
                SELECT
                    {", ".join(select_fields)}
                FROM raw_sessions
                ORDER BY started_at DESC
                LIMIT ?
            """,
                (limit,),
            )

            return [dict(row) for row in cursor.fetchall()]

        finally:
            conn.close()

    def _empty_metrics(self, status: dict[str, object]) -> Dict[str, Any]:
        return {
            "total_sessions": 0,
            "by_project": {},
            "timeline": [],
            "day_of_week": {},
            "outcomes": {},
            "avg_duration_minutes": 0.0,
            "success_rate": 0.0,
            "source_status": status,
        }
