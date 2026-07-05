"""Pydantic models for metrics endpoints"""

from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime


class MetricsQuery(BaseModel):
    """Query parameters for metrics endpoints"""

    days: int = Field(default=30, ge=1, le=365, description="Number of days to analyze")
    project: str | None = Field(default=None, description="Filter by project")
    skill: str | None = Field(default=None, description="Filter by skill")
    model: str | None = Field(default=None, description="Filter by model")


class SessionMetrics(BaseModel):
    """Session metrics response"""

    total_sessions: int
    outcomes: dict[str, int]
    avg_duration_minutes: float
    by_project: dict[str, int]
    timeline: list[dict[str, Any]]
    day_of_week: dict[str, int]
    success_rate: float = 0.0


class SkillMetrics(BaseModel):
    """Skill metrics response"""

    total_invocations: int
    unique_skills: int
    overall_success_rate: float
    by_skill: dict[str, dict[str, Any]]
    top_skills: list[dict[str, Any]]
    failures: list[dict[str, Any]]


class TokenMetrics(BaseModel):
    """Token metrics response"""

    total_tokens: int
    input_tokens: int
    output_tokens: int
    cache_hits: int
    total_cost_usd: float | None = None
    by_model: dict[str, dict[str, Any]]
    by_project: dict[str, dict[str, Any]]
    daily_average: float
    timeline: list[dict[str, Any]]


class ModelMetrics(BaseModel):
    """Model metrics response"""

    total_invocations: int
    by_model: dict[str, dict[str, Any]]
    distribution_pct: dict[str, float]
    success_rates: dict[str, float]
    performance_rank: list[str]


class LessonMetrics(BaseModel):
    """Lesson metrics response"""

    total_lessons: int
    by_source: dict[str, int]
    by_status: dict[str, int]
    by_confidence: dict[str, int]
    capture_rate: float
    promoted_count: int
    recent_lessons: list[dict[str, Any]]


class WorkflowMetrics(BaseModel):
    """Workflow metrics response"""

    total_workflows: int
    by_workflow: dict[str, dict[str, Any]]
    overall_success_rate: float
    by_status: dict[str, int]
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
    details: dict[str, Any] | None = None
