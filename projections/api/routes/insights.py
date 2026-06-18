"""Insights API routes"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from core.telemetry.attribution_config import ATTRIBUTION_COVERAGE_MIN as _ATTRIBUTION_COVERAGE_MIN

from ..models.insights import (
    InsightsResponse,
    RecommendationsResponse,
    HighPriorityResponse,
    RootCauseAnalysis,
)
from projections.core.collectors import (
    SessionCollector,
    SkillCollector,
    TokenCollector,
    ModelCollector,
    LessonCollector,
    WorkflowCollector,
)
from projections.core.analyzers import (
    PerformanceAnalyzer,
    TrendAnalyzer,
    AnomalyDetector,
    Predictor,
)
from projections.core.insights import InsightEngine, RootCauseAnalyzer, RecommendationEngine

router = APIRouter()


def get_db_path() -> str:
    """Get database path"""
    from core.config.database import get_db_path as _canonical

    return str(_canonical())


def collect_metrics(days: int = 30):
    """Collect all metrics"""
    db_path = get_db_path()

    collectors = {
        "sessions": SessionCollector(db_path),
        "skills": SkillCollector(db_path),
        "tokens": TokenCollector(db_path),
        "models": ModelCollector(db_path),
        "lessons": LessonCollector(db_path),
        "workflows": WorkflowCollector(db_path),
    }

    metrics = {key: collector.collect(days=days) for key, collector in collectors.items()}

    return metrics


def analyze_metrics(metrics: dict):
    """Run all analyzers on metrics"""
    perf_analyzer = PerformanceAnalyzer()
    trend_analyzer = TrendAnalyzer()
    anomaly_detector = AnomalyDetector()
    predictor = Predictor()

    analysis = {}

    # Performance analysis
    if "skills" in metrics:
        analysis["performance"] = perf_analyzer.analyze_skill_performance(metrics["skills"])

    # Trend analysis
    if "sessions" in metrics and "timeline" in metrics["sessions"]:
        analysis["trends"] = {
            "sessions": trend_analyzer.analyze_timeline(metrics["sessions"]["timeline"])
        }

    # Anomaly detection
    if "sessions" in metrics and "timeline" in metrics["sessions"]:
        anomaly_results = anomaly_detector.comprehensive_anomaly_scan(
            metrics["sessions"]["timeline"]
        )
        analysis["anomalies"] = anomaly_results

    # Forecasting
    if "sessions" in metrics and "timeline" in metrics["sessions"]:
        forecast = predictor.forecast_linear(metrics["sessions"]["timeline"], steps_ahead=7)
        analysis["forecast"] = forecast

    return analysis


@router.get("/", response_model=InsightsResponse)
async def get_all_insights(days: int = Query(default=30, ge=1, le=365)):
    """Get comprehensive insights"""
    try:
        # Collect metrics
        metrics = collect_metrics(days)

        # Analyze metrics
        analysis = analyze_metrics(metrics)

        # Generate insights
        engine = InsightEngine()
        insights = engine.generate_insights(metrics, analysis)

        return InsightsResponse(**insights)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating insights: {str(e)}")


@router.get("/strengths")
async def get_strengths(days: int = Query(default=30, ge=1, le=365)):
    """Get strengths analysis"""
    try:
        metrics = collect_metrics(days)
        analysis = analyze_metrics(metrics)

        engine = InsightEngine()
        insights = engine.generate_insights(metrics, analysis)

        return {
            "strengths": insights["strengths"],
            "count": len(insights["strengths"]),
            "generated_at": insights["generated_at"],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing strengths: {str(e)}")


@router.get("/issues")
async def get_issues(days: int = Query(default=30, ge=1, le=365)):
    """Get issues detected"""
    try:
        metrics = collect_metrics(days)
        analysis = analyze_metrics(metrics)

        engine = InsightEngine()
        insights = engine.generate_insights(metrics, analysis)

        return {
            "issues": insights["issues"],
            "count": len(insights["issues"]),
            "generated_at": insights["generated_at"],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error detecting issues: {str(e)}")


@router.get("/opportunities")
async def get_opportunities(days: int = Query(default=30, ge=1, le=365)):
    """Get improvement opportunities"""
    try:
        metrics = collect_metrics(days)
        analysis = analyze_metrics(metrics)

        engine = InsightEngine()
        insights = engine.generate_insights(metrics, analysis)

        return {
            "opportunities": insights["opportunities"],
            "count": len(insights["opportunities"]),
            "generated_at": insights["generated_at"],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error identifying opportunities: {str(e)}")


@router.get("/risks")
async def get_risks(days: int = Query(default=30, ge=1, le=365)):
    """Get risk analysis"""
    try:
        metrics = collect_metrics(days)
        analysis = analyze_metrics(metrics)

        engine = InsightEngine()
        insights = engine.generate_insights(metrics, analysis)

        return {
            "risks": insights["risks"],
            "count": len(insights["risks"]),
            "generated_at": insights["generated_at"],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing risks: {str(e)}")


@router.get("/high-priority", response_model=HighPriorityResponse)
async def get_high_priority(days: int = Query(default=30, ge=1, le=365)):
    """Get high priority insights only"""
    try:
        metrics = collect_metrics(days)
        analysis = analyze_metrics(metrics)

        engine = InsightEngine()
        insights = engine.generate_insights(metrics, analysis)

        high_priority = engine.get_high_priority_insights(insights)

        return HighPriorityResponse(
            high_priority=high_priority,
            count=len(high_priority),
            generated_at=datetime.now().isoformat(),
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error getting high priority insights: {str(e)}"
        )


@router.get("/recommendations", response_model=RecommendationsResponse)
async def get_recommendations(days: int = Query(default=30, ge=1, le=365)):
    """Get strategic recommendations"""
    try:
        metrics = collect_metrics(days)
        analysis = analyze_metrics(metrics)

        # Generate insights
        insight_engine = InsightEngine()
        insights = insight_engine.generate_insights(metrics, analysis)

        # Generate recommendations
        rec_engine = RecommendationEngine()
        recommendations = rec_engine.generate_recommendations(insights)
        quick_wins = rec_engine.get_quick_wins(recommendations)
        grouped = rec_engine.group_by_category(recommendations)
        executive_summary = rec_engine.format_for_executive(recommendations, limit=5)

        return RecommendationsResponse(
            recommendations=recommendations,
            quick_wins=quick_wins,
            grouped=grouped,
            executive_summary=executive_summary,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating recommendations: {str(e)}")


@router.post("/root-cause", response_model=RootCauseAnalysis)
async def analyze_root_cause(
    issue_index: int = Query(description="Index of issue to analyze"),
    days: int = Query(default=30, ge=1, le=365),
):
    """Perform root cause analysis on a specific issue"""
    try:
        metrics = collect_metrics(days)
        analysis = analyze_metrics(metrics)

        # Generate insights
        insight_engine = InsightEngine()
        insights = insight_engine.generate_insights(metrics, analysis)

        # Get the specific issue
        issues = insights["issues"]
        if issue_index < 0 or issue_index >= len(issues):
            raise HTTPException(status_code=404, detail="Issue not found")

        issue = issues[issue_index]

        # Perform root cause analysis
        rc_analyzer = RootCauseAnalyzer()
        root_cause = rc_analyzer.analyze_issue(issue, metrics, analysis)

        return RootCauseAnalysis(**root_cause)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing root cause: {str(e)}")


@router.get("/rhythm")
async def get_work_rhythm(days: int = Query(default=30, ge=1, le=365)):
    """Get work rhythm analysis: heatmap, peak hours/days, productivity patterns"""
    from collections import defaultdict
    from core.config.database import get_connection

    conn = get_connection()
    cursor = conn.cursor()

    try:
        from datetime import timedelta

        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        # Heatmap: 7 days x 24 hours
        cursor.execute(
            """
            SELECT
                CAST(strftime('%w', started_at) AS INTEGER) as dow,
                CAST(strftime('%H', started_at) AS INTEGER) as hour,
                COUNT(*) as count
            FROM raw_sessions
            WHERE started_at >= ?
            GROUP BY dow, hour
        """,
            (cutoff,),
        )

        heatmap = [[0] * 24 for _ in range(7)]
        for row in cursor.fetchall():
            heatmap[row["dow"]][row["hour"]] = row["count"]

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
        cursor.execute(
            """
            SELECT
                CAST(strftime('%H', started_at) AS INTEGER) as hour,
                COUNT(*) as total,
                SUM(CASE WHEN outcome = 'completed' THEN 1 ELSE 0 END) as completed
            FROM raw_sessions
            WHERE started_at >= ?
            GROUP BY hour
        """,
            (cutoff,),
        )
        completion_by_hour = {}
        for row in cursor.fetchall():
            total = row["total"]
            completed = row["completed"] or 0
            completion_by_hour[str(row["hour"])] = round(completed / total, 3) if total > 0 else 0.0

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


# ---------------------------------------------------------------------------
# Attribution coverage — 18.4.2a
# ---------------------------------------------------------------------------


@router.get("/attribution-coverage")
async def get_attribution_coverage(project_id: str = Query(default=None)):
    """Return attribution coverage breakdown for token.consumed events.

    Internal diagnostic panel — surfaced under Intelligence > Token Attribution.
    Compares fully_attributed / partial / orphan counts.
    Logs a warning when coverage drops below the configured threshold.
    """
    from projections.api.queries.token_attribution import attribution_coverage
    import logging

    log = logging.getLogger(__name__)

    try:
        data = attribution_coverage(project_id=project_id)
        fully_pct = data.get("fully_attributed_pct", 0.0)

        # Log warning if fully-attributed coverage falls below threshold.
        if data.get("data_status") == "ok" and (fully_pct / 100) < _ATTRIBUTION_COVERAGE_MIN:
            log.warning(
                "attribution_coverage below threshold: %.1f%% < %.0f%% "
                "(project_id=%s total_events=%d)",
                fully_pct,
                _ATTRIBUTION_COVERAGE_MIN * 100,
                project_id,
                data.get("total_events", 0),
            )

        return {
            "schema": "dream_studio.attribution_coverage.v1",
            "project_id": project_id,
            "total_events": data.get("total_events", 0),
            "fully_attributed_count": data.get("fully_attributed_count", 0),
            "partial_count": data.get("partial_count", 0),
            "orphan_count": data.get("orphan_count", 0),
            "fully_attributed_pct": data.get("fully_attributed_pct", 0.0),
            "partial_pct": data.get("partial_pct", 0.0),
            "orphan_pct": data.get("orphan_pct", 0.0),
            "coverage_threshold_pct": _ATTRIBUTION_COVERAGE_MIN * 100,
            "below_threshold": (fully_pct / 100) < _ATTRIBUTION_COVERAGE_MIN,
            "data_status": data.get("data_status", "empty"),
            "visibility": "internal",
            "generated_at": datetime.now().isoformat(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error computing attribution coverage: {exc}")


@router.get("/attribution-coverage/orphans")
async def get_attribution_orphans(
    project_id: str = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Return recent orphan token.consumed events for drill-down.

    Orphans are events where attribution_status is NULL or 'orphan'.
    No raw payloads or PII are included.
    """
    from projections.api.queries.token_attribution import orphan_events

    try:
        events = orphan_events(project_id=project_id, limit=limit)
        return {
            "schema": "dream_studio.attribution_orphans.v1",
            "project_id": project_id,
            "orphan_count": len(events),
            "limit": limit,
            "orphans": events,
            "generated_at": datetime.now().isoformat(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error fetching orphan events: {exc}")


# ---------------------------------------------------------------------------
# Memory Surface — Chain 7 dashboard panel (18.4.4)
# ---------------------------------------------------------------------------


@router.get("/memory-surface")
async def get_memory_surface(project_id: str = Query(default=None)) -> dict:
    """Return memory_entries summary for the Chain 7 dashboard panel.

    Shows total entries, surfaced-this-session count, source type breakdown,
    and the 10 most recently surfaced entries. Read-only.
    """
    from core.config.database import get_connection

    try:
        conn = get_connection()
        conn.row_factory = __import__("sqlite3").Row
        try:
            total = conn.execute("SELECT COUNT(*) FROM memory_entries").fetchone()[0]

            surfaced = conn.execute(
                "SELECT COUNT(*) FROM memory_entries WHERE intelligence_surfaced_at IS NOT NULL"
            ).fetchone()[0]

            source_rows = conn.execute(
                "SELECT source, COUNT(*) cnt FROM memory_entries GROUP BY source ORDER BY cnt DESC"
            ).fetchall()
            source_types = {r["source"]: r["cnt"] for r in source_rows}

            recent_rows = conn.execute(
                "SELECT memory_id, content, importance, category, intelligence_surfaced_at"
                " FROM memory_entries"
                " WHERE intelligence_surfaced_at IS NOT NULL"
                " ORDER BY intelligence_surfaced_at DESC LIMIT 10"
            ).fetchall()

            def _label(imp: float) -> str:
                if imp >= 0.8:
                    return "high"
                if imp >= 0.5:
                    return "medium"
                return "low"

            recently_surfaced = [
                {
                    "memory_id": r["memory_id"],
                    "content": (r["content"] or "")[:150],
                    "importance": r["importance"],
                    "importance_label": _label(r["importance"] or 0.5),
                    "category": r["category"],
                    "surfaced_at": r["intelligence_surfaced_at"],
                }
                for r in recent_rows
            ]
        finally:
            conn.close()

        return {
            "schema": "dream_studio.memory_surface.v1",
            "project_id": project_id,
            "total_entries": total,
            "surfaced_this_session": surfaced,
            "source_types": source_types,
            "recently_surfaced": recently_surfaced,
            "generated_at": datetime.now().isoformat(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error fetching memory surface: {exc}")


# ---------------------------------------------------------------------------
# Attribution Breakouts — token usage aggregated by dimension (18.x)
# ---------------------------------------------------------------------------

_BREAKOUT_REQUIRED_COLUMNS = {
    "project_id",
    "milestone_id",
    "task_id",
    "skill_id",
    "agent_id",
    "input_tokens",
    "output_tokens",
}


@router.get("/attribution-breakouts")
async def get_attribution_breakouts() -> dict:
    """Return token usage aggregated by project, milestone, task, skill, and agent.

    Reads directly from ``token_usage_records``. If the table does not exist or
    lacks the expected columns, returns ``data_status="empty"`` with empty lists.
    All breakouts are capped at 20 rows, ordered by tokens DESC.
    """
    import sqlite3 as _sqlite3
    from core.config.database import get_connection
    from projections.api.routes.sqlite_schema import has_columns, object_exists

    _EMPTY = {
        "schema": "dream_studio.attribution_breakouts.v1",
        "total_tokens": 0,
        "total_records": 0,
        "by_project": [],
        "by_milestone": [],
        "by_task": [],
        "by_skill": [],
        "by_agent": [],
        "data_status": "empty",
        "generated_at": datetime.now().isoformat(),
    }

    try:
        conn = get_connection()
        conn.row_factory = _sqlite3.Row
        try:
            if not object_exists(conn, "token_usage_records"):
                return _EMPTY

            if not has_columns(conn, "token_usage_records", _BREAKOUT_REQUIRED_COLUMNS):
                return _EMPTY

            # Totals
            totals_row = conn.execute(
                "SELECT"
                "  COALESCE(SUM(input_tokens + output_tokens), 0) AS total_tokens,"
                "  COUNT(*) AS total_records"
                " FROM token_usage_records"
            ).fetchone()
            total_tokens = int(totals_row["total_tokens"] or 0)
            total_records = int(totals_row["total_records"] or 0)

            def _breakout(column: str) -> list[dict]:
                rows = conn.execute(
                    f"SELECT {column} AS key,"
                    f"  SUM(input_tokens + output_tokens) AS tokens,"
                    f"  COUNT(*) AS records"
                    f" FROM token_usage_records"
                    f" WHERE {column} IS NOT NULL"
                    f" GROUP BY {column}"
                    f" ORDER BY tokens DESC"
                    f" LIMIT 20"
                ).fetchall()
                return [
                    {
                        column: row["key"],
                        "tokens": int(row["tokens"] or 0),
                        "records": int(row["records"] or 0),
                    }
                    for row in rows
                ]

            by_project = _breakout("project_id")

            # Enrich by_project rows with human-readable project names.
            # Falls back to None per row if business_projects doesn't exist or lookup fails.
            try:
                if by_project and object_exists(conn, "business_projects"):
                    project_ids = [row["project_id"] for row in by_project]
                    placeholders = ",".join("?" * len(project_ids))
                    name_rows = conn.execute(
                        f"SELECT project_id, name FROM business_projects"
                        f" WHERE project_id IN ({placeholders})",
                        project_ids,
                    ).fetchall()
                    name_map: dict[str, str | None] = {
                        r["project_id"]: r["name"] for r in name_rows
                    }
                    by_project = [
                        {
                            "project_id": row["project_id"],
                            "project_name": name_map.get(row["project_id"]),
                            "tokens": row["tokens"],
                            "records": row["records"],
                        }
                        for row in by_project
                    ]
                else:
                    by_project = [{**row, "project_name": None} for row in by_project]
            except Exception:
                by_project = [{**row, "project_name": None} for row in by_project]

            by_milestone = _breakout("milestone_id")
            by_task = _breakout("task_id")
            by_skill = _breakout("skill_id")
            by_agent = _breakout("agent_id")

        finally:
            conn.close()

        return {
            "schema": "dream_studio.attribution_breakouts.v1",
            "total_tokens": total_tokens,
            "total_records": total_records,
            "by_project": by_project,
            "by_milestone": by_milestone,
            "by_task": by_task,
            "by_skill": by_skill,
            "by_agent": by_agent,
            "data_status": "ok" if total_records > 0 else "empty",
            "generated_at": datetime.now().isoformat(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error computing attribution breakouts: {exc}")
