"""Canonical event models for the adapter layer.

Moved from interfaces/adapters/models.py (Slice 4 retirement).
TraceContext authority lives in core/events/trace.py.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from core.events.trace import TraceContext  # authoritative location since Slice 3

# Re-export TraceContext so callers that used to import it from here still work.
__all__ = ["CanonicalEvent", "SeverityLevel", "TraceContext"]

SeverityLevel = Literal["info", "low", "medium", "high", "critical"]


@dataclass
class CanonicalEvent:
    """Standardized event schema for the legacy adapter normalization layer.

    Used by studio_db.py for skill execution normalization (TC-007).
    Not the same schema as canonical/events/envelope.py CanonicalEventEnvelope,
    which is the spool-pipeline event schema.
    """

    event_id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = ""
    entity_type: str = ""
    entity_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    severity: SeverityLevel = "info"
    payload: dict[str, Any] = field(default_factory=dict)
    trace: TraceContext = field(default_factory=TraceContext)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
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
        if not self.event_id:
            raise ValueError("event_id is required and cannot be empty")
        if not self.event_type:
            raise ValueError("event_type is required and cannot be empty")
        valid_severities = {"info", "low", "medium", "high", "critical"}
        if self.severity not in valid_severities:
            raise ValueError(
                f"Invalid severity: {self.severity!r}. Must be one of {valid_severities}"
            )
