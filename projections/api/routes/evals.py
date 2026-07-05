"""Eval Health routes — surfaces ds_eval_baselines + eval canonical events for the dashboard."""

import json

from fastapi import APIRouter
from typing import Any

from core.config.database import get_connection

router = APIRouter()
registry_router = APIRouter()


def _has_table(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


@router.get("/health")
async def get_eval_health() -> dict[str, Any]:
    """Return eval baseline pass rates and recent run history for the dashboard."""
    conn = get_connection()
    try:
        if not _has_table(conn, "ds_eval_baselines"):
            return {
                "total_evals": 0,
                "passing": 0,
                "failing": 0,
                "pass_rate": None,
                "baselines": [],
                "recent_runs": [],
                "source_status": {
                    "classification": "empty by design",
                    "reason": "ds_eval_baselines table not yet created — run migrations first.",
                },
            }

        baselines = conn.execute("""
            SELECT eval_id, version, baseline_score, regression_flag, last_run_at
            FROM ds_eval_baselines
            ORDER BY last_run_at DESC
            """).fetchall()

        total = len(baselines)
        passing = sum(1 for r in baselines if not r["regression_flag"])
        failing = total - passing
        pass_rate = round(passing / total * 100, 1) if total > 0 else None

        # Recent runs now come from the canonical event stream — ds_eval_runs was
        # dropped in T4 (WO-DBA-EVAL-DECISION). work_order.verified events carry
        # composite_score instead of total_score; COALESCE bridges the two shapes.
        recent_runs: list = []
        if _has_table(conn, "business_canonical_events"):
            rows = conn.execute("""
                SELECT payload
                FROM business_canonical_events
                WHERE event_type IN ('eval.run.completed', 'work_order.verified')
                ORDER BY event_timestamp DESC
                LIMIT 20
                """).fetchall()
            recent_runs = []
            for r in rows:
                payload = json.loads(r["payload"]) if r["payload"] else {}
                recent_runs.append(
                    {
                        "run_id": payload.get("run_id"),
                        "eval_id": payload.get("eval_id"),
                        "total_score": payload.get("total_score", payload.get("composite_score")),
                        "passed": bool(payload.get("passed")),
                        "started_at": payload.get("started_at"),
                        "model_tested": payload.get("model_tested"),
                    }
                )

        return {
            "total_evals": total,
            "passing": passing,
            "failing": failing,
            "pass_rate": pass_rate,
            "baselines": [
                {
                    "eval_id": r["eval_id"],
                    "version": r["version"],
                    "score": r["baseline_score"],
                    "passed": not bool(r["regression_flag"]),
                    "last_run_at": r["last_run_at"],
                }
                for r in baselines
            ],
            "recent_runs": recent_runs,
        }
    finally:
        conn.close()


@registry_router.get("/registry")
async def get_eval_registry() -> list[dict[str, Any]]:
    """Return eval_registry entries joined with baseline scores from ds_eval_baselines."""
    conn = get_connection()
    try:
        if not _has_table(conn, "eval_registry"):
            return []

        # Baseline score now comes from ds_eval_baselines (join on eval_id) instead
        # of the dropped ds_eval_runs table (T4, WO-DBA-EVAL-DECISION).
        has_baselines = _has_table(conn, "ds_eval_baselines")
        if has_baselines:
            rows = conn.execute("""
                SELECT
                    er.target_id,
                    er.target_type,
                    er.rubric_score,
                    er.friction_flag,
                    er.last_run_at,
                    er.last_run_id,
                    eb.baseline_score AS baseline_score
                FROM eval_registry er
                LEFT JOIN ds_eval_baselines eb ON eb.eval_id = er.eval_id
                ORDER BY er.target_type, er.target_id
            """).fetchall()
        else:
            rows = conn.execute("""
                SELECT
                    target_id, target_type, rubric_score, friction_flag,
                    last_run_at, last_run_id,
                    NULL AS baseline_score
                FROM eval_registry
                ORDER BY target_type, target_id
            """).fetchall()

        return [
            {
                "target_id": r["target_id"],
                "target_type": r["target_type"],
                "rubric_score": r["rubric_score"],
                "baseline_score": r["baseline_score"],
                "friction_flag": bool(r["friction_flag"]),
                "last_run_at": r["last_run_at"],
                "last_run_id": r["last_run_id"],
            }
            for r in rows
        ]
    finally:
        conn.close()
