"""Pydantic models for metrics endpoints"""
from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional
from datetime import datetime


class MetricsQuery(BaseModel):
    """Query parameters for metrics endpoints"""
    days: int = Field(default=30, ge=1, le=365, description="Number of days to analyze")
    project: Optional[str] = Field(default=None, description="Filter by project")
    skill: Optional[str] = Field(default=None, description="Filter by skill")
    model: Optional[str] = Field(default=None, description="Filter by model")


class SessionMetrics(BaseModel):
    """Session metrics response"""
    total_sessions: int
    outcomes: Dict[str, int]
    avg_duration_minutes: float
    by_project: Dict[str, int]
    timeline: List[Dict[str, Any]]
    day_of_week: Dict[str, int]
    success_rate: float = 0.0


class SkillMetrics(BaseModel):
    """Skill metrics response"""
    total_invocations: int
    unique_skills: int
    overall_success_rate: float
    by_skill: Dict[str, Dict[str, Any]]
    top_skills: List[Dict[str, Any]]
    failures: List[Dict[str, Any]]


class TokenMetrics(BaseModel):
    """Token metrics response"""
    total_tokens: int
    input_tokens: int
    output_tokens: int
    cache_hits: int
    total_cost_usd: float
    by_model: Dict[str, Dict[str, Any]]
    by_project: Dict[str, Dict[str, Any]]
    daily_average: float
    timeline: List[Dict[str, Any]]


class ModelMetrics(BaseModel):
    """Model metrics response"""
    total_invocations: int
    by_model: Dict[str, Dict[str, Any]]
    distribution_pct: Dict[str, float]
    success_rates: Dict[str, float]
    performance_rank: List[str]


class LessonMetrics(BaseModel):
    """Lesson metrics response"""
    total_lessons: int
    by_source: Dict[str, int]
    by_status: Dict[str, int]
    by_confidence: Dict[str, int]
    capture_rate: float
    promoted_count: int
    recent_lessons: List[Dict[str, Any]]


class WorkflowMetrics(BaseModel):
    """Workflow metrics response"""
    total_workflows: int
    by_workflow: Dict[str, Dict[str, Any]]
    overall_success_rate: float
    by_status: Dict[str, int]
    avg_completion_time_minutes: float
    total_nodes: int


class AllMetricsResponse(BaseModel):
    """Combined metrics response"""
    sessions: SessionMetrics
    skills: SkillMetrics
    tokens: TokenMetrics
    models: ModelMetrics
    lessons: LessonMetrics
    workflows: WorkflowMetrics
    generated_at: datetime
    query_params: MetricsQuery


class MetricsError(BaseModel):
    """Error response"""
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None
