"""
Canonical event models for the adapter layer.

These models define the ONLY coupling between Data, Control, and Analytics planes.
Changes to these schemas require coordinated updates across all three planes.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

# Type alias for severity levels (enables type checking and IDE autocomplete)
SeverityLevel = Literal["info", "low", "medium", "high", "critical"]


@dataclass
class TraceContext:
    """
    Execution trace metadata for event correlation.

    Links events to their originating context (project, task, session).
    Used for: cross-plane analysis, debugging, audit trails.
    """

    project_id: str | None = None
    task_id: str | None = None
    prd_id: str | None = None
    session_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "project_id": self.project_id,
            "task_id": self.task_id,
            "prd_id": self.prd_id,
            "session_id": self.session_id,
        }


@dataclass
class CanonicalEvent:
    """
    Standardized event schema across all planes.

    This is the SINGLE SOURCE OF TRUTH for event structure.
    All AI/model outputs MUST be normalized to this schema before writing to activity_log.

    Fields:
        event_id: Unique event identifier (UUID4)
        event_type: Event category (e.g., "skill.completed", "security.finding.created")
        entity_type: Primary entity type (e.g., "skill_execution", "hook_execution")
        entity_id: ID of the primary entity
        timestamp: Event occurrence time (UTC)
        severity: Event severity level
        payload: Model-specific flexible data (JSON-serializable dict)
        trace: Execution trace context (project/task/session)
        metadata: Adapter metadata (version, model, etc.)

    Severity levels:
        - "info": Informational events
        - "low": Low-impact events
        - "medium": Medium-impact events
        - "high": High-impact events (requires attention)
        - "critical": Critical events (requires immediate action)
    """

    event_id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = ""
    entity_type: str = ""
    entity_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    severity: SeverityLevel = "info"
    payload: dict[str, Any] = field(
        default_factory=dict
    )  # WARNING: Do not include sensitive data (API keys, credentials, PII)
    trace: TraceContext = field(default_factory=TraceContext)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for activity_log insertion.

        Returns:
            Dictionary with all fields serialized (ISO timestamps, nested dicts).
        """
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity,
            "payload": self.payload,
            "trace": self.trace.to_dict(),
            "metadata": self.metadata,
        }

    def validate(self) -> None:
        """
        Validate required fields and constraints.

        Raises:
            ValueError: If any validation fails (with specific error message).
        """
        if not self.event_id:
            raise ValueError("event_id is required and cannot be empty")
        if not self.event_type:
            raise ValueError("event_type is required and cannot be empty")

        valid_severities = {"info", "low", "medium", "high", "critical"}
        if self.severity not in valid_severities:
            raise ValueError(
                f"Invalid severity: {self.severity!r}. Must be one of {valid_severities}"
            )
