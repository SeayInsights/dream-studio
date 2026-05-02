"""Insights API routes"""
from fastapi import APIRouter, HTTPException, Query
from datetime import datetime

from ..models.insights import (
    InsightsResponse,
    RecommendationsResponse,
    HighPriorityResponse,
    RootCauseAnalysis
)
from analytics.core.collectors import (
    SessionCollector,
    SkillCollector,
    TokenCollector,
    ModelCollector,
    LessonCollector,
    WorkflowCollector
)
from analytics.core.analyzers import (
    PerformanceAnalyzer,
    TrendAnalyzer,
    AnomalyDetector,
    Predictor
)
from analytics.core.insights import (
    InsightEngine,
    RootCauseAnalyzer,
    RecommendationEngine
)

router = APIRouter()


def get_db_path() -> str:
    """Get database path"""
    import os
    return os.path.expanduser("~/.dream-studio/state/studio.db")


def collect_metrics(days: int = 30):
    """Collect all metrics"""
    db_path = get_db_path()

    collectors = {
        "sessions": SessionCollector(db_path),
        "skills": SkillCollector(db_path),
        "tokens": TokenCollector(db_path),
        "models": ModelCollector(db_path),
        "lessons": LessonCollector(db_path),
        "workflows": WorkflowCollector(db_path)
    }

    metrics = {
        key: collector.collect(days=days)
        for key, collector in collectors.items()
    }

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
        anomaly_results = anomaly_detector.comprehensive_anomaly_scan(metrics["sessions"]["timeline"])
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
            "generated_at": insights["generated_at"]
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
            "generated_at": insights["generated_at"]
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
            "generated_at": insights["generated_at"]
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
            "generated_at": insights["generated_at"]
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
            generated_at=datetime.now().isoformat()
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting high priority insights: {str(e)}")


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
            executive_summary=executive_summary
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating recommendations: {str(e)}")


@router.post("/root-cause", response_model=RootCauseAnalysis)
async def analyze_root_cause(
    issue_index: int = Query(description="Index of issue to analyze"),
    days: int = Query(default=30, ge=1, le=365)
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
    import sqlite3
    from collections import defaultdict

    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        # Heatmap: 7 days x 24 hours
        cursor.execute("""
            SELECT
                CAST(strftime('%w', started_at) AS INTEGER) as dow,
                CAST(strftime('%H', started_at) AS INTEGER) as hour,
                COUNT(*) as count
            FROM raw_sessions
            WHERE started_at >= ?
            GROUP BY dow, hour
        """, (cutoff,))

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
        cursor.execute("""
            SELECT
                CAST(strftime('%H', started_at) AS INTEGER) as hour,
                COUNT(*) as total,
                SUM(CASE WHEN outcome = 'completed' THEN 1 ELSE 0 END) as completed
            FROM raw_sessions
            WHERE started_at >= ?
            GROUP BY hour
        """, (cutoff,))
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
            "generated_at": datetime.now().isoformat()
        }
    finally:
        conn.close()
