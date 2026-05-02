"""SessionCollector - Collects session metrics from studio.db"""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional


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
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Calculate cutoff date
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            # Total sessions
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM raw_sessions
                WHERE started_at >= ?
            """, (cutoff_date,))
            total_sessions = cursor.fetchone()["total"]

            # By project
            cursor.execute("""
                SELECT project_id, COUNT(*) as count
                FROM raw_sessions
                WHERE started_at >= ?
                GROUP BY project_id
                ORDER BY count DESC
            """, (cutoff_date,))
            by_project = {row["project_id"]: row["count"] for row in cursor.fetchall()}

            # Timeline (daily)
            cursor.execute("""
                SELECT DATE(started_at) as date, COUNT(*) as count
                FROM raw_sessions
                WHERE started_at >= ?
                GROUP BY DATE(started_at)
                ORDER BY date ASC
            """, (cutoff_date,))
            timeline = [{"date": row["date"], "count": row["count"]} for row in cursor.fetchall()]

            # Day of week (0=Monday, 6=Sunday)
            cursor.execute("""
                SELECT
                    CAST(strftime('%w', started_at) AS INTEGER) as dow,
                    COUNT(*) as count
                FROM raw_sessions
                WHERE started_at >= ?
                GROUP BY dow
                ORDER BY dow
            """, (cutoff_date,))
            day_of_week_data = cursor.fetchall()

            # Convert SQLite weekday (0=Sunday) to Python weekday (0=Monday)
            weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            day_of_week = {}
            for row in day_of_week_data:
                sqlite_dow = row["dow"]  # 0=Sunday in SQLite
                python_dow = (sqlite_dow + 6) % 7  # Convert to 0=Monday
                day_of_week[weekday_names[python_dow]] = row["count"]

            # Outcomes
            cursor.execute("""
                SELECT outcome, COUNT(*) as count
                FROM raw_sessions
                WHERE started_at >= ? AND outcome IS NOT NULL
                GROUP BY outcome
                ORDER BY count DESC
            """, (cutoff_date,))
            outcomes = {row["outcome"]: row["count"] for row in cursor.fetchall()}

            # Average duration
            cursor.execute("""
                SELECT AVG(
                    (julianday(ended_at) - julianday(started_at)) * 24 * 60
                ) as avg_duration_minutes
                FROM raw_sessions
                WHERE started_at >= ?
                AND ended_at IS NOT NULL
                AND ended_at > started_at
            """, (cutoff_date,))
            result = cursor.fetchone()
            avg_duration_minutes = round(result["avg_duration_minutes"], 2) if result["avg_duration_minutes"] else 0.0

            completed = outcomes.get("completed", 0)
            success_rate = round(completed / total_sessions, 3) if total_sessions > 0 else 0.0

            return {
                "total_sessions": total_sessions,
                "by_project": by_project,
                "timeline": timeline,
                "day_of_week": day_of_week,
                "outcomes": outcomes,
                "avg_duration_minutes": avg_duration_minutes,
                "success_rate": success_rate
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
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT
                    session_id,
                    project_id,
                    started_at,
                    ended_at,
                    outcome
                FROM raw_sessions
                ORDER BY started_at DESC
                LIMIT ?
            """, (limit,))

            return [dict(row) for row in cursor.fetchall()]

        finally:
            conn.close()
