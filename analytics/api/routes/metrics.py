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
    return os.path.expanduser("~/.dream-studio/studio.db")


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


@router.get("/skills", response_model=SkillMetrics)
async def get_skill_metrics(days: int = Query(default=30, ge=1, le=365)):
    """Get skill metrics"""
    try:
        db_path = get_db_path()
        collector = SkillCollector(db_path)
        data = collector.collect(days=days)
        return SkillMetrics(**data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error collecting skill metrics: {str(e)}")


@router.get("/tokens", response_model=TokenMetrics)
async def get_token_metrics(days: int = Query(default=30, ge=1, le=365)):
    """Get token usage metrics"""
    try:
        db_path = get_db_path()
        collector = TokenCollector(db_path)
        data = collector.collect(days=days)
        return TokenMetrics(**data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error collecting token metrics: {str(e)}")


@router.get("/models", response_model=ModelMetrics)
async def get_model_metrics(days: int = Query(default=30, ge=1, le=365)):
    """Get model usage metrics"""
    try:
        db_path = get_db_path()
        collector = ModelCollector(db_path)
        data = collector.collect(days=days)
        return ModelMetrics(**data)
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
