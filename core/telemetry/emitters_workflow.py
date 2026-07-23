"""WO-GF-TELEMETRY-SPLIT: workflow invocation emitter.

Extracted verbatim from core/telemetry/emitters.py (see emitters.py facade).
emit_workflow_invocation.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core.telemetry.execution_spine import record_execution_event

from .emitters_shared import (
    MODE_BEST_EFFORT,
    TelemetryContext,
    TelemetryEmitResult,
    _context,
    _emit,
    _refs,
    _stable_id,
    _status,
    _text,
)


def emit_workflow_invocation(
    *,
    workflow_id: str,
    status: str,
    run_key: str | None = None,
    node_id: str | None = None,
    yaml_path: str | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
    duration_ms: int | None = None,
    nodes: Mapping[str, Any] | None = None,
    context: TelemetryContext | Mapping[str, Any] | None = None,
    source_refs: Sequence[str] | None = None,
    evidence_refs: Sequence[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
    db_path: Path | str | None = None,
    mode: str = MODE_BEST_EFFORT,
) -> TelemetryEmitResult:
    """Dual-write workflow execution facts while preserving raw workflow tables.

    WO-AI-SPINE (migration 139): the outcome_records and dashboard_attention_items
    writes below were removed — pure duplication of the execution_events row this
    function already writes. Readers derive outcome/attention state from
    execution_events filtered by event_type='workflow.invocation_recorded' and
    outcome_status.
    """

    ctx = _context(context)
    workflow_status = (_text(status) or "unknown").lower()
    normalized_status = {
        "success": "completed",
        "completed": "completed",
        "completed_with_failures": "failed",
        "aborted": "cancelled",
    }.get(workflow_status, _status(status))
    invocation_id = _stable_id("workflow", workflow_id, run_key, node_id, normalized_status)

    def _write(conn: sqlite3.Connection) -> TelemetryEmitResult:
        existing = conn.execute(
            "SELECT event_id FROM execution_events WHERE event_id = ?",
            (invocation_id,),
        ).fetchone()
        if existing is not None:
            return TelemetryEmitResult(
                False, record_id=invocation_id, error="duplicate workflow invocation skipped"
            )

        event_id = invocation_id
        merged_source_refs = _refs(ctx.source_refs, source_refs)
        merged_evidence_refs = _refs(ctx.evidence_refs, evidence_refs)
        workflow_metadata = {
            "run_key": run_key,
            "node_id": node_id,
            "yaml_path": yaml_path,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_ms": duration_ms,
            "nodes": dict(nodes or {}),
            "metadata": dict(metadata or {}),
        }
        record_execution_event(
            conn,
            **ctx.scope(),
            event_id=event_id,
            event_type="workflow.invocation_recorded",
            event_name=f"Workflow invocation: {workflow_id}",
            actor_type="workflow",
            actor_id=workflow_id,
            workflow_id=workflow_id,
            source_refs=merged_source_refs,
            evidence_refs=merged_evidence_refs,
            metadata=workflow_metadata,
            outcome_status=normalized_status,
        )
        return TelemetryEmitResult(True, event_id=event_id, record_id=event_id)

    return _emit(
        _write,
        db_path=db_path,
        mode=mode,
        required_tables=("execution_events",),
    )
