"""SkillCollector - Collects skill usage and performance metrics from studio.db"""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional


class SkillCollector:
    """Collects and aggregates skill metrics from raw_skill_telemetry table"""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize SkillCollector

        Args:
            db_path: Path to studio.db. If None, uses default ~/.dream-studio/state/studio.db
        """
        if db_path is None:
            self.db_path = str(Path.home() / ".dream-studio" / "state" / "studio.db")
        else:
            self.db_path = db_path

    def collect(self, days: int = 90) -> Dict[str, Any]:
        """
        Collect skill metrics

        Args:
            days: Number of days of history to collect (default: 90)

        Returns:
            Dict containing:
                - total_invocations: int
                - by_skill: Dict[skill_name -> {count, success_rate, avg_exec_time}]
                - success_rate_overall: float
                - failures: List[Dict] with recent failures
                - top_skills: List of (skill, count) tuples
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            # Total invocations
            cursor.execute("""
                SELECT COUNT(*) as total
                FROM raw_skill_telemetry
                WHERE invoked_at >= ?
            """, (cutoff_date,))
            total_invocations = cursor.fetchone()["total"]

            # By skill with success rate and performance
            cursor.execute("""
                SELECT
                    skill_name,
                    COUNT(*) as count,
                    SUM(success) as successes,
                    AVG(execution_time_s) as avg_exec_time,
                    AVG(input_tokens) as avg_input_tokens,
                    AVG(output_tokens) as avg_output_tokens
                FROM raw_skill_telemetry
                WHERE invoked_at >= ?
                GROUP BY skill_name
                ORDER BY count DESC
            """, (cutoff_date,))

            by_skill = {}
            for row in cursor.fetchall():
                skill = row["skill_name"]
                count = row["count"]
                successes = row["successes"] or 0
                success_rate = (successes / count * 100) if count > 0 else 0.0

                by_skill[skill] = {
                    "count": count,
                    "success_rate": round(success_rate, 1),
                    "avg_exec_time_s": round(row["avg_exec_time"], 2) if row["avg_exec_time"] else 0.0,
                    "avg_input_tokens": round(row["avg_input_tokens"], 0) if row["avg_input_tokens"] else 0,
                    "avg_output_tokens": round(row["avg_output_tokens"], 0) if row["avg_output_tokens"] else 0
                }

            # Overall success rate
            cursor.execute("""
                SELECT
                    SUM(success) as successes,
                    COUNT(*) as total
                FROM raw_skill_telemetry
                WHERE invoked_at >= ?
            """, (cutoff_date,))
            result = cursor.fetchone()
            success_rate_overall = (result["successes"] / result["total"] * 100) if result["total"] > 0 else 0.0

            # Recent failures
            cursor.execute("""
                SELECT
                    skill_name,
                    invoked_at,
                    execution_time_s,
                    project_id
                FROM raw_skill_telemetry
                WHERE invoked_at >= ?
                AND success = 0
                ORDER BY invoked_at DESC
                LIMIT 20
            """, (cutoff_date,))
            failures = [dict(row) for row in cursor.fetchall()]

            # Top skills by usage
            top_skills = [(skill, data["count"]) for skill, data in
                         sorted(by_skill.items(), key=lambda x: x[1]["count"], reverse=True)[:10]]

            return {
                "total_invocations": total_invocations,
                "by_skill": by_skill,
                "success_rate_overall": round(success_rate_overall, 1),
                "failures": failures,
                "top_skills": top_skills
            }

        finally:
            conn.close()

    def get_skill_timeline(self, skill_name: str, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get daily usage timeline for a specific skill

        Args:
            skill_name: Name of the skill
            days: Number of days of history

        Returns:
            List of dicts with date, count, success_rate
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            cursor.execute("""
                SELECT
                    DATE(invoked_at) as date,
                    COUNT(*) as count,
                    SUM(success) as successes
                FROM raw_skill_telemetry
                WHERE skill_name = ?
                AND invoked_at >= ?
                GROUP BY DATE(invoked_at)
                ORDER BY date ASC
            """, (skill_name, cutoff_date))

            timeline = []
            for row in cursor.fetchall():
                count = row["count"]
                successes = row["successes"] or 0
                success_rate = (successes / count * 100) if count > 0 else 0.0

                timeline.append({
                    "date": row["date"],
                    "count": count,
                    "success_rate": round(success_rate, 1)
                })

            return timeline

        finally:
            conn.close()
