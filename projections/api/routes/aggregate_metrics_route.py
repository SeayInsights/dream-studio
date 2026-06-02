"""Cross-skill findings aggregate endpoint.

Provides a single endpoint that aggregates findings across all skills
per project — what no existing route does today.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Query

router = APIRouter()


def _aggregate_db_conn():
    """Connect to aggregate_metrics.db via the approved helper."""
    try:
        from core.analytics.aggregate_metrics import (
            _connect_aggregate,
            aggregate_metrics_db_path,
        )

        path = aggregate_metrics_db_path()
        if not path.exists():
            return None
        return _connect_aggregate(path)
    except Exception:
        return None


@router.get("/aggregate", summary="Cross-skill findings summary per project")
async def get_aggregate_metrics(
    project_id: Optional[str] = Query(None, description="Filter by project UUID"),
    days: int = Query(30, ge=1, le=365, description="Lookback window in days"),
) -> Dict[str, Any]:
    """Cross-skill findings rollup. Aggregates finding_rollups table across all 6 skills."""
    conn = _aggregate_db_conn()
    if conn is None:
        return {
            "error": "aggregate_metrics.db not found. Run `ds analyze aggregate` first.",
            "project_id": project_id,
            "findings_by_skill": {},
            "findings_by_severity": {},
            "total_findings": 0,
            "source_status": {
                "classification": "unavailable",
                "reason": "aggregate_metrics.db not built yet",
                "derived_view": True,
            },
        }

    try:
        where = ""
        params: list = []
        if project_id:
            where = "WHERE project_id = ?"
            params.append(project_id)

        # Findings by skill
        rows = conn.execute(
            f"""SELECT skill_id, SUM(finding_count) AS total
                FROM finding_rollups {where}
                GROUP BY skill_id ORDER BY total DESC""",
            params,
        ).fetchall()
        by_skill = {r["skill_id"]: r["total"] for r in rows}

        # Findings by severity
        sev_rows = conn.execute(
            f"""SELECT severity, SUM(finding_count) AS total
                FROM finding_rollups {where}
                GROUP BY severity""",
            params,
        ).fetchall()
        by_severity = {r["severity"]: r["total"] for r in sev_rows}

        total = sum(by_skill.values())

        # Trend (last N days vs prior N days)
        trend_rows = conn.execute(
            f"""SELECT
                    SUM(CASE WHEN day >= date('now', '-{days} days') THEN finding_count ELSE 0 END) AS recent,
                    SUM(CASE WHEN day >= date('now', '-{days * 2} days')
                              AND day < date('now', '-{days} days') THEN finding_count ELSE 0 END) AS prior
                FROM finding_rollups {where}""",
            params,
        ).fetchone()
        recent = trend_rows["recent"] or 0
        prior = trend_rows["prior"] or 0
        trend = "improving" if recent < prior else "stable" if recent == prior else "regressing"

        # Last aggregated
        last_aggregated = None
        try:
            from core.analytics.aggregate_metrics import _connect_aggregate

            mc = _connect_aggregate()
            meta_row = mc.execute(
                "SELECT value FROM _aggregate_meta WHERE key = 'last_aggregated_at'"
            ).fetchone()
            last_aggregated = meta_row["value"] if meta_row else None
            mc.close()
        except Exception:
            pass

        return {
            "project_id": project_id,
            "findings_by_skill": by_skill,
            "findings_by_severity": by_severity,
            "total_findings": total,
            "trend": trend,
            "recent_count": recent,
            "prior_count": prior,
            "lookback_days": days,
            "last_aggregated_at": last_aggregated,
            "source_status": {
                "classification": "fresh" if total > 0 else "empty",
                "derived_view": True,
                "primary_authority": False,
            },
        }
    finally:
        conn.close()
