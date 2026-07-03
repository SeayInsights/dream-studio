"""Canonical event emission for eval runs (WO-DBA-EVAL-DECISION).

Eval runs are events attached to business entities, not private table rows.
Emission goes through the spool → ingestor path (Rule 4: the ingestor is the
sole canonical-event writer). Best-effort: spool failures never fail the run.
"""

from __future__ import annotations

from typing import Any


def emit_eval_run_event(
    payload: dict[str, Any],
    *,
    timestamp: str | None = None,
    work_order_id: str | None = None,
    hook_id: str | None = None,
) -> None:
    try:
        import spool.writer as _spool_writer

        from canonical.events.envelope import CanonicalEventEnvelope

        trace: dict[str, Any] = {"domain": "telemetry", "attribution_status": "fully_attributed"}
        if work_order_id:
            trace["work_order_id"] = work_order_id
        if hook_id:
            trace["hook_id"] = hook_id

        kwargs: dict[str, Any] = {}
        if timestamp:
            kwargs["timestamp"] = timestamp
        envelope = CanonicalEventEnvelope(
            event_type="eval.run.completed",
            session_id=None,
            payload=payload,
            severity="info",
            trace=trace,
            **kwargs,
        )
        _spool_writer.write_event(envelope.to_dict())
    except Exception:
        return
