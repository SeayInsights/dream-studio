"""SkillCollector - Collects skill usage and performance metrics from studio.db"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
from core.config.database import get_connection
from projections.core.collectors.authority_sources import skill_usage_sql


class SkillCollector:
    """Collects and aggregates skill metrics from skill_invocations authority."""

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
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            source_sql = skill_usage_sql(conn)
            if source_sql is None:
                return {
                    "total_invocations": 0,
                    "unique_skills": 0,
                    "overall_success_rate": 0.0,
                    "by_skill": {},
                    "top_skills": [],
                    "failures": [],
                    "timeline": [],
                    "invocations": [],
                    "source_status": {
                        "classification": "empty by design",
                        "reason": "skill_invocations is unavailable; skill metrics return an honest empty state.",
                        "source_tables": ["skill_invocations"],
                    },
                }

            # Total invocations
            cursor.execute(
                f"""
                SELECT COUNT(*) as total
                FROM ({source_sql}) skill_usage
                WHERE invoked_at >= ?
            """,
                (cutoff_date,),
            )
            total_invocations = cursor.fetchone()["total"]

            # By skill with success rate and performance
            cursor.execute(
                f"""
                SELECT
                    skill_name,
                    COUNT(*) as count,
                    SUM(success) as successes,
                    AVG(execution_time_s) as avg_exec_time,
                    AVG(input_tokens) as avg_input_tokens,
                    AVG(output_tokens) as avg_output_tokens
                FROM ({source_sql}) skill_usage
                WHERE invoked_at >= ?
                GROUP BY skill_name
                ORDER BY count DESC
            """,
                (cutoff_date,),
            )

            by_skill = {}
            for row in cursor.fetchall():
                skill = row["skill_name"]
                count = row["count"]
                successes = row["successes"] or 0
                success_rate = (successes / count * 100) if count > 0 else 0.0

                by_skill[skill] = {
                    "count": count,
                    "success_rate": round(success_rate, 1),
                    "avg_exec_time_s": (
                        round(row["avg_exec_time"], 2) if row["avg_exec_time"] else 0.0
                    ),
                    "avg_input_tokens": (
                        round(row["avg_input_tokens"], 0) if row["avg_input_tokens"] else 0
                    ),
                    "avg_output_tokens": (
                        round(row["avg_output_tokens"], 0) if row["avg_output_tokens"] else 0
                    ),
                }

            # Overall success rate
            cursor.execute(
                f"""
                SELECT
                    SUM(success) as successes,
                    COUNT(*) as total
                FROM ({source_sql}) skill_usage
                WHERE invoked_at >= ?
            """,
                (cutoff_date,),
            )
            result = cursor.fetchone()
            success_rate_overall = (
                (result["successes"] / result["total"] * 100) if result["total"] > 0 else 0.0
            )

            # Recent failures
            cursor.execute(
                f"""
                SELECT
                    skill_name,
                    invoked_at,
                    execution_time_s,
                    project_id
                FROM ({source_sql}) skill_usage
                WHERE invoked_at >= ?
                AND success = 0
                ORDER BY invoked_at DESC
                LIMIT 20
            """,
                (cutoff_date,),
            )
            failures = [dict(row) for row in cursor.fetchall()]

            # Top skills by usage (as list of dicts)
            top_skills = [
                {"skill_name": skill, "count": data["count"], "success_rate": data["success_rate"]}
                for skill, data in sorted(
                    by_skill.items(), key=lambda x: x[1]["count"], reverse=True
                )[:10]
            ]

            # Count unique skills
            unique_skills = len(by_skill)

            # Timeline: daily skill invocation counts
            cursor.execute(
                f"""
                SELECT
                    DATE(invoked_at) as date,
                    COUNT(*) as count
                FROM ({source_sql}) skill_usage
                WHERE invoked_at >= ?
                GROUP BY DATE(invoked_at)
                ORDER BY date ASC
            """,
                (cutoff_date,),
            )
            timeline = [{"date": row["date"], "count": row["count"]} for row in cursor.fetchall()]

            # Raw invocations for pattern detection
            cursor.execute(
                f"""
                SELECT session_id, skill_name, invoked_at
                FROM ({source_sql}) skill_usage
                WHERE invoked_at >= ?
                ORDER BY invoked_at ASC
            """,
                (cutoff_date,),
            )
            invocations = [dict(row) for row in cursor.fetchall()]

            return {
                "total_invocations": total_invocations,
                "unique_skills": unique_skills,
                "overall_success_rate": round(success_rate_overall, 1),
                "by_skill": by_skill,
                "top_skills": top_skills,
                "failures": failures,
                "timeline": timeline,
                "invocations": invocations,
                "source_status": {
                    "classification": "fresh",
                    "reason": "Skill metrics are derived from current skill_invocations authority.",
                    "source_tables": ["skill_invocations"],
                },
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
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            source_sql = skill_usage_sql(conn)
            if source_sql is None:
                return []

            cursor.execute(
                f"""
                SELECT
                    DATE(invoked_at) as date,
                    COUNT(*) as count,
                    SUM(success) as successes
                FROM ({source_sql}) skill_usage
                WHERE skill_name = ?
                AND invoked_at >= ?
                GROUP BY DATE(invoked_at)
                ORDER BY date ASC
            """,
                (skill_name, cutoff_date),
            )

            timeline = []
            for row in cursor.fetchall():
                count = row["count"]
                successes = row["successes"] or 0
                success_rate = (successes / count * 100) if count > 0 else 0.0

                timeline.append(
                    {"date": row["date"], "count": count, "success_rate": round(success_rate, 1)}
                )

            return timeline

        finally:
            conn.close()
