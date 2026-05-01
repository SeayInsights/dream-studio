"""TokenCollector - Collects token usage and cost metrics from studio.db"""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional


# Claude pricing (as of 2026) - $/million tokens
PRICING = {
    "opus": {"input": 15.00, "output": 75.00},
    "sonnet": {"input": 3.00, "output": 15.00},
    "haiku": {"input": 0.80, "output": 4.00},
    # Legacy model names
    "claude-opus-4": {"input": 15.00, "output": 75.00},
    "claude-sonnet-4": {"input": 3.00, "output": 15.00},
    "claude-haiku-4": {"input": 0.80, "output": 4.00},
}


class TokenCollector:
    """Collects and aggregates token usage and cost metrics from raw_token_usage table"""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize TokenCollector

        Args:
            db_path: Path to studio.db. If None, uses default ~/.dream-studio/state/studio.db
        """
        if db_path is None:
            self.db_path = str(Path.home() / ".dream-studio" / "state" / "studio.db")
        else:
            self.db_path = db_path

    def _calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost in USD for given token usage"""
        # Normalize model name
        model_key = model.lower()
        for key in PRICING:
            if key in model_key:
                pricing = PRICING[key]
                input_cost = (input_tokens / 1_000_000) * pricing["input"]
                output_cost = (output_tokens / 1_000_000) * pricing["output"]
                return input_cost + output_cost
        return 0.0  # Unknown model

    def collect(self, days: int = 90) -> Dict[str, Any]:
        """
        Collect token usage metrics

        Args:
            days: Number of days of history to collect (default: 90)

        Returns:
            Dict containing:
                - total_input_tokens: int
                - total_output_tokens: int
                - total_tokens: int
                - total_cost_usd: float
                - by_model: Dict[model -> {tokens, cost, percentage}]
                - by_project: Dict[project -> {tokens, cost}]
                - by_skill: Dict[skill -> {tokens, cost}]
                - daily_average: float (tokens per day)
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            # Total tokens
            cursor.execute("""
                SELECT
                    SUM(input_tokens) as total_input,
                    SUM(output_tokens) as total_output
                FROM raw_token_usage
                WHERE recorded_at >= ?
            """, (cutoff_date,))
            result = cursor.fetchone()
            total_input = result["total_input"] or 0
            total_output = result["total_output"] or 0
            total_tokens = total_input + total_output

            # By model with cost
            cursor.execute("""
                SELECT
                    model,
                    SUM(input_tokens) as input_tokens,
                    SUM(output_tokens) as output_tokens,
                    COUNT(*) as record_count
                FROM raw_token_usage
                WHERE recorded_at >= ?
                AND model IS NOT NULL
                GROUP BY model
                ORDER BY (input_tokens + output_tokens) DESC
            """, (cutoff_date,))

            by_model = {}
            total_cost = 0.0

            for row in cursor.fetchall():
                model = row["model"]
                input_tok = row["input_tokens"] or 0
                output_tok = row["output_tokens"] or 0
                total = input_tok + output_tok
                cost = self._calculate_cost(model, input_tok, output_tok)
                total_cost += cost

                by_model[model] = {
                    "input_tokens": input_tok,
                    "output_tokens": output_tok,
                    "total_tokens": total,
                    "cost_usd": round(cost, 2),
                    "record_count": row["record_count"]
                }

            # Add percentage after total is known
            for model_data in by_model.values():
                model_data["percentage"] = round(
                    (model_data["total_tokens"] / total_tokens * 100) if total_tokens > 0 else 0.0,
                    1
                )

            # By project
            cursor.execute("""
                SELECT
                    project_id,
                    SUM(input_tokens) as input_tokens,
                    SUM(output_tokens) as output_tokens,
                    model
                FROM raw_token_usage
                WHERE recorded_at >= ?
                AND project_id IS NOT NULL
                GROUP BY project_id, model
            """, (cutoff_date,))

            by_project = {}
            for row in cursor.fetchall():
                project = row["project_id"]
                input_tok = row["input_tokens"] or 0
                output_tok = row["output_tokens"] or 0
                cost = self._calculate_cost(row["model"], input_tok, output_tok)

                if project not in by_project:
                    by_project[project] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0}

                by_project[project]["input_tokens"] += input_tok
                by_project[project]["output_tokens"] += output_tok
                by_project[project]["total_tokens"] += (input_tok + output_tok)
                by_project[project]["cost_usd"] = round(by_project[project]["cost_usd"] + cost, 2)

            # By skill
            cursor.execute("""
                SELECT
                    skill_name,
                    SUM(input_tokens) as input_tokens,
                    SUM(output_tokens) as output_tokens,
                    model
                FROM raw_token_usage
                WHERE recorded_at >= ?
                AND skill_name IS NOT NULL
                GROUP BY skill_name, model
            """, (cutoff_date,))

            by_skill = {}
            for row in cursor.fetchall():
                skill = row["skill_name"]
                input_tok = row["input_tokens"] or 0
                output_tok = row["output_tokens"] or 0
                cost = self._calculate_cost(row["model"], input_tok, output_tok)

                if skill not in by_skill:
                    by_skill[skill] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0}

                by_skill[skill]["input_tokens"] += input_tok
                by_skill[skill]["output_tokens"] += output_tok
                by_skill[skill]["total_tokens"] += (input_tok + output_tok)
                by_skill[skill]["cost_usd"] = round(by_skill[skill]["cost_usd"] + cost, 2)

            # Daily average
            daily_average = total_tokens / days if days > 0 else 0.0

            return {
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "total_tokens": total_tokens,
                "total_cost_usd": round(total_cost, 2),
                "by_model": by_model,
                "by_project": by_project,
                "by_skill": by_skill,
                "daily_average": round(daily_average, 0)
            }

        finally:
            conn.close()

    def get_timeline(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get daily token usage timeline

        Args:
            days: Number of days of history

        Returns:
            List of dicts with date, tokens, cost
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            cursor.execute("""
                SELECT
                    DATE(recorded_at) as date,
                    SUM(input_tokens) as input_tokens,
                    SUM(output_tokens) as output_tokens,
                    model
                FROM raw_token_usage
                WHERE recorded_at >= ?
                GROUP BY DATE(recorded_at), model
                ORDER BY date ASC
            """, (cutoff_date,))

            # Aggregate by date
            by_date = {}
            for row in cursor.fetchall():
                date = row["date"]
                input_tok = row["input_tokens"] or 0
                output_tok = row["output_tokens"] or 0
                cost = self._calculate_cost(row["model"], input_tok, output_tok)

                if date not in by_date:
                    by_date[date] = {"date": date, "tokens": 0, "cost_usd": 0.0}

                by_date[date]["tokens"] += (input_tok + output_tok)
                by_date[date]["cost_usd"] = round(by_date[date]["cost_usd"] + cost, 2)

            return sorted(by_date.values(), key=lambda x: x["date"])

        finally:
            conn.close()
