"""Best-effort dual-write emitters for the execution telemetry spine."""

from __future__ import annotations

import os
import json
import sqlite3
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.config.database import get_db_path
from core.telemetry.execution_spine import (
    record_dashboard_attention,
    record_execution_event,
    record_route_decision,
    record_research_evidence,
    record_security_finding,
    record_token_usage,
    resolve_security_finding,
)

TELEMETRY_DB_ENV = "DREAM_STUDIO_TELEMETRY_DB"
TELEMETRY_DISABLED_ENV = "DREAM_STUDIO_TELEMETRY_DISABLED"
MODE_BEST_EFFORT = "best_effort"
MODE_STRICT = "strict"


@dataclass(frozen=True)
class TelemetryContext:
    project_id: str | None = None
    milestone_id: str | None = None
    task_id: str | None = None
    process_run_id: str | None = None
    source_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    current_stage_gate: str | None = None
    current_milestone: str | None = None
    next_stage_gate: str | None = None
    next_milestone: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "TelemetryContext":
        if not isinstance(value, Mapping):
            return cls()
        return cls(
            project_id=_text(
                value.get("project_id"), value.get("project"), value.get("project_name")
            ),
            milestone_id=_text(
                value.get("milestone_id"),
                value.get("milestone"),
                value.get("current_milestone"),
                value.get("next_milestone"),
            ),
            task_id=_text(
                value.get("task_id"), value.get("work_order_id"), value.get("linked_work_order_id")
            ),
            process_run_id=_text(
                value.get("process_run_id"), value.get("run_id"), value.get("session_name")
            ),
            source_refs=_tuple(value.get("source_refs")),
            evidence_refs=_tuple(value.get("evidence_refs")),
            current_stage_gate=_text(value.get("current_stage_gate")),
            current_milestone=_text(value.get("current_milestone")),
            next_stage_gate=_text(value.get("next_stage_gate")),
            next_milestone=_text(value.get("next_milestone")),
        )

    def scope(self) -> dict[str, str | None]:
        return {
            "project_id": _clean(self.project_id),
            "milestone_id": _clean(self.milestone_id or self.current_milestone),
            "task_id": _clean(self.task_id),
            "process_run_id": _clean(self.process_run_id),
        }


@dataclass(frozen=True)
class TelemetryEmitResult:
    emitted: bool
    event_id: str | None = None
    record_id: str | None = None
    error: str | None = None


