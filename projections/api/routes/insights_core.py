"""Core insights endpoints: all/strengths/issues/opportunities/risks,
high-priority, recommendations, and root-cause analysis.

WO-GF-API-ROUTES: split out of insights.py.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, Query

from ..models.insights import (
    InsightsResponse,
    RecommendationsResponse,
    HighPriorityResponse,
    RootCauseAnalysis,
)
from projections.core.insights import InsightEngine, RootCauseAnalyzer, RecommendationEngine

from .insights_router import router
from .insights_shared import analyze_metrics, collect_metrics


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
