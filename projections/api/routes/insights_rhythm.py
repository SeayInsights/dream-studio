"""Work rhythm analysis endpoint: heatmap, peak hours/days, productivity patterns.

WO-GF-API-ROUTES: split out of insights.py.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import Query

from .insights_router import router


@router.get("/rhythm")
async def get_work_rhythm(days: int = Query(default=30, ge=1, le=365)):
    """Get work rhythm analysis: heatmap, peak hours/days, productivity patterns.

    Reads from DuckDB aggregate_metrics.db (raw_sessions view over events_fact).
    """
    from collections import defaultdict
    from core.analytics.duckdb_store import connect_analytics
    from datetime import timedelta

    conn = connect_analytics(read_only=True)

    try:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        # Heatmap: 7 days x 24 hours — DuckDB strftime same format as SQLite
        rows = conn.execute(
            """
            SELECT
                CAST(strftime(started_at, '%w') AS INTEGER) as dow,
                CAST(strftime(started_at, '%H') AS INTEGER) as hour,
                COUNT(*) as count
            FROM raw_sessions
            WHERE started_at >= ?
            GROUP BY dow, hour
        """,
            [cutoff],
        ).fetchall()

        heatmap = [[0] * 24 for _ in range(7)]
        for row in rows:
            heatmap[row[0]][row[1]] = row[2]

        # Peak hour
        hour_totals = defaultdict(int)
        for dow in range(7):
            for hour in range(24):
                hour_totals[hour] += heatmap[dow][hour]
        peak_hour = max(hour_totals, key=hour_totals.get) if hour_totals else 0

        # Peak day
        day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        day_totals = {d: sum(heatmap[d]) for d in range(7)}
        peak_day_idx = max(day_totals, key=day_totals.get) if day_totals else 0
        quietest_day_idx = min(day_totals, key=day_totals.get) if day_totals else 0

        # Completion rate by hour
        comp_rows = conn.execute(
            """
            SELECT
                CAST(strftime(started_at, '%H') AS INTEGER) as hour,
                COUNT(*) as total,
                SUM(CASE WHEN outcome = 'completed' THEN 1 ELSE 0 END) as completed
            FROM raw_sessions
            WHERE started_at >= ?
            GROUP BY hour
        """,
            [cutoff],
        ).fetchall()
        completion_by_hour = {}
        for row in comp_rows:
            total = row[1]
            completed = row[2] or 0
            completion_by_hour[str(row[0])] = round(completed / total, 3) if total > 0 else 0.0

        return {
            "heatmap": heatmap,
            "day_labels": day_names,
            "peak_hour": peak_hour,
            "peak_day": day_names[peak_day_idx],
            "busiest_day_count": day_totals.get(peak_day_idx, 0),
            "quietest_day": day_names[quietest_day_idx],
            "quietest_day_count": day_totals.get(quietest_day_idx, 0),
            "completion_by_hour": completion_by_hour,
            "hour_totals": dict(hour_totals),
            "generated_at": datetime.now().isoformat(),
        }
    finally:
        conn.close()
