"""Metrics API routes"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime

from ..models.metrics import (
    MetricsQuery,
    AllMetricsResponse,
    SessionMetrics,
    SkillMetrics,
    TokenMetrics,
    ModelMetrics,
    LessonMetrics,
    WorkflowMetrics
)
from analytics.core.collectors import (
    SessionCollector,
    SkillCollector,
    TokenCollector,
    ModelCollector,
    LessonCollector,
    WorkflowCollector
)

router = APIRouter()


def get_db_path() -> str:
    """Get database path - could be from env or config"""
    import os
    return os.path.expanduser("~/.dream-studio/state/studio.db")


@router.get("/", response_model=AllMetricsResponse)
async def get_all_metrics(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
    project: Optional[str] = Query(default=None, description="Filter by project"),
    skill: Optional[str] = Query(default=None, description="Filter by skill"),
    model: Optional[str] = Query(default=None, description="Filter by model")
):
    """Get all metrics combined"""
    try:
        db_path = get_db_path()

        # Initialize collectors
        session_collector = SessionCollector(db_path)
        skill_collector = SkillCollector(db_path)
        token_collector = TokenCollector(db_path)
        model_collector = ModelCollector(db_path)
        lesson_collector = LessonCollector(db_path)
        workflow_collector = WorkflowCollector(db_path)

        # Collect all metrics
        sessions_data = session_collector.collect(days=days)
        skills_data = skill_collector.collect(days=days)
        tokens_data = token_collector.collect(days=days)
        models_data = model_collector.collect(days=days)
        lessons_data = lesson_collector.collect(days=days)
        workflows_data = workflow_collector.collect(days=days)

        # Map workflow collector fields to Pydantic model fields
        workflows_mapped = {
            "total_workflows": workflows_data["total_runs"],
            "by_workflow": workflows_data["by_workflow"],
            "overall_success_rate": workflows_data["success_rate"],
            "by_status": workflows_data["by_status"],
            "avg_completion_time_minutes": workflows_data["avg_completion_time_minutes"],
            "total_nodes": workflows_data["total_nodes_executed"]
        }

        # Build response
        return AllMetricsResponse(
            sessions=SessionMetrics(**sessions_data),
            skills=SkillMetrics(**skills_data),
            tokens=TokenMetrics(**tokens_data),
            models=ModelMetrics(**models_data),
            lessons=LessonMetrics(**lessons_data),
            workflows=WorkflowMetrics(**workflows_mapped),
            generated_at=datetime.now(),
            query_params=MetricsQuery(days=days, project=project, skill=skill, model=model)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error collecting metrics: {str(e)}")


@router.get("/sessions", response_model=SessionMetrics)
async def get_session_metrics(days: int = Query(default=30, ge=1, le=365)):
    """Get session metrics"""
    try:
        db_path = get_db_path()
        collector = SessionCollector(db_path)
        data = collector.collect(days=days)
        return SessionMetrics(**data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error collecting session metrics: {str(e)}")


@router.get("/skills")
async def get_skill_metrics(days: int = Query(default=30, ge=1, le=365)):
    """Get skill metrics with dashboard-friendly format"""
    try:
        db_path = get_db_path()
        collector = SkillCollector(db_path)
        data = collector.collect(days=days)

        # Transform to dashboard format
        leaderboard = []
        for skill_name, skill_data in data.get('by_skill', {}).items():
            avg_exec_s = skill_data.get('avg_exec_time_s', 0)
            avg_duration_minutes = avg_exec_s / 60 if avg_exec_s else 0

            # Estimate cost based on tokens (very rough estimate)
            input_tok = skill_data.get('avg_input_tokens', 0)
            output_tok = skill_data.get('avg_output_tokens', 0)
            # Rough estimate: $0.003/1K input, $0.015/1K output (Sonnet-like pricing)
            avg_cost = (input_tok / 1000 * 0.003) + (output_tok / 1000 * 0.015)

            leaderboard.append({
                'skill_name': skill_name,
                'invocations': skill_data.get('count', 0),
                'success_rate': skill_data.get('success_rate', 0) / 100,  # Convert to 0-1 range
                'avg_exec_time_s': avg_exec_s,
                'avg_duration_minutes': avg_duration_minutes,
                'avg_cost': avg_cost,
                'avg_input_tokens': input_tok,
                'avg_output_tokens': output_tok
            })

        # Get most used skill
        most_used_skill = data.get('top_skills', [{}])[0].get('skill_name', 'N/A') if data.get('top_skills') else 'N/A'
        most_used_count = data.get('top_skills', [{}])[0].get('count', 0) if data.get('top_skills') else 0

        return {
            **data,
            'leaderboard': leaderboard,
            'most_used_skill': most_used_skill,
            'most_used_count': most_used_count,
            'recent_failures': data.get('failures', []),
            'success_trend': [],  # TODO: Add timeline data
            'heatmap': []  # TODO: Add heatmap data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error collecting skill metrics: {str(e)}")


@router.get("/tokens")
async def get_token_metrics(days: int = Query(default=30, ge=1, le=365)):
    """Get token usage metrics with dashboard-friendly format"""
    try:
        db_path = get_db_path()
        collector = TokenCollector(db_path)
        data = collector.collect(days=days)

        # Calculate cache hit rate (placeholder for now)
        cache_hit_rate = data.get('cache_hits', 0) / max(data.get('total_tokens', 1), 1)

        return {
            **data,
            'total_cost': data.get('total_cost_usd', 0),
            'cache_hit_rate': cache_hit_rate
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error collecting token metrics: {str(e)}")


@router.get("/models")
async def get_model_metrics(days: int = Query(default=30, ge=1, le=365)):
    """Get model usage metrics with dashboard-friendly format"""
    try:
        db_path = get_db_path()
        collector = ModelCollector(db_path)
        data = collector.collect(days=days)

        # Transform distribution for pie chart
        distribution = []
        for model, percentage in data.get('distribution_pct', {}).items():
            distribution.append({
                'model': model,
                'percentage': percentage
            })

        return {
            **data,
            'distribution': distribution
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error collecting model metrics: {str(e)}")


@router.get("/lessons", response_model=LessonMetrics)
async def get_lesson_metrics(days: int = Query(default=30, ge=1, le=365)):
    """Get lesson capture metrics"""
    try:
        db_path = get_db_path()
        collector = LessonCollector(db_path)
        data = collector.collect(days=days)
        # Collector returns correct field names - no mapping needed
        return LessonMetrics(**data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error collecting lesson metrics: {str(e)}")


@router.get("/workflows", response_model=WorkflowMetrics)
async def get_workflow_metrics(days: int = Query(default=30, ge=1, le=365)):
    """Get workflow metrics"""
    try:
        db_path = get_db_path()
        collector = WorkflowCollector(db_path)
        data = collector.collect(days=days)

        # Map WorkflowCollector field names to WorkflowMetrics field names
        mapped_data = {
            "total_workflows": data["total_runs"],
            "by_workflow": data["by_workflow"],
            "overall_success_rate": data["success_rate"],
            "by_status": data["by_status"],
            "avg_completion_time_minutes": data["avg_completion_time_minutes"],
            "total_nodes": data["total_nodes_executed"]
        }

        return WorkflowMetrics(**mapped_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error collecting workflow metrics: {str(e)}")
