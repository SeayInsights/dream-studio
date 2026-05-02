"""Pydantic models for insights endpoints"""
from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional
from datetime import datetime


class InsightItem(BaseModel):
    """Individual insight"""
    category: str
    title: str
    description: str
    impact: Optional[str] = None
    severity: Optional[str] = None
    risk_level: Optional[str] = None
    potential_impact: Optional[str] = None
    evidence: Dict[str, Any]
    recommended_action: Optional[str] = None
    mitigation: Optional[str] = None


class InsightsResponse(BaseModel):
    """Complete insights response"""
    strengths: List[InsightItem]
    issues: List[InsightItem]
    opportunities: List[InsightItem]
    risks: List[InsightItem]
    summary: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    generated_at: str


class RootCauseAnalysis(BaseModel):
    """Root cause analysis response"""
    issue: InsightItem
    probable_causes: List[Dict[str, Any]]
    correlations: Dict[str, str]
    confidence: float = Field(ge=0.0, le=1.0)
    recommendations: List[str]


class Recommendation(BaseModel):
    """Single recommendation"""
    title: str
    category: str
    priority: str
    impact: str
    effort: str
    source: str
    details: Optional[str] = None


class RecommendationsResponse(BaseModel):
    """Recommendations response"""
    recommendations: List[Recommendation]
    quick_wins: List[Recommendation]
    grouped: Dict[str, List[Recommendation]]
    executive_summary: str


class HighPriorityInsight(BaseModel):
    """High priority insight item"""
    type: str  # "issue", "strength", "risk"
    category: str
    title: str
    description: str
    severity: Optional[str] = None
    impact: Optional[str] = None
    risk_level: Optional[str] = None
    evidence: Dict[str, Any]


class HighPriorityResponse(BaseModel):
    """High priority insights response"""
    high_priority: List[HighPriorityInsight]
    count: int
    generated_at: str
