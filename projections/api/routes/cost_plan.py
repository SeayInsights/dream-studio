"""Plan vs API-equivalent cost route.

Exposes GET /api/v1/cost/plan-comparison backed by
projections.core.cost_analysis.plan_comparison.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from core.config.database import get_connection, get_db_path

from projections.core.cost_analysis import plan_comparison

router = APIRouter()


@router.get("/cost/plan-comparison")
async def get_plan_comparison() -> dict[str, Any]:
    """Return plan vs API-equivalent cost comparison.

    Response shape::

        {
            "plan_configured": bool,
            "plan_name": str | null,
            "plan_monthly_usd": float | null,
            "api_equivalent_total_usd": float,
            "delta_usd": float | null,
            "by_model": [{"model_id": str, "tokens": int, "usd": float}, ...],
            "coverage": {
                "priced_record_count": int,
                "unpriced_record_count": int,
                "record_count": int,
            },
        }
    """
    conn = get_connection()
    try:
        db_path = get_db_path()
        return plan_comparison(conn, db_path=db_path)
    finally:
        conn.close()
