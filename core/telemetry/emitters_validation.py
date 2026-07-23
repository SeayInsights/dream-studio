"""WO-GF-TELEMETRY-SPLIT: validation result emitter.

Extracted verbatim from core/telemetry/emitters.py (see emitters.py facade).
emit_validation_result.
"""

from __future__ import annotations

import json
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
    _id,
    _refs,
    _status,
)


def emit_validation_result(
    *,
    validation_type: str,
    status: str,
    command: str | None = None,
    scope: str | None = None,
    summary: str | None = None,
    pass_count: int | None = None,
    fail_count: int | None = None,
    error_count: int | None = None,
    warning_count: int | None = None,
    context: TelemetryContext | Mapping[str, Any] | None = None,
    source_refs: Sequence[str] | None = None,
    evidence_refs: Sequence[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
    db_path: Path | str | None = None,
    mode: str = MODE_BEST_EFFORT,
) -> TelemetryEmitResult:
    """Dual-write validation/eval results into execution_events and validation_results.

    WO-AI-SPINE (migration 139): the outcome_records and dashboard_attention_items
    writes below were removed — they were pure duplication of the
    execution_events row this function already writes (0/2/0 production rows
    across the three retired tables). Outcome/attention readers now derive
    their view from execution_events filtered by event_type + outcome_status.
    """

    ctx = _context(context)
    normalized_status = _status(status)

    def _write(conn: sqlite3.Connection) -> TelemetryEmitResult:
        event_id = _id("validation-event")
        validation_id = _id("validation")
        merged_source_refs = _refs(ctx.source_refs, source_refs)
        merged_evidence_refs = _refs(ctx.evidence_refs, evidence_refs)
        event_metadata = {
            "validation_type": validation_type,
            "command": command,
            "scope": scope,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "error_count": error_count,
            "warning_count": warning_count,
            "metadata": dict(metadata or {}),
        }
        record_execution_event(
            conn,
            **ctx.scope(),
            event_id=event_id,
            event_type="validation.result_recorded",
            event_name=f"Validation result: {validation_type}",
            actor_type="system",
            actor_id="validation",
            source_refs=merged_source_refs,
            evidence_refs=merged_evidence_refs,
            metadata=event_metadata,
            outcome_status=normalized_status,
        )
        conn.execute(
            """
            INSERT INTO validation_results (
                validation_id, project_id, milestone_id, task_id, process_run_id,
                event_id, validation_type, status, command, scope, summary,
                evidence_refs_json
            ) VALUES (
                :validation_id, :project_id, :milestone_id, :task_id, :process_run_id,
                :event_id, :validation_type, :status, :command, :scope, :summary,
                :evidence_refs_json
            )
            """,
            {
                **ctx.scope(),
                "validation_id": validation_id,
                "event_id": event_id,
                "validation_type": validation_type,
                "status": normalized_status,
                "command": command,
                "scope": scope,
                "summary": summary,
                "evidence_refs_json": json.dumps(merged_evidence_refs, sort_keys=True),
            },
        )
        return TelemetryEmitResult(True, event_id=event_id, record_id=validation_id)

    return _emit(
        _write,
        db_path=db_path,
        mode=mode,
        required_tables=(
            "execution_events",
            "validation_results",
        ),
    )
