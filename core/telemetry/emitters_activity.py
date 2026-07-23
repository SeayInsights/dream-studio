"""WO-GF-TELEMETRY-SPLIT: emitters for hook/tool/skill/token activity.

Extracted verbatim from core/telemetry/emitters.py (see emitters.py facade).
emit_hook_tool_activity, emit_skill_invocations, emit_token_usage_record.
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
    _id,
    _refs,
    _text,
)


def emit_hook_tool_activity(
    *,
    hook_name: str,
    tool_name: str,
    tool_input: Mapping[str, Any] | None = None,
    status: str = "completed",
    context: TelemetryContext | Mapping[str, Any] | None = None,
    db_path: Path | str | None = None,
    mode: str = MODE_BEST_EFFORT,
) -> TelemetryEmitResult:
    """Persist hook and tool activity while preserving existing hook behavior."""

    ctx = _context(context)
    tool_input = tool_input if isinstance(tool_input, Mapping) else {}

    def _write(conn: sqlite3.Connection) -> TelemetryEmitResult:
        event_id = _id("hook-tool-event")
        source_refs = _refs(ctx.source_refs)
        evidence_refs = _refs(ctx.evidence_refs)
        metadata = {
            "hook_name": hook_name,
            "tool_name": tool_name,
            "tool_input_keys": sorted(str(key) for key in tool_input.keys()),
            "file_path": _text(tool_input.get("file_path"), tool_input.get("path")),
        }
        record_execution_event(
            conn,
            **ctx.scope(),
            event_id=event_id,
            event_type="hook.tool_activity",
            event_name=f"{hook_name}: {tool_name}",
            actor_type="hook",
            actor_id=hook_name,
            hook_id=hook_name,
            tool_id=tool_name,
            source_refs=source_refs,
            evidence_refs=evidence_refs,
            metadata=metadata,
            outcome_status=status,
        )
        return TelemetryEmitResult(True, event_id=event_id, record_id=event_id)

    return _emit(
        _write,
        db_path=db_path,
        mode=mode,
        required_tables=("execution_events",),
    )


def emit_skill_invocations(
    skills: Sequence[Mapping[str, Any]],
    *,
    success: bool,
    context: TelemetryContext | Mapping[str, Any] | None = None,
    db_path: Path | str | None = None,
    mode: str = MODE_BEST_EFFORT,
) -> TelemetryEmitResult:
    """Dual-write session skill telemetry into the new skill fact table."""

    ctx = _context(context)

    def _write(conn: sqlite3.Connection) -> TelemetryEmitResult:
        last_event_id: str | None = None
        for skill in skills:
            skill_id = (
                _text(skill.get("name"), skill.get("skill"), skill.get("skill_name")) or "unknown"
            )
            event_id = _id("skill-event")
            metadata = {"skill": dict(skill), "success": success}
            record_execution_event(
                conn,
                **ctx.scope(),
                event_id=event_id,
                event_type="skill.invoked",
                event_name=f"Skill invoked: {skill_id}",
                actor_type="skill",
                actor_id=skill_id,
                skill_id=skill_id,
                source_refs=_refs(ctx.source_refs),
                evidence_refs=_refs(ctx.evidence_refs),
                metadata=metadata,
                outcome_status="completed" if success else "failed",
            )
            last_event_id = event_id
        return TelemetryEmitResult(True, event_id=last_event_id, record_id=last_event_id)

    return _emit(
        _write,
        db_path=db_path,
        mode=mode,
        required_tables=("execution_events",),
    )


def emit_token_usage_record(
    *,
    session_name: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
    context: TelemetryContext | Mapping[str, Any] | None = None,
    db_path: Path | str | None = None,
    mode: str = MODE_BEST_EFFORT,
) -> TelemetryEmitResult:
    """Dual-write token log telemetry into execution_events.

    WO-DBA-DROP: the token_usage_records SQLite table (migration 137) is retired
    — record_token_usage/token_usage_records were removed since the canonical
    token.consumed events (captured independently by
    core/telemetry/token_capture.py) are the source of truth for token
    accounting, projected into the DuckDB aggregate_metrics.db
    token_usage_records view. This function's execution_events dual-write is
    unrelated telemetry (session/skill invocation tracking) and is unchanged.
    """

    ctx = _context(context)

    def _write(conn: sqlite3.Connection) -> TelemetryEmitResult:
        event_id = _id("token-event")
        metadata = {"session_name": session_name, "model": model}
        record_execution_event(
            conn,
            **ctx.scope(),
            event_id=event_id,
            event_type="token.usage_recorded",
            event_name=f"Token usage: {session_name}",
            actor_type="system",
            actor_id="token_logger",
            model_id=model,
            source_refs=_refs(ctx.source_refs),
            evidence_refs=_refs(ctx.evidence_refs),
            metadata=metadata,
            outcome_status="recorded",
        )
        return TelemetryEmitResult(True, event_id=event_id, record_id=event_id)

    return _emit(
        _write,
        db_path=db_path,
        mode=mode,
        required_tables=("execution_events",),
    )
