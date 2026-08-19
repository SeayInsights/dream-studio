"""Gate-bypass event emission (WO-BYPASS-TELEMETRY).

Every gate escape hatch leaves a mark: acknowledgment env vars
(MIGRATION_RISK_ACKNOWLEDGED), review-trailer consumption
(Docs-Reviewed-No-Change), and force-closes all record a ``gate.bypassed``
canonical event so ``ds doctor`` / ``ds project state`` can answer "which
hatches fired, and how often". Best-effort by contract — a broken emit path
never changes a gate outcome.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def record_gate_bypass(gate: str, reason: str, extra: dict[str, Any] | None = None) -> None:
    """Emit a ``gate.bypassed`` spool event for a non-force gate escape hatch.

    Mirrors the force-close emission in ``close_main`` (same event type, same
    business-canonical routing) so ``bypass_report`` aggregates both families.
    """
    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        payload: dict[str, Any] = {"gate": gate, "reason": reason}
        if extra:
            payload.update(extra)
        envelope = CanonicalEventEnvelope(
            event_type="gate.bypassed",
            session_id=None,
            payload=payload,
            timestamp=datetime.now(UTC).isoformat(),
            severity="warning",
            trace={"domain": "sdlc", "attribution_status": "unattributed"},
        )
        _spool_writer.write_event(envelope.to_dict())
    except Exception:
        pass  # never let telemetry change a gate outcome