def emit_route_decision(
    decision: Mapping[str, Any],
    *,
    context: TelemetryContext | Mapping[str, Any] | None = None,
    state: Mapping[str, Any] | None = None,
    db_path: Path | str | None = None,
    mode: str = MODE_BEST_EFFORT,
) -> TelemetryEmitResult:
    """Persist a route/work-order decision without replacing legacy behavior."""

    ctx = _context(context)

    def _write(conn: sqlite3.Connection) -> TelemetryEmitResult:
        event_id = _id("route-event")
        route_id = _id("route")
        route_decision = (
            _text(decision.get("route_decision"), decision.get("next_action")) or "unknown"
        )
        handoff_required = _truthy(decision.get("handoff_required"))
        operator_action_required = _truthy(
            decision.get("operator_action_required"),
            decision.get("human_approval_required"),
        )
        prompt_required = handoff_required or operator_action_required
        source_refs = _refs(ctx.source_refs, decision.get("source_refs"))
        evidence_refs = _refs(ctx.evidence_refs, decision.get("evidence_refs"))
        current_stage_gate = _text(decision.get("current_stage_gate"), ctx.current_stage_gate)
        current_milestone = _text(decision.get("current_milestone"), ctx.current_milestone)
        next_stage_gate = _text(
            decision.get("next_stage_gate"), ctx.next_stage_gate, current_stage_gate
        )
        next_milestone = _text(decision.get("next_milestone"), ctx.next_milestone)
        recommended_next_work_order = _text(decision.get("recommended_next_work_order"))
        if not recommended_next_work_order and not handoff_required:
            recommended_next_work_order = "none"

        metadata = {
            "current_stage_gate": current_stage_gate,
            "current_milestone": current_milestone,
            "next_stage_gate": next_stage_gate,
            "next_milestone": next_milestone,
            "handoff_reason": decision.get("handoff_reason"),
            "stop_gate": decision.get("stop_gate"),
            "continuation_allowed": not handoff_required and not operator_action_required,
            "reason": decision.get("decision_rationale") or decision.get("reason"),
            "state_keys": (
                sorted(str(key) for key in state.keys()) if isinstance(state, Mapping) else []
            ),
        }
        record_execution_event(
            conn,
            **ctx.scope(),
            event_id=event_id,
            event_type="work_order.route_decision",
            event_name=f"Route decision: {route_decision}",
            actor_type="system",
            actor_id="dream-studio",
            source_refs=source_refs,
            evidence_refs=evidence_refs,
            metadata=metadata,
            outcome_status="recorded",
        )
        record_route_decision(
            conn,
            **ctx.scope(),
            event_id=event_id,
            route_id=route_id,
            route_decision=route_decision,
            handoff_required=handoff_required,
            operator_action_required=operator_action_required,
            prompt_required=prompt_required,
            next_stage_gate=next_stage_gate,
            next_milestone=next_milestone,
            recommended_next_work_order=recommended_next_work_order,
            source_refs=source_refs,
            evidence_refs=evidence_refs,
        )
        return TelemetryEmitResult(True, event_id=event_id, record_id=route_id)

    return _emit(
        _write,
        db_path=db_path,
        mode=mode,
        required_tables=("execution_events", "route_decision_records"),
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
    """Dual-write token log rows to token_usage_records."""

    ctx = _context(context)

    def _write(conn: sqlite3.Connection) -> TelemetryEmitResult:
        event_id = _id("token-event")
        token_usage_id = _id("token")
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
        record_token_usage(
            conn,
            **ctx.scope(),
            token_usage_id=token_usage_id,
            model_id=model,
            provider=_provider_from_model(model),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            purpose="session token logging",
        )
        return TelemetryEmitResult(True, event_id=event_id, record_id=token_usage_id)

    return _emit(
        _write,
        db_path=db_path,
        mode=mode,
        required_tables=("execution_events", "token_usage_records"),
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
    """Dual-write validation/eval results into validation, outcome, and attention facts."""

    ctx = _context(context)
    normalized_status = _status(status)

    def _write(conn: sqlite3.Connection) -> TelemetryEmitResult:
        event_id = _id("validation-event")
        validation_id = _id("validation")
        outcome_id = _id("outcome")
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
        conn.execute(
            """
            INSERT INTO outcome_records (
                outcome_id, project_id, milestone_id, task_id, process_run_id,
                event_id, outcome_type, outcome_status, summary, evidence_refs_json
            ) VALUES (
                :outcome_id, :project_id, :milestone_id, :task_id, :process_run_id,
                :event_id, 'validation', :outcome_status, :summary, :evidence_refs_json
            )
            """,
            {
                **ctx.scope(),
                "outcome_id": outcome_id,
                "event_id": event_id,
                "outcome_status": normalized_status,
                "summary": summary,
                "evidence_refs_json": json.dumps(merged_evidence_refs, sort_keys=True),
            },
        )
        attention = _validation_attention(normalized_status, fail_count, error_count, warning_count)
        if attention is not None:
            record_dashboard_attention(
                conn,
                **ctx.scope(),
                event_id=event_id,
                attention_id=_id("attention"),
                attention_type=attention,
                severity=_attention_severity(normalized_status),
                title=f"Validation {normalized_status}: {validation_type}",
                summary=summary or f"Validation result recorded as {normalized_status}.",
                action_required=normalized_status in {"failed", "error", "warning"},
                operator_action_required=False,
                prompt_required=False,
                source_refs=merged_source_refs,
                evidence_refs=merged_evidence_refs,
            )
        return TelemetryEmitResult(True, event_id=event_id, record_id=validation_id)

    return _emit(
        _write,
        db_path=db_path,
        mode=mode,
        required_tables=(
            "execution_events",
            "validation_results",
            "outcome_records",
            "dashboard_attention_items",
        ),
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
            # findings retired migration 112 (WO-Y); dedup via security_events spine directly
            # (findings_current_status is a projection that lags until fold_spine() runs).
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
        if normalized_severity in {"critical", "high"} or normalized_status in {
            "open",
            "unresolved",
        }:
            record_dashboard_attention(
                conn,
                **ctx.scope(),
                event_id=event_id,
                attention_id=_id("attention"),
                attention_type="security_finding",
                severity=normalized_severity,
                title=f"{normalized_severity.title()} security finding",
                summary=description,
                action_required=True,
                operator_action_required=False,
                prompt_required=False,
                source_refs=merged_source_refs,
                evidence_refs=merged_evidence_refs,
            )
        return TelemetryEmitResult(True, event_id=event_id, record_id=finding_id)

    return _emit(
        _write,
        db_path=db_path,
        mode=mode,
        required_tables=("execution_events", "security_events", "dashboard_attention_items"),
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
    """Dual-write workflow execution facts while preserving raw workflow tables."""

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
        _record_outcome(
            conn,
            ctx,
            event_id=event_id,
            outcome_type="workflow",
            outcome_status=normalized_status,
            summary=f"Workflow {workflow_id} recorded with status {normalized_status}.",
            evidence_refs=merged_evidence_refs,
        )
        if normalized_status in {"failed", "error", "warning", "completed_with_failures"}:
            record_dashboard_attention(
                conn,
                **ctx.scope(),
                event_id=event_id,
                attention_id=_id("attention"),
                attention_type="workflow_status_attention",
                severity=_attention_severity(normalized_status),
                title=f"Workflow {normalized_status}: {workflow_id}",
                summary=f"Workflow {workflow_id} requires review for status {normalized_status}.",
                action_required=True,
                operator_action_required=False,
                prompt_required=False,
                source_refs=merged_source_refs,
                evidence_refs=merged_evidence_refs,
            )
        return TelemetryEmitResult(True, event_id=event_id, record_id=event_id)

    return _emit(
        _write,
        db_path=db_path,
        mode=mode,
        required_tables=(
            "execution_events",
            "outcome_records",
            "dashboard_attention_items",
        ),
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
        prompt_required = decision_class in {
            "true_unknown_prompt_required",
            "blocked_due_to_source_uncertainty",
            "blocked_due_to_safety_or_sensitive_context",
        }
        if operator_verification_required or prompt_required:
            record_dashboard_attention(
                conn,
                **ctx.scope(),
                event_id=event_id,
                attention_id=_id("attention"),
                attention_type="research_verification_required",
                severity="warning" if not prompt_required else "high",
                title="Research verification required",
                summary=source_summary or question,
                action_required=True,
                operator_action_required=operator_verification_required,
                prompt_required=prompt_required,
                source_refs=merged_source_refs,
                evidence_refs=merged_evidence_refs,
            )
        return TelemetryEmitResult(True, event_id=event_id, record_id=normalized_research_id)

    return _emit(
        _write,
        db_path=db_path,
        mode=mode,
        required_tables=(
            "execution_events",
            "research_evidence_records",
            "dashboard_attention_items",
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
    """Dual-write decision/operator-decision facts into decision_records."""

    ctx = _context(context)
    decision_id = source_decision_id or _stable_id(
        "decision", decision_type, selected_option, route_impact, tuple(_refs(source_refs))
    )
    normalized_status = _status(decision_status)

    def _write(conn: sqlite3.Connection) -> TelemetryEmitResult:
        existing = conn.execute(
            "SELECT decision_id FROM decision_records WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()
        if existing is not None:
            return TelemetryEmitResult(
                False, record_id=decision_id, error="duplicate decision record skipped"
            )

        event_id = _id("decision-event")
        merged_source_refs = _refs(ctx.source_refs, source_refs)
        merged_evidence_refs = _refs(ctx.evidence_refs, evidence_refs)
        decision_metadata = {
            "options_considered": list(options_considered or []),
            "route_impact": route_impact,
            "outcome_impact": outcome_impact,
            "research_id": research_id,
            "operator_required": operator_required,
            "approval_required": approval_required,
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
        conn.execute(
            """
            INSERT INTO decision_records (
                decision_id, project_id, milestone_id, task_id, process_run_id,
                event_id, decision_type, decision_status, selected_option,
                rationale, source_refs_json, evidence_refs_json
            ) VALUES (
                :decision_id, :project_id, :milestone_id, :task_id, :process_run_id,
                :event_id, :decision_type, :decision_status, :selected_option,
                :rationale, :source_refs_json, :evidence_refs_json
            )
            """,
            {
                **ctx.scope(),
                "decision_id": decision_id,
                "event_id": event_id,
                "decision_type": decision_type,
                "decision_status": normalized_status,
                "selected_option": selected_option,
                "rationale": rationale,
                "source_refs_json": json.dumps(merged_source_refs, sort_keys=True),
                "evidence_refs_json": json.dumps(merged_evidence_refs, sort_keys=True),
            },
        )
        _record_outcome(
            conn,
            ctx,
            event_id=event_id,
            outcome_type="decision",
            outcome_status=normalized_status,
            summary=rationale or f"Decision {decision_type} recorded.",
            evidence_refs=merged_evidence_refs,
        )
        if operator_required or approval_required or prompt_required:
            record_dashboard_attention(
                conn,
                **ctx.scope(),
                event_id=event_id,
                attention_id=_id("attention"),
                attention_type="decision_attention",
                severity="high" if prompt_required else "warning",
                title=f"Decision attention: {decision_type}",
                summary=rationale or f"Decision {decision_type} requires attention.",
                action_required=True,
                operator_action_required=operator_required or approval_required,
                prompt_required=prompt_required,
                source_refs=merged_source_refs,
                evidence_refs=merged_evidence_refs,
            )
        return TelemetryEmitResult(True, event_id=event_id, record_id=decision_id)

    return _emit(
        _write,
        db_path=db_path,
        mode=mode,
        required_tables=(
            "execution_events",
            "decision_records",
            "outcome_records",
            "dashboard_attention_items",
        ),
    )


def _status(value: Any) -> str:
    text = (_text(value) or "unknown").lower()
    if text in {"pass", "passed", "success", "succeeded", "ok"}:
        return "passed"
    if text in {"fail", "failed", "failure"}:
        return "failed"
    if text in {"warn", "warning"}:
        return "warning"
    if text in {"err", "error", "errored"}:
        return "error"
    if text in {"open", "unresolved", "resolved", "recorded", "unknown"}:
        return text
    return text


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


def _attention_severity(status: str) -> str:
    if status == "error":
        return "high"
    if status == "failed":
        return "warning"
    if status == "warning":
        return "warning"
    return "info"


def _validation_attention(
    status: str,
    fail_count: int | None,
    error_count: int | None,
    warning_count: int | None,
) -> str | None:
    if status in {"failed", "error"} or (fail_count or 0) > 0 or (error_count or 0) > 0:
        return "validation_failure"
    if status == "warning" or (warning_count or 0) > 0:
        return "validation_warning"
    return None


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


def _stable_id(prefix: str, *parts: Any) -> str:
    stable = "|".join(str(part) for part in parts if part is not None)
    return f"{prefix}-{uuid.uuid5(uuid.NAMESPACE_URL, stable).hex}"


def _record_outcome(
    conn: sqlite3.Connection,
    ctx: TelemetryContext,
    *,
    event_id: str,
    outcome_type: str,
    outcome_status: str,
    summary: str | None,
    evidence_refs: Sequence[str],
) -> None:
    conn.execute(
        """
        INSERT INTO outcome_records (
            outcome_id, project_id, milestone_id, task_id, process_run_id,
            event_id, outcome_type, outcome_status, summary, evidence_refs_json
        ) VALUES (
            :outcome_id, :project_id, :milestone_id, :task_id, :process_run_id,
            :event_id, :outcome_type, :outcome_status, :summary, :evidence_refs_json
        )
        """,
        {
            **ctx.scope(),
            "outcome_id": _id("outcome"),
            "event_id": event_id,
            "outcome_type": outcome_type,
            "outcome_status": outcome_status,
            "summary": summary,
            "evidence_refs_json": json.dumps(list(evidence_refs), sort_keys=True),
        },
    )


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _emit(
    writer: Any,
    *,
    db_path: Path | str | None,
    mode: str,
    required_tables: Sequence[str],
) -> TelemetryEmitResult:
    if os.environ.get(TELEMETRY_DISABLED_ENV):
        return TelemetryEmitResult(False, error="telemetry disabled")
    try:
        with _connect(db_path) as conn:
            _require_tables(conn, required_tables)
            result = writer(conn)
            conn.commit()
            return result
    except Exception as exc:
        if mode == MODE_STRICT:
            raise
        return TelemetryEmitResult(False, error=str(exc))


def _connect(db_path: Path | str | None) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else _default_db_path()
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def _default_db_path() -> Path:
    override = os.environ.get(TELEMETRY_DB_ENV)
    return Path(override) if override else get_db_path()


def _require_tables(conn: sqlite3.Connection, tables: Sequence[str]) -> None:
    missing = [
        table
        for table in tables
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        is None
    ]
    if missing:
        raise RuntimeError(f"telemetry spine tables missing: {', '.join(missing)}")


def _context(value: TelemetryContext | Mapping[str, Any] | None) -> TelemetryContext:
    if isinstance(value, TelemetryContext):
        return value
    return TelemetryContext.from_mapping(value)


def _text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _clean(value: Any) -> str | None:
    return _text(value)


def _tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value if str(item).strip())
    return (str(value),)


def _refs(*values: Any) -> list[str]:
    refs: list[str] = []
    for value in values:
        refs.extend(_tuple(value))
    return refs


def _truthy(*values: Any) -> bool:
    for value in values:
        if isinstance(value, str):
            if value.strip().lower() in {"true", "1", "yes"}:
                return True
            continue
        if bool(value):
            return True
    return False


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _provider_from_model(model: str) -> str | None:
    lower = model.lower()
    if "claude" in lower:
        return "anthropic"
    if "gpt" in lower or "openai" in lower:
        return "openai"
    return None
