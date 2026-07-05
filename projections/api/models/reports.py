"""Pydantic models for reports endpoints"""

from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime
from enum import Enum

RAW_PRIVATE_EXPORT_SOURCES = frozenset(
    {
        "memory_entries",
        "raw_sessions",
        "raw_token_usage",
        "validation_failures",
        "canonical_events",
        "canonical_events.payload",
        "raw_handoffs",
        "prd_handoffs",
        "handoff_content",
        "session_content",
    }
)

ALLOWED_PRIVATE_EXPORT_CLASSIFICATIONS = frozenset({"redacted", "aggregate"})
DERIVED_EXPORT_CLASSIFICATION = "derived_projection_snapshot"


class ExportPrivacyError(ValueError):
    """Raised when an export request would expose raw private local state."""


def _normalize_export_source(source: str) -> str:
    return source.strip().lower()


def _private_sources_in(sources: list[str] | None) -> list[str]:
    private_sources: list[str] = []
    for source in sources or []:
        normalized = _normalize_export_source(source)
        root = normalized.split(".", 1)[0]
        if normalized in RAW_PRIVATE_EXPORT_SOURCES or root in RAW_PRIVATE_EXPORT_SOURCES:
            private_sources.append(normalized)
    return sorted(set(private_sources))


def classify_export_privacy(
    *,
    include_raw_data: bool = False,
    sources: list[str] | None = None,
    redaction_classification: str | None = None,
) -> dict[str, Any]:
    """Classify an export/report request before any file is produced.

    Raw local runtime state can only pass this gate when the caller explicitly
    names a redacted or aggregate classification. The helper does not redact
    data itself; it prevents accidental raw export paths.
    """
    normalized_classification = (
        redaction_classification.strip().lower() if redaction_classification else None
    )
    private_sources = _private_sources_in(sources)
    requires_redaction = include_raw_data or bool(private_sources)

    if (
        requires_redaction
        and normalized_classification not in ALLOWED_PRIVATE_EXPORT_CLASSIFICATIONS
    ):
        blocked = ["include_raw_data"] if include_raw_data else []
        blocked.extend(private_sources)
        raise ExportPrivacyError(
            "Raw/private export sources require an explicit redacted or aggregate "
            f"classification before export: {', '.join(sorted(set(blocked)))}"
        )

    classification = normalized_classification or DERIVED_EXPORT_CLASSIFICATION
    return {
        "classification": classification,
        "include_raw_data": include_raw_data,
        "private_sources": private_sources,
        "redaction_required": requires_redaction,
    }


def validate_export_payload(data: dict[str, Any]) -> None:
    """Reject direct exporter payloads that contain raw private source keys."""
    discovered: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = _normalize_export_source(str(key))
                root = normalized.split(".", 1)[0]
                if normalized in RAW_PRIVATE_EXPORT_SOURCES or root in RAW_PRIVATE_EXPORT_SOURCES:
                    discovered.append(normalized)
                visit(child)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(data)
    private_sources = sorted(set(discovered))
    if private_sources:
        raise ExportPrivacyError(
            "Exporter payload contains raw/private local state keys without an "
            f"explicit redaction gate: {', '.join(private_sources)}"
        )


class ReportType(str, Enum):
    """Report types"""

    EXECUTIVE = "executive"
    DETAILED = "detailed"
    TECHNICAL = "technical"
    CUSTOM = "custom"


class ReportFormat(str, Enum):
    """Export formats"""

    PDF = "pdf"
    EXCEL = "excel"
    PPTX = "pptx"
    CSV = "csv"
    CSV_ZIP = "csv_zip"
    POWERBI = "powerbi"
    JSON = "json"
    HTML = "html"


class ReportCreate(BaseModel):
    """Create report request"""

    name: str = Field(min_length=1, max_length=200)
    type: ReportType
    description: str | None = None
    days: int = Field(default=30, ge=1, le=365)
    filters: dict[str, Any] | None = None
    sections: list[str] | None = None  # Which sections to include


class ReportUpdate(BaseModel):
    """Update report request"""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    filters: dict[str, Any] | None = None
    sections: list[str] | None = None


class Report(BaseModel):
    """Report metadata"""

    id: str
    name: str
    type: ReportType
    description: str | None
    days: int
    filters: dict[str, Any]
    sections: list[str]
    created_at: datetime
    updated_at: datetime
    generated_count: int = 0


class ReportContent(BaseModel):
    """Full report content"""

    id: str
    name: str
    type: ReportType
    metadata: dict[str, Any]
    metrics: dict[str, Any]
    insights: dict[str, Any]
    recommendations: list[dict[str, Any]]
    charts: list[dict[str, Any]] | None = None
    generated_at: datetime


class ReportList(BaseModel):
    """List of reports"""

    reports: list[Report]
    total: int
    page: int = 1
    page_size: int = 50


class ExportRequest(BaseModel):
    """Export request"""

    report_id: str | None = None
    format: ReportFormat
    include_charts: bool = True
    include_raw_data: bool = False
    sources: list[str] = Field(default_factory=list)
    redaction_classification: str | None = None


class ExportResponse(BaseModel):
    """Export response"""

    export_id: str
    format: ReportFormat
    status: str  # "processing", "complete", "failed"
    download_url: str | None = None
    expires_at: datetime | None = None
    file_size_bytes: int | None = None
    privacy_classification: str | None = None
