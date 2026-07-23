"""WO-GF-TELEMETRY-SPLIT: research evidence and decision record emitters.

Extracted verbatim from core/telemetry/emitters.py (see emitters.py facade).
emit_research_evidence_record, emit_decision_record.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core.telemetry.execution_spine import record_execution_event, record_research_evidence

from .emitters_shared import (
    MODE_BEST_EFFORT,
    TelemetryContext,
    TelemetryEmitResult,
    _context,
    _emit,
    _id,
    _refs,
    _stable_id,
    _status,
)


def emit_research_evidence_record(
    *,
    question: str,
    decision_class: str = "research_allowed",
    confidence: str | float = "unknown",
    sources: Sequence[Any] | None = None,
    source_summary: str | None = None,
    decision_impact: str | None = None,
    operator_verification_required: bool = False,
    research_id: str | None = None,
    context: TelemetryContext | Mapping[str, Any] | None = None,
    source_refs: Sequence[str] | None = None,
    evidence_refs: Sequence[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
    db_path: Path | str | None = None,
    mode: str = MODE_BEST_EFFORT,
) -> TelemetryEmitResult:
    """Dual-write research/cache/evidence facts into the telemetry spine."""

    ctx = _context(context)
    normalized_research_id = research_id or _stable_id(
        "research", question, tuple(_refs(source_refs)), decision_class
    )

    def _write(conn: sqlite3.Connection) -> TelemetryEmitResult:
        existing = conn.execute(
            "SELECT research_id FROM research_evidence_records WHERE research_id = ?",
            (normalized_research_id,),
        ).fetchone()
        if existing is not None:
            return TelemetryEmitResult(
                False, record_id=normalized_research_id, error="duplicate research evidence skipped"
            )

        event_id = _id("research-event")
        merged_source_refs = _refs(ctx.source_refs, source_refs)
        merged_evidence_refs = _refs(ctx.evidence_refs, evidence_refs)
        research_metadata = {"metadata": dict(metadata or {})}
        record_execution_event(
            conn,
            **ctx.scope(),
            event_id=event_id,
            event_type="research.evidence_recorded",
            event_name=f"Research evidence: {question[:80]}",
            actor_type="system",
            actor_id="research",
            source_refs=merged_source_refs,
            evidence_refs=merged_evidence_refs,
            metadata=research_metadata,
            outcome_status="recorded",
        )
        record_research_evidence(
            conn,
            **ctx.scope(),
            event_id=event_id,
            research_id=normalized_research_id,
            question=question,
            decision_class=decision_class,
            confidence=str(confidence),
            sources=list(sources or []),
            source_summary=source_summary,
            decision_impact=decision_impact,
            operator_verification_required=operator_verification_required,
            evidence_refs=merged_evidence_refs,
        )
        # WO-AI-SPINE (migration 139): the dashboard_attention_items write that
        # used to live here was removed — pure duplication (0 production rows).
        # operator_verification_required and decision_class remain fully
        # queryable directly on research_evidence_records above.
        return TelemetryEmitResult(True, event_id=event_id, record_id=normalized_research_id)

    return _emit(
        _write,
        db_path=db_path,
        mode=mode,
        required_tables=(
            "execution_events",
            "research_evidence_records",
        ),
    )


def emit_decision_record(
    *,
    decision_type: str,
    decision_status: str,
    selected_option: str | None = None,
    rationale: str | None = None,
    options_considered: Sequence[Any] | None = None,
    route_impact: str | None = None,
    outcome_impact: str | None = None,
    research_id: str | None = None,
    operator_required: bool = False,
    approval_required: bool = False,
    prompt_required: bool = False,
    source_decision_id: str | None = None,
    context: TelemetryContext | Mapping[str, Any] | None = None,
    source_refs: Sequence[str] | None = None,
    evidence_refs: Sequence[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
    db_path: Path | str | None = None,
    mode: str = MODE_BEST_EFFORT,
) -> TelemetryEmitResult:
    """Dual-write decision/operator-decision facts into the execution_events spine.

    WO-AI-SPINE (migration 139): decision_records, outcome_records, and
    dashboard_attention_items were dropped (0/2/0 production rows) — this
    function's execution_events row was already a full dual-write of the
    decision, so the per-type tables were pure duplication. The stable
    decision_id is now used directly as the execution_events primary key
    (mirroring emit_workflow_invocation's idempotency pattern below), so
    duplicate calls with the same decision_id remain a no-op. selected_option
    and rationale are not persisted as separate columns anywhere post-migration
    139; event_name captures decision_type and outcome_status captures
    decision_status for read-model derivation (see core/telemetry/read_models.py).
    """

    ctx = _context(context)
    decision_id = source_decision_id or _stable_id(
        "decision", decision_type, selected_option, route_impact, tuple(_refs(source_refs))
    )
    normalized_status = _status(decision_status)

    def _write(conn: sqlite3.Connection) -> TelemetryEmitResult:
        existing = conn.execute(
            "SELECT event_id FROM execution_events WHERE event_id = ?",
            (decision_id,),
        ).fetchone()
        if existing is not None:
            return TelemetryEmitResult(
                False, record_id=decision_id, error="duplicate decision record skipped"
            )

        event_id = decision_id
        merged_source_refs = _refs(ctx.source_refs, source_refs)
        merged_evidence_refs = _refs(ctx.evidence_refs, evidence_refs)
        decision_metadata = {
            "options_considered": list(options_considered or []),
            "selected_option": selected_option,
            "rationale": rationale,
            "route_impact": route_impact,
            "outcome_impact": outcome_impact,
            "research_id": research_id,
            "operator_required": operator_required,
            "approval_required": approval_required,
            "prompt_required": prompt_required,
            "metadata": dict(metadata or {}),
        }
        record_execution_event(
            conn,
            **ctx.scope(),
            event_id=event_id,
            event_type="decision.recorded",
            event_name=f"Decision: {decision_type}",
            actor_type="system",
            actor_id="decision",
            source_refs=merged_source_refs,
            evidence_refs=merged_evidence_refs,
            metadata=decision_metadata,
            outcome_status=normalized_status,
        )
        return TelemetryEmitResult(True, event_id=event_id, record_id=decision_id)

    return _emit(
        _write,
        db_path=db_path,
        mode=mode,
        required_tables=("execution_events",),
    )
