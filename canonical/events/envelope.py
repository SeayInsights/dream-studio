from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

SCHEMA_VERSION = 1


@dataclass
class CanonicalEventEnvelope:
    event_type: str
    session_id: str | None
    payload: dict[str, Any]

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    schema_version: int = SCHEMA_VERSION

    severity: str = "info"
    confidence: str = "exact"
    project_id: str | None = None
    trace: dict[str, Any] = field(default_factory=dict)

    # ``source_type`` is part of the canonical event JSON schema (constrained
    # to ``confirmed | inferred | weak_inference``). Default ``confirmed``
    # since CLI-emitted lifecycle events (work_order/milestone/gate/skill)
    # are first-party rather than inferred — matches what hand-built dicts
    # set before A0.
    source_type: str = "confirmed"

    raw_prompt_retained: bool = False
    raw_tool_output_retained: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "project_id": self.project_id,
            "severity": self.severity,
            "confidence": self.confidence,
            "trace": self.trace,
            "payload": self.payload,
            "source_type": self.source_type,
            "raw_prompt_retained": self.raw_prompt_retained,
            "raw_tool_output_retained": self.raw_tool_output_retained,
        }
        err = _validate_sdlc_event(d)
        if err is not None:
            try:
                from core.telemetry.diagnostics import log_diagnostic

                log_diagnostic(
                    category="failure",
                    source="canonical.events.envelope.validate",
                    context={"event_type": self.event_type, "event_id": self.event_id},
                    details={"error_message": err},
                )
            except Exception:
                pass
        return d


_VALID_ATTRIBUTION_STATUSES: frozenset[str] = frozenset(
    {"fully_attributed", "partial", "orphan", "backfill"}
)


def _validate_sdlc_event(envelope: dict[str, Any]) -> Optional[str]:
    """Validate SDLC-domain events have required attribution fields.

    Returns an error message if validation fails, None if OK.
    Non-SDLC events always pass.
    """
    trace = envelope.get("trace", {})
    if trace.get("domain") != "sdlc":
        return None

    if "attribution_status" not in trace:
        return "SDLC event missing required trace.attribution_status"

    if trace["attribution_status"] not in _VALID_ATTRIBUTION_STATUSES:
        return (
            f"Invalid attribution_status: {trace['attribution_status']!r}"
            f" (must be one of {sorted(_VALID_ATTRIBUTION_STATUSES)})"
        )

    return None


REQUIRED_FIELDS: frozenset[str] = frozenset(
    {"event_id", "event_type", "timestamp", "schema_version"}
)


def validate_envelope(d: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for f in REQUIRED_FIELDS:
        if f not in d:
            errors.append(f"missing required field: {f}")
    if "event_type" in d and not isinstance(d["event_type"], str):
        errors.append("event_type must be a string")
    if "schema_version" in d and d["schema_version"] != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if d.get("raw_prompt_retained"):
        errors.append("raw_prompt_retained must be false")
    if d.get("raw_tool_output_retained"):
        errors.append("raw_tool_output_retained must be false")
    return errors
