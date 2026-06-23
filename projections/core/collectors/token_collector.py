"""TokenCollector - Collects token usage metrics from studio.db.

Tokens are usage telemetry. Costs are reported only when SQLite records carry
an explicit cost visibility/source that makes the amount reportable.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from core.shared_intelligence.usage_accounting import REPORTABLE_COST_VISIBILITIES
from projections.api.routes.sqlite_schema import source_status
from projections.core.collectors.authority_sources import token_usage_sql


class TokenCollector:
    """Collects and aggregates token usage metrics from token_usage_records."""

    def __init__(self, db_path: str | None = None):
        """
        Initialize TokenCollector

        Args:
            db_path: Path to studio.db. If None, uses default ~/.dream-studio/state/studio.db
        """
        if db_path is None:
            self.db_path = str(Path.home() / ".dream-studio" / "state" / "studio.db")
        else:
            self.db_path = db_path

    def collect(self, days: int = 90) -> dict[str, Any]:
        """
        Collect token usage metrics

        Args:
            days: Number of days of history to collect (default: 90)

        Returns:
            Dict containing:
                - total_input_tokens: int
                - total_output_tokens: int
                - total_tokens: int
                - total_cost_usd: float | None
                - by_model: Dict[model -> {tokens, cost if reportable, percentage}]
                - by_project: Dict[project -> {tokens, cost if reportable}]
                - by_skill: Dict[skill -> {tokens, cost if reportable}]
                - daily_average: float (tokens per day)
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            source_sql = token_usage_sql(conn)
            if source_sql is None:
                return self._empty_metrics(
                    source_status(
                        "empty by design",
                        "token_usage_records is unavailable; token metrics return an honest empty state.",
                        source_tables=["token_usage_records"],
                        missing=["token_usage_records"],
                    )
                )

            # Total tokens
            cursor.execute(
                f"""
                SELECT
                    SUM(input_tokens) as total_input,
                    SUM(output_tokens) as total_output
                FROM ({source_sql}) token_usage
                WHERE recorded_at >= ?
            """,
                (cutoff_date,),
            )
            result = cursor.fetchone()
            total_input = result["total_input"] or 0
            total_output = result["total_output"] or 0
            total_tokens = total_input + total_output

            # By model with reportable cost only.
            cursor.execute(
                f"""
                SELECT
                    model,
                    billing_mode,
                    token_visibility,
                    cost_visibility,
                    usage_source,
                    cost_source,
                    accounting_confidence,
                    SUM(input_tokens) as input_tokens,
                    SUM(output_tokens) as output_tokens,
                    SUM(
                        CASE
                            WHEN cost_visibility IN ({_reportable_sql_placeholders()})
                            THEN estimated_cost
                            ELSE NULL
                        END
                    ) as reportable_cost,
                    COUNT(*) as record_count
                FROM ({source_sql}) token_usage
                WHERE recorded_at >= ?
                AND model IS NOT NULL
                GROUP BY model, billing_mode, token_visibility, cost_visibility,
                         usage_source, cost_source, accounting_confidence
                ORDER BY (input_tokens + output_tokens) DESC
            """,
                (*REPORTABLE_COST_VISIBILITIES, cutoff_date),
            )

            by_model = {}
            total_cost: float | None = None

            for row in cursor.fetchall():
                model = row["model"]
                input_tok = row["input_tokens"] or 0
                output_tok = row["output_tokens"] or 0
                total = input_tok + output_tok
                cost = _optional_float(row["reportable_cost"])
                total_cost = _sum_optional(total_cost, cost)

                by_model[model] = {
                    "input_tokens": input_tok,
                    "output_tokens": output_tok,
                    "total_tokens": total,
                    "cost_usd": _round_optional(cost),
                    "cost_visibility": row["cost_visibility"],
                    "cost_source": row["cost_source"],
                    "billing_mode": row["billing_mode"],
                    "token_visibility": row["token_visibility"],
                    "usage_source": row["usage_source"],
                    "accounting_confidence": row["accounting_confidence"],
                    "record_count": row["record_count"],
                }

            # Add percentage after total is known
            for model_data in by_model.values():
                model_data["percentage"] = round(
                    (model_data["total_tokens"] / total_tokens * 100) if total_tokens > 0 else 0.0,
                    1,
                )

            # By project.
            cursor.execute(
                f"""
                SELECT
                    project_id,
                    SUM(input_tokens) as input_tokens,
                    SUM(output_tokens) as output_tokens,
                    SUM(
                        CASE
                            WHEN cost_visibility IN ({_reportable_sql_placeholders()})
                            THEN estimated_cost
                            ELSE NULL
                        END
                    ) as reportable_cost
                FROM ({source_sql}) token_usage
                WHERE recorded_at >= ?
                AND project_id IS NOT NULL
                GROUP BY project_id
            """,
                (*REPORTABLE_COST_VISIBILITIES, cutoff_date),
            )

            by_project = {}
            for row in cursor.fetchall():
                project = row["project_id"]
                input_tok = row["input_tokens"] or 0
                output_tok = row["output_tokens"] or 0
                cost = _optional_float(row["reportable_cost"])

                if project not in by_project:
                    by_project[project] = {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "total_tokens": 0,
                        "cost_usd": None,
                    }

                by_project[project]["input_tokens"] += input_tok
                by_project[project]["output_tokens"] += output_tok
                by_project[project]["total_tokens"] += input_tok + output_tok
                by_project[project]["cost_usd"] = _round_optional(
                    _sum_optional(by_project[project]["cost_usd"], cost)
                )

            # By skill
            cursor.execute(
                f"""
                SELECT
                    skill_name,
                    SUM(input_tokens) as input_tokens,
                    SUM(output_tokens) as output_tokens,
                    SUM(
                        CASE
                            WHEN cost_visibility IN ({_reportable_sql_placeholders()})
                            THEN estimated_cost
                            ELSE NULL
                        END
                    ) as reportable_cost
                FROM ({source_sql}) token_usage
                WHERE recorded_at >= ?
                AND skill_name IS NOT NULL
                GROUP BY skill_name
            """,
                (*REPORTABLE_COST_VISIBILITIES, cutoff_date),
            )

            by_skill = {}
            for row in cursor.fetchall():
                skill = row["skill_name"]
                input_tok = row["input_tokens"] or 0
                output_tok = row["output_tokens"] or 0
                cost = _optional_float(row["reportable_cost"])

                if skill not in by_skill:
                    by_skill[skill] = {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "total_tokens": 0,
                        "cost_usd": None,
                    }

                by_skill[skill]["input_tokens"] += input_tok
                by_skill[skill]["output_tokens"] += output_tok
                by_skill[skill]["total_tokens"] += input_tok + output_tok
                by_skill[skill]["cost_usd"] = _round_optional(
                    _sum_optional(by_skill[skill]["cost_usd"], cost)
                )

            # Daily average
            daily_average = total_tokens / days if days > 0 else 0.0

            # Build timeline
            cursor.execute(
                f"""
                SELECT
                    DATE(recorded_at) as date,
                    SUM(input_tokens + output_tokens) as total
                FROM ({source_sql}) token_usage
                WHERE recorded_at >= ?
                GROUP BY DATE(recorded_at)
                ORDER BY date ASC
            """,
                (cutoff_date,),
            )
            timeline = [
                {"date": row["date"], "total": row["total"] or 0} for row in cursor.fetchall()
            ]

            return {
                "total_tokens": total_tokens,
                "input_tokens": total_input,
                "output_tokens": total_output,
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "cache_hits": 0,
                "total_cost_usd": _round_optional(total_cost),
                "cost_status": "reportable" if total_cost is not None else "unknown",
                "cost_visibility": "reportable" if total_cost is not None else "unavailable",
                "cost_policy": _cost_policy(),
                "by_model": by_model,
                "by_project": by_project,
                "by_skill": by_skill,
                "daily_average": round(daily_average, 0),
                "timeline": timeline,
                "source_status": source_status(
                    "fresh",
                    "Token metrics are derived from current token_usage_records authority.",
                    source_tables=["token_usage_records"],
                ),
            }

        finally:
            conn.close()

    def _empty_metrics(self, status: dict[str, object]) -> dict[str, Any]:
        return {
            "total_tokens": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "cache_hits": 0,
            "total_cost_usd": None,
            "cost_status": "unknown",
            "cost_visibility": "unavailable",
            "cost_policy": _cost_policy(),
            "by_model": {},
            "by_project": {},
            "by_skill": {},
            "daily_average": 0.0,
            "timeline": [],
            "source_status": status,
        }

    def get_timeline(self, days: int = 30) -> list[dict[str, Any]]:
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
            source_sql = token_usage_sql(conn)
            if source_sql is None:
                return []

            cursor.execute(
                f"""
                SELECT
                    DATE(recorded_at) as date,
                    SUM(input_tokens) as input_tokens,
                    SUM(output_tokens) as output_tokens,
                    SUM(
                        CASE
                            WHEN cost_visibility IN ({_reportable_sql_placeholders()})
                            THEN estimated_cost
                            ELSE NULL
                        END
                    ) as reportable_cost
                FROM ({source_sql}) token_usage
                WHERE recorded_at >= ?
                GROUP BY DATE(recorded_at)
                ORDER BY date ASC
            """,
                (*REPORTABLE_COST_VISIBILITIES, cutoff_date),
            )

            # Aggregate by date
            by_date = {}
            for row in cursor.fetchall():
                date = row["date"]
                input_tok = row["input_tokens"] or 0
                output_tok = row["output_tokens"] or 0
                cost = _optional_float(row["reportable_cost"])

                if date not in by_date:
                    by_date[date] = {"date": date, "tokens": 0, "cost_usd": None}

                by_date[date]["tokens"] += input_tok + output_tok
                by_date[date]["cost_usd"] = _round_optional(
                    _sum_optional(by_date[date]["cost_usd"], cost)
                )

            return sorted(by_date.values(), key=lambda x: x["date"])

        finally:
            conn.close()


def _reportable_sql_placeholders() -> str:
    return ",".join("?" for _ in REPORTABLE_COST_VISIBILITIES)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _sum_optional(current: float | None, value: float | None) -> float | None:
    if value is None:
        return current
    return (current or 0.0) + value


def _round_optional(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def _cost_policy() -> dict[str, Any]:
    return {
        "tokens_are_usage_not_cost": True,
        "plan_usage_does_not_infer_cost": True,
        "cost_unknown_display": "unknown",
        "provider_billing_credentials_inspected": False,
    }
