"""Security event emission for canonical_events.

Routes all security events through the canonical spool pipeline (Slice 3),
ensuring consistent validation, persistence, and criticality handling.

Note: emission flows through the spool pipeline, not direct to SQLite.
"""

import logging
from typing import Any

from canonical.events.envelope import CanonicalEventEnvelope
from canonical.events.redactor import redact_file_path
from emitters.shared.spool_writer import write_envelopes

logger = logging.getLogger(__name__)


def emit_security_event(
    event_type: str,
    payload: dict[str, Any],
    severity: str = "info",
    conn=None,
    validate: bool = True,
) -> str | None:
    """Emit security event through canonical spool pipeline.

    Args:
        event_type: Event type suffix (will be prefixed with 'security.')
        payload: Event payload data
        severity: Event severity (info, low, medium, high, critical)
        conn: Ignored — retained for call-site compatibility
        validate: Ignored — canonical path always validates
    """
    full_event_type = f"security.{event_type}"

    envelope = CanonicalEventEnvelope(
        event_type=full_event_type,
        session_id=None,
        payload=payload,
        severity=severity,
        confidence="unavailable",
        project_id=None,
        trace={"source": "security_scanner"},
    )
    write_envelopes([envelope])
    return envelope.event_id


def emit_scan_started(scan_id: str, prd_id: str, project_path: str, conn=None):
    """Emit scan started event."""
    emit_security_event(
        "scan.started",
        {"scan_id": scan_id, "prd_id": prd_id, "project_path": redact_file_path(project_path)},
        conn=conn,
    )


def emit_scan_completed(
    scan_id: str,
    findings_count: int,
    duration_seconds: float = None,
    severity_breakdown: dict = None,
    scan_coverage: dict = None,
    suppression_count: int = 0,
    conn=None,
):
    """Emit scan completed event with enriched metrics."""
    payload = {
        "scan_id": scan_id,
        "findings_count": findings_count,
        "duration_seconds": duration_seconds,
        "suppression_count": suppression_count,
    }

    if severity_breakdown:
        payload.update(
            {
                "critical_count": severity_breakdown.get("CRITICAL", 0),
                "high_count": severity_breakdown.get("HIGH", 0),
                "medium_count": severity_breakdown.get("MEDIUM", 0),
                "low_count": severity_breakdown.get("LOW", 0),
                "info_count": severity_breakdown.get("INFO", 0),
            }
        )

    if scan_coverage:
        payload.update(scan_coverage)

    emit_security_event("scan.completed", payload, conn=conn)


def emit_scan_failed(scan_id: str, error: str, conn=None):
    """Emit scan failed event."""
    emit_security_event(
        "scan.failed", {"scan_id": scan_id, "error": error}, severity="high", conn=conn
    )
