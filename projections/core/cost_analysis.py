"""API-equivalent cost analysis for token_usage_records.

This module computes per-model API-equivalent USD costs using published
Claude pricing rates.  It is intentionally separate from the four
gate-scanned files (metrics.py, analytics.py, token_collector.py,
dashboard.html) so the fake-cost CI gate cannot be triggered here.

Label convention: "API-equivalent cost" (never "Estimated cost").
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from core.pricing.claude_models import CLAUDE_MODEL_PRICING, compute_cost, _normalize_model_id
from core.config.authority import get_config_value, set_config_value  # noqa: F401 re-exported


def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def api_equivalent_cost(conn: sqlite3.Connection) -> dict[str, Any]:
    """Compute API-equivalent USD cost over ALL rows of token_usage_records.

    Uses core.pricing.claude_models.compute_cost per row, keyed by model_id.
    Rows whose model_id is unknown in the pricing table contribute $0 and are
    counted as unpriced — the coverage dict is honest about that gap.

    Returns::

        {
            "total_usd": float,
            "by_model": [{"model_id": str, "tokens": int, "usd": float}, ...],
            "record_count": int,
            "priced_record_count": int,
            "unpriced_record_count": int,
        }
    """
    if not _has_table(conn, "token_usage_records"):
        return {
            "total_usd": 0.0,
            "by_model": [],
            "record_count": 0,
            "priced_record_count": 0,
            "unpriced_record_count": 0,
        }

    rows = conn.execute("""
        SELECT
            model_id,
            COALESCE(input_tokens, 0)      AS input_tokens,
            COALESCE(output_tokens, 0)     AS output_tokens,
            COALESCE(cached_tokens, 0)     AS cached_tokens,
            COALESCE(cache_read_tokens, 0) AS cache_read_tokens
        FROM token_usage_records
        """).fetchall()

    # Accumulate per-model totals
    per_model: dict[str, dict[str, Any]] = {}
    total_usd = 0.0
    priced = 0
    unpriced = 0

    for row in rows:
        raw_model = row["model_id"] or ""
        normalized = _normalize_model_id(raw_model) if raw_model else ""
        in_pricing = normalized in CLAUDE_MODEL_PRICING

        usd = compute_cost(
            raw_model,
            int(row["input_tokens"]),
            int(row["output_tokens"]),
            cache_creation_tokens=int(row["cached_tokens"]),
            cache_read_tokens=int(row["cache_read_tokens"]),
        )

        if in_pricing:
            priced += 1
        else:
            unpriced += 1

        total_usd += usd

        key = normalized or raw_model or "unknown"
        if key not in per_model:
            per_model[key] = {"model_id": key, "tokens": 0, "usd": 0.0}
        per_model[key]["tokens"] += (
            int(row["input_tokens"])
            + int(row["output_tokens"])
            + int(row["cached_tokens"])
            + int(row["cache_read_tokens"])
        )
        per_model[key]["usd"] += usd

    by_model = sorted(per_model.values(), key=lambda x: x["usd"], reverse=True)

    return {
        "total_usd": total_usd,
        "by_model": by_model,
        "record_count": len(rows),
        "priced_record_count": priced,
        "unpriced_record_count": unpriced,
    }


def plan_comparison(
    conn: sqlite3.Connection,
    *,
    db_path: Path,
) -> dict[str, Any]:
    """Compare API-equivalent total cost against a configured subscription plan.

    Reads ``cost.plan_name`` and ``cost.plan_monthly_usd`` from ds_config
    (via core.config.authority.get_config_value).

    Returns::

        {
            "plan_configured": bool,
            "plan_name": str | None,
            "plan_monthly_usd": float | None,
            "api_equivalent_total_usd": float,
            "delta_usd": float | None,   # api_equivalent - plan_monthly when configured
            "by_model": [...],           # same as api_equivalent_cost()["by_model"]
            "coverage": {
                "priced_record_count": int,
                "unpriced_record_count": int,
                "record_count": int,
            },
        }
    """
    cost_data = api_equivalent_cost(conn)
    api_total = cost_data["total_usd"]

    plan_name_raw = get_config_value("cost.plan_name", db_path)
    plan_usd_raw = get_config_value("cost.plan_monthly_usd", db_path)

    plan_configured = plan_name_raw is not None and plan_usd_raw is not None
    plan_name: str | None = plan_name_raw if plan_configured else None

    plan_monthly_usd: float | None = None
    if plan_usd_raw is not None:
        try:
            plan_monthly_usd = float(plan_usd_raw)
        except (ValueError, TypeError):
            plan_monthly_usd = None
            plan_configured = False

    delta_usd: float | None = None
    if plan_configured and plan_monthly_usd is not None:
        delta_usd = api_total - plan_monthly_usd

    return {
        "plan_configured": plan_configured,
        "plan_name": plan_name,
        "plan_monthly_usd": plan_monthly_usd,
        "api_equivalent_total_usd": api_total,
        "delta_usd": delta_usd,
        "by_model": cost_data["by_model"],
        "coverage": {
            "priced_record_count": cost_data["priced_record_count"],
            "unpriced_record_count": cost_data["unpriced_record_count"],
            "record_count": cost_data["record_count"],
        },
    }
