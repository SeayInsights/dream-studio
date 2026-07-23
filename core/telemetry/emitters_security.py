"""WO-GF-TELEMETRY-SPLIT: security finding emitters.

Extracted verbatim from core/telemetry/emitters.py (see emitters.py facade).
emit_security_finding, emit_security_finding_resolved, _severity,
_stable_security_finding_id, _int_or_none.

LANDMINE (preserve verbatim, no test edit): tests/unit/test_security_findings_writer.py
patches `spool.writer.write_event` (source-module attribute) at call time.
emit_security_finding and emit_security_finding_resolved MUST keep
`from spool.writer import write_event as _write_event` (and, in
emit_security_finding, `from canonical.events.envelope import
CanonicalEventEnvelope` + `from canonical.events.redactor import
redact_file_path as _redact`) as LAZY imports INSIDE the function body —
hoisting them to module level would break the patch target.
"""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core.telemetry.execution_spine import (
    record_execution_event,
    record_security_finding,
    resolve_security_finding,
)

from .emitters_shared import (
    MODE_BEST_EFFORT,
    TelemetryContext,
    TelemetryEmitResult,
    _context,
    _emit,
    _id,
    _refs,
    _status,
    _text,
)


def emit_security_finding(
    *,
    severity: str,
    description: str,
    category: str | None = None,
    rule_id: str | None = None,
    file_path: str | None = None,
    start_line: int | str | None = None,
    end_line: int | str | None = None,
    recommendation: str | None = None,
    status: str = "open",
    scan_id: str | None = None,
    introduced_by_agent_id: str | None = None,
    introduced_by_skill_id: str | None = None,
    introduced_by_workflow_id: str | None = None,
    introduced_by_hook_id: str | None = None,
    context: TelemetryContext | Mapping[str, Any] | None = None,
    source_refs: Sequence[str] | None = None,
    evidence_refs: Sequence[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
    db_path: Path | str | None = None,
    mode: str = MODE_BEST_EFFORT,
) -> TelemetryEmitResult:
    """Dual-write security findings with deterministic idempotency."""

    ctx = _context(context)
    normalized_severity = _severity(severity)
    normalized_status = _status(status)
    normalized_start_line = _int_or_none(start_line)
    normalized_end_line = _int_or_none(end_line) or normalized_start_line
    finding_id = _stable_security_finding_id(
        ctx=ctx,
        scan_id=scan_id,
        rule_id=rule_id,
        file_path=file_path,
        start_line=normalized_start_line,
        end_line=normalized_end_line,
        severity=normalized_severity,
    )

    def _write(conn: sqlite3.Connection) -> TelemetryEmitResult:
        existing = conn.execute(
            # findings retired migration 112 (WO-Y); dedup via security_events spine directly.
            # findings_current_status (dropped migration 140) is now a read-time
            # derivation over this same spine, never a separate lagging projection.
            "SELECT event_id FROM security_events WHERE event_id = ? AND event_kind = 'finding.recorded'",
            (finding_id,),
        ).fetchone()
        if existing is not None:
            return TelemetryEmitResult(
                False, record_id=finding_id, error="duplicate security finding skipped"
            )

        event_id = _id("security-event")
        merged_source_refs = _refs(ctx.source_refs, source_refs)
        merged_evidence_refs = _refs(ctx.evidence_refs, evidence_refs)
        event_metadata = {
            "category": category,
            "rule_id": rule_id,
            "file_path": file_path,
            "start_line": normalized_start_line,
            "end_line": normalized_end_line,
            "status": normalized_status,
            "metadata": dict(metadata or {}),
        }
        record_execution_event(
            conn,
            **ctx.scope(),
            event_id=event_id,
            event_type="security.finding_recorded",
            event_name=f"Security finding: {rule_id or category or normalized_severity}",
            actor_type="system",
            actor_id="security",
            source_refs=merged_source_refs,
            evidence_refs=merged_evidence_refs,
            metadata=event_metadata,
            outcome_status=normalized_status,
        )
        record_security_finding(
            conn,
            **ctx.scope(),
            finding_id=finding_id,
            scan_id=scan_id,
            severity=normalized_severity,
            category=category,
            rule_id=rule_id,
            file_path=file_path,
            start_line=normalized_start_line,
            end_line=normalized_end_line,
            description=description,
            recommendation=recommendation,
            status=normalized_status,
            introduced_by_agent_id=introduced_by_agent_id,
            introduced_by_skill_id=introduced_by_skill_id,
            introduced_by_workflow_id=introduced_by_workflow_id,
            introduced_by_hook_id=introduced_by_hook_id,
            evidence_refs=merged_evidence_refs,
        )
        try:
            from canonical.events.envelope import CanonicalEventEnvelope
            from canonical.events.redactor import redact_file_path as _redact
            from spool.writer import write_event as _write_event

            _envelope = CanonicalEventEnvelope(
                event_type="security.finding.logged",
                payload={
                    "finding_id": finding_id,
                    "project_id": ctx.project_id or "",
                    "severity": normalized_severity,
                    "status": normalized_status,
                    "scan_id": scan_id,
                    "rule_id": rule_id,
                    "category": category,
                    "file_path": _redact(file_path or ""),
                    "start_line": normalized_start_line,
                    "end_line": normalized_end_line,
                },
                project_id=ctx.project_id,
                session_id=None,
                confidence="high",
            )
            _write_event(_envelope.to_dict(), root=None)
        except Exception:
            pass  # fail-open; SQLite write already succeeded
        # WO-AI-SPINE (migration 139): the dashboard_attention_items write that used
        # to live here was removed — pure duplication of the execution_events row
        # above (0 production rows). Attention-worthy findings (critical/high
        # severity, or open/unresolved status) are still fully queryable via the
        # security_events spine written above (findings_current_status dropped
        # migration 140 — current status is derived from security_events at
        # read time, see core/findings/current_status.py).
        return TelemetryEmitResult(True, event_id=event_id, record_id=finding_id)

    return _emit(
        _write,
        db_path=db_path,
        mode=mode,
        required_tables=("execution_events", "security_events"),
    )


def emit_security_finding_resolved(
    *,
    finding_id: str,
    project_id: str | None = None,
    resolution: str | None = None,
    resolved_by_agent_id: str | None = None,
    resolved_by_skill_id: str | None = None,
    context: TelemetryContext | Mapping[str, Any] | None = None,
    db_path: Path | str | None = None,
    mode: str = MODE_BEST_EFFORT,
) -> TelemetryEmitResult:
    """Mark a security finding resolved and emit security.finding.resolved to spool."""
    ctx = _context(context)
    effective_project_id = project_id or ctx.project_id or ""

    def _write(conn: sqlite3.Connection) -> TelemetryEmitResult:
        updated = resolve_security_finding(conn, finding_id=finding_id, resolution=resolution)
        if not updated:
            return TelemetryEmitResult(False, error=f"security finding not found: {finding_id}")

        try:
            from canonical.events.envelope import CanonicalEventEnvelope
            from spool.writer import write_event as _write_event

            _envelope = CanonicalEventEnvelope(
                event_type="security.finding.resolved",
                payload={
                    "finding_id": finding_id,
                    "project_id": effective_project_id,
                    "resolution": resolution,
                    "resolved_by_agent_id": resolved_by_agent_id,
                    "resolved_by_skill_id": resolved_by_skill_id,
                },
                project_id=effective_project_id or None,
                session_id=None,
                confidence="high",
            )
            _write_event(_envelope.to_dict(), root=None)
        except Exception:
            pass  # fail-open; SQLite update already succeeded

        return TelemetryEmitResult(True, record_id=finding_id)

    return _emit(
        _write,
        db_path=db_path,
        mode=mode,
        required_tables=("security_events",),
    )


def _severity(value: Any) -> str:
    text = (_text(value) or "medium").lower()
    if text in {"error", "critical", "crit"}:
        return "critical"
    if text in {"warning", "warn", "high"}:
        return "high"
    if text in {"medium", "med"}:
        return "medium"
    if text in {"info", "informational"}:
        return "info"
    if text in {"low"}:
        return "low"
    return text


def _stable_security_finding_id(
    *,
    ctx: TelemetryContext,
    scan_id: str | None,
    rule_id: str | None,
    file_path: str | None,
    start_line: int | None,
    end_line: int | None,
    severity: str,
) -> str:
    stable = "|".join(
        (
            ctx.project_id or "",
            scan_id or "",
            rule_id or "",
            file_path or "",
            str(start_line or ""),
            str(end_line or ""),
            severity,
        )
    )
    return f"security-{uuid.uuid5(uuid.NAMESPACE_URL, stable).hex}"


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
