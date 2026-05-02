"""API models - Pydantic schemas for request/response validation"""

from .metrics import (
    MetricsQuery,
    SessionMetrics,
    SkillMetrics,
    TokenMetrics,
    ModelMetrics,
    LessonMetrics,
    WorkflowMetrics,
    AllMetricsResponse,
    MetricsError
)

from .insights import (
    InsightItem,
    InsightsResponse,
    RootCauseAnalysis,
    Recommendation,
    RecommendationsResponse,
    HighPriorityInsight,
    HighPriorityResponse
)

from .reports import (
    ReportType,
    ReportFormat,
    ReportCreate,
    ReportUpdate,
    Report,
    ReportContent,
    ReportList,
    ExportRequest,
    ExportResponse
)

__all__ = [
    # Metrics
    "MetricsQuery",
    "SessionMetrics",
    "SkillMetrics",
    "TokenMetrics",
    "ModelMetrics",
    "LessonMetrics",
    "WorkflowMetrics",
    "AllMetricsResponse",
    "MetricsError",
    # Insights
    "InsightItem",
    "InsightsResponse",
    "RootCauseAnalysis",
    "Recommendation",
    "RecommendationsResponse",
    "HighPriorityInsight",
    "HighPriorityResponse",
    # Reports
    "ReportType",
    "ReportFormat",
    "ReportCreate",
    "ReportUpdate",
    "Report",
    "ReportContent",
    "ReportList",
    "ExportRequest",
    "ExportResponse"
]
