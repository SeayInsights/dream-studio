"""ModelCollector - Collects model usage and performance metrics from studio.db"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
from projections.core.collectors.authority_sources import skill_usage_sql, token_usage_sql


class ModelCollector:
    """Collects and aggregates model metrics from current telemetry authority."""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize ModelCollector

        Args:
            db_path: Path to studio.db. If None, uses default ~/.dream-studio/state/studio.db
        """
        if db_path is None:
            self.db_path = str(Path.home() / ".dream-studio" / "state" / "studio.db")
        else:
            self.db_path = db_path

    def collect(self, days: int = 90) -> Dict[str, Any]:
        """
        Collect model metrics

        Args:
            days: Number of days of history to collect (default: 90)

        Returns:
            Dict containing:
                - by_model: Dict[model -> {invocations, success_rate, avg_exec_time, tokens}]
                - distribution: Dict[model -> percentage]
                - performance_rank: List[(model, score)] ordered by performance
                - token_efficiency: Dict[model -> tokens_per_second]
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            skill_sql = skill_usage_sql(conn)
            token_sql = token_usage_sql(conn)

            # Performance metrics from skill telemetry
            if skill_sql is not None:
                cursor.execute(
                    f"""
                    SELECT
                        model,
                        COUNT(*) as invocations,
                        SUM(success) as successes,
                        AVG(execution_time_s) as avg_exec_time,
                        AVG(input_tokens + output_tokens) as avg_tokens_per_run
                    FROM ({skill_sql}) skill_usage
                    WHERE invoked_at >= ?
                    AND model IS NOT NULL
                    GROUP BY model
                """,
                    (cutoff_date,),
                )
                skill_rows = cursor.fetchall()
            else:
                skill_rows = []

            by_model = {}
            total_invocations = 0

            for row in skill_rows:
                model = row["model"]
                invocations = row["invocations"]
                successes = row["successes"] or 0
                success_rate = (successes / invocations * 100) if invocations > 0 else 0.0

                by_model[model] = {
                    "invocations": invocations,
                    "success_rate": round(success_rate, 1),
                    "avg_exec_time_s": (
                        round(row["avg_exec_time"], 2) if row["avg_exec_time"] else 0.0
                    ),
                    "avg_tokens_per_run": (
                        round(row["avg_tokens_per_run"], 0) if row["avg_tokens_per_run"] else 0
                    ),
                }

                total_invocations += invocations

            # Add token totals from token usage
            if token_sql is not None:
                cursor.execute(
                    f"""
                    SELECT
                        model,
                        SUM(input_tokens + output_tokens) as total_tokens
                    FROM ({token_sql}) token_usage
                    WHERE recorded_at >= ?
                    AND model IS NOT NULL
                    GROUP BY model
                """,
                    (cutoff_date,),
                )
                token_rows = cursor.fetchall()
            else:
                token_rows = []

            for row in token_rows:
                model = row["model"]
                if model in by_model:
                    by_model[model]["total_tokens"] = row["total_tokens"] or 0

            # Calculate distribution percentages
            distribution = {}
            for model, data in by_model.items():
                percentage = (
                    (data["invocations"] / total_invocations * 100)
                    if total_invocations > 0
                    else 0.0
                )
                distribution[model] = round(percentage, 1)

            # Performance ranking (higher is better)
            # Score = success_rate * (1 / avg_exec_time) * distribution_weight
            performance_rank = []
            for model, data in by_model.items():
                if data["avg_exec_time_s"] > 0:
                    # Speed score (inverted time)
                    speed_score = 1 / data["avg_exec_time_s"]
                    # Weighted by success rate and usage
                    score = (
                        (data["success_rate"] / 100)
                        * speed_score
                        * (distribution.get(model, 0) / 100)
                    )
                    performance_rank.append((model, round(score, 4)))

            performance_rank.sort(key=lambda x: x[1], reverse=True)

            # Extract success rates as separate dict
            success_rates = {model: data["success_rate"] for model, data in by_model.items()}

            return {
                "total_invocations": total_invocations,
                "by_model": by_model,
                "distribution_pct": distribution,
                "success_rates": success_rates,
                "performance_rank": [
                    model for model, score in performance_rank
                ],  # Just model names
            }

        finally:
            conn.close()

    def get_model_timeline(self, model_name: str, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get daily usage timeline for a specific model

        Args:
            model_name: Name of the model
            days: Number of days of history

        Returns:
            List of dicts with date, invocations, success_rate
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            skill_sql = skill_usage_sql(conn)
            if skill_sql is None:
                return []

            cursor.execute(
                f"""
                SELECT
                    DATE(invoked_at) as date,
                    COUNT(*) as invocations,
                    SUM(success) as successes,
                    AVG(execution_time_s) as avg_exec_time
                FROM ({skill_sql}) skill_usage
                WHERE model = ?
                AND invoked_at >= ?
                GROUP BY DATE(invoked_at)
                ORDER BY date ASC
            """,
                (model_name, cutoff_date),
            )

            timeline = []
            for row in cursor.fetchall():
                invocations = row["invocations"]
                successes = row["successes"] or 0
                success_rate = (successes / invocations * 100) if invocations > 0 else 0.0

                timeline.append(
                    {
                        "date": row["date"],
                        "invocations": invocations,
                        "success_rate": round(success_rate, 1),
                        "avg_exec_time_s": (
                            round(row["avg_exec_time"], 2) if row["avg_exec_time"] else 0.0
                        ),
                    }
                )

            return timeline

        finally:
            conn.close()
