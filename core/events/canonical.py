"""
Canonical Event Schema Models

These models define the interface between the system and analytics/storage.
All models are standalone with zero external dependencies beyond Pydantic.

Migrated from projections.models.events during system unification (2026-05-07).
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class CanonicalEvent(BaseModel):
    """Base event structure for all canonical events."""

    activity_id: str = Field(..., description="Unique identifier for this event")
    activity_type: str = Field(
        ..., description="Type of activity (e.g., 'hook.executed', 'security.scan')"
    )
    event_timestamp: datetime = Field(..., description="When the event occurred")
    severity: str = Field(..., description="Severity level: info, warning, error, critical")
    stream_type: str = Field(
        ..., description="Event stream category: hook, security, workflow, etc."
    )
    stream_id: str = Field(..., description="Identifier for the specific stream instance")
    event_data: dict = Field(
        default_factory=dict, description="Type-specific event payload as JSON"
    )


class ActivityLog(BaseModel):
    """Database representation of canonical events (maps to activity_log table)."""

    activity_id: str = Field(..., description="Unique identifier for this event")
    activity_type: str = Field(..., description="Type of activity")
    event_timestamp: datetime = Field(..., description="When the event occurred")
    severity: str = Field(..., description="Severity level: info, warning, error, critical")
    stream_type: str = Field(..., description="Event stream category")
    stream_id: str = Field(..., description="Stream instance identifier")
    event_data: dict = Field(default_factory=dict, description="Event payload as JSON")


class HookExecution(BaseModel):
    """Hook-specific event data."""

    hook_name: str = Field(..., description="Name of the hook that executed")
    execution_id: str = Field(..., description="Unique identifier for this execution")
    duration_ms: float = Field(..., description="Execution duration in milliseconds")
    status: str = Field(..., description="Execution status: success, failed, timeout")
    exit_code: int = Field(..., description="Process exit code (0 = success)")
    event_timestamp: datetime = Field(..., description="When the hook executed")


class SecurityFinding(BaseModel):
    """Security scan finding/vulnerability."""

    finding_id: str = Field(..., description="Unique identifier for this finding")
    source_type: str = Field(..., description="Finding source: sarif, cve, manual, hook_check")
    severity: str = Field(..., description="Severity level: info, low, medium, high, critical")
    file_path: Optional[str] = Field(None, description="File path where finding was detected")
    line_number: Optional[int] = Field(None, description="Line number in file (if applicable)")
    message: str = Field(..., description="Human-readable description of the finding")
    status: str = Field(..., description="Finding status: open, triaged, fixed, ignored")
    created_at: datetime = Field(..., description="When the finding was created")
