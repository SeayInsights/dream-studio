"""Pydantic models for insights endpoints"""

from pydantic import BaseModel, Field
from typing import Any


class InsightItem(BaseModel):
    """Individual insight"""

    category: str
    title: str
    description: str
    impact: str | None = None
    severity: str | None = None
    risk_level: str | None = None
    potential_impact: str | None = None
    evidence: dict[str, Any]
    recommended_action: str | None = None
    mitigation: str | None = None


class InsightsResponse(BaseModel):
    """Complete insights response"""

    strengths: list[InsightItem]
    issues: list[InsightItem]
    opportunities: list[InsightItem]
    risks: list[InsightItem]
    summary: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    generated_at: str


class RootCauseAnalysis(BaseModel):
    """Root cause analysis response"""

    issue: InsightItem
    probable_causes: list[dict[str, Any]]
    correlations: dict[str, str]
    confidence: float = Field(ge=0.0, le=1.0)
    recommendations: list[str]


class Recommendation(BaseModel):
    """Single recommendation"""

    title: str
    category: str
    priority: str
    impact: str
    effort: str
    source: str
    details: str | None = None


class RecommendationsResponse(BaseModel):
    """Recommendations response"""

    recommendations: list[Recommendation]
    quick_wins: list[Recommendation]
    grouped: dict[str, list[Recommendation]]
    executive_summary: str


class HighPriorityInsight(BaseModel):
    """High priority insight item"""

    type: str  # "issue", "strength", "risk"
    category: str
    title: str
    description: str
    severity: str | None = None
    impact: str | None = None
    risk_level: str | None = None
    evidence: dict[str, Any]


class HighPriorityResponse(BaseModel):
    """High priority insights response"""

    high_priority: list[HighPriorityInsight]
    count: int
    generated_at: str
