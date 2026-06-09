"""Eval Health routes — surfaces ds_eval_baselines and ds_eval_runs for the dashboard."""

from fastapi import APIRouter
from typing import Any, Dict

from core.config.database import get_connection

router = APIRouter()


def _has_table(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


@router.get("/health")
async def get_eval_health() -> Dict[str, Any]:
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
            SELECT eval_id, eval_version, score, passed, last_run_at
            FROM ds_eval_baselines
            ORDER BY last_run_at DESC
            """).fetchall()

        total = len(baselines)
        passing = sum(1 for r in baselines if r["passed"])
        failing = total - passing
        pass_rate = round(passing / total * 100, 1) if total > 0 else None

        recent_runs: list = []
        if _has_table(conn, "ds_eval_runs"):
            rows = conn.execute("""
                SELECT run_id, eval_id, total_score, passed, started_at, model_tested
                FROM ds_eval_runs
                ORDER BY started_at DESC
                LIMIT 20
                """).fetchall()
            recent_runs = [
                {
                    "run_id": r["run_id"],
                    "eval_id": r["eval_id"],
                    "total_score": r["total_score"],
                    "passed": bool(r["passed"]),
                    "started_at": r["started_at"],
                    "model_tested": r["model_tested"],
                }
                for r in rows
            ]

        return {
            "total_evals": total,
            "passing": passing,
            "failing": failing,
            "pass_rate": pass_rate,
            "baselines": [
                {
                    "eval_id": r["eval_id"],
                    "version": r["eval_version"],
                    "score": r["score"],
                    "passed": bool(r["passed"]),
                    "last_run_at": r["last_run_at"],
                }
                for r in baselines
            ],
            "recent_runs": recent_runs,
        }
    finally:
        conn.close()
