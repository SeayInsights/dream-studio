"""Execution telemetry spine helpers for Dream Studio.

The helpers in this module are deliberately local-first and SQLite-native. They
write structured evidence/test records to the approved telemetry tables without
depending on dashboard/API/runtime surfaces.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from canonical.events.envelope import CanonicalEventEnvelope
    from emitters.shared.spool_writer import write_envelopes as _write_envelopes
except ImportError:
    CanonicalEventEnvelope = None  # type: ignore[assignment,misc]
    _write_envelopes = None  # type: ignore[assignment]

DASHBOARD_MODULES: tuple[dict[str, Any], ...] = (
    {
        "module_id": "security_analytics",
        "module_name": "Security Analytics",
        "module_type": "dashboard_projection",
        "docker_profile": "security-scanners",
        "owns_tables": ["findings"],
        "source_tables": ["execution_events", "findings"],
        "dashboard_cards": ["findings_by_severity", "findings_by_file", "component_attribution"],
        "drilldown_paths": ["project", "milestone", "task", "process_run", "file_line", "finding"],
        "empty_state": "No security findings recorded for the selected scope.",
    },
    {
        "module_id": "token_analytics",
        "module_name": "Token Analytics",
        "module_type": "dashboard_projection",
        "docker_profile": None,
        "owns_tables": ["token_usage_records"],
        "source_tables": [
            "execution_events",
            "token_usage_records",
            "ai_adapter_accounting_profiles",
            "ai_usage_operational_records",
        ],
        "dashboard_cards": [
            "tokens_by_model",
            "tokens_by_component",
            "cost_visibility",
            "operational_value",
        ],
        "drilldown_paths": [
            "project",
            "milestone",
            "task",
            "agent",
            "skill",
            "workflow",
            "hook",
            "model",
        ],
        "empty_state": "No token usage recorded for the selected scope.",
    },
    {
        "module_id": "agent_analytics",
        "module_name": "Agent Analytics",
        "module_type": "dashboard_projection",
        "docker_profile": "agent-workers",
        "owns_tables": ["agent_invocations"],
        "source_tables": ["execution_events", "agent_invocations"],
        "dashboard_cards": ["agent_usage", "agent_outcomes"],
        "drilldown_paths": ["project", "milestone", "task", "process_run", "agent"],
        "empty_state": "No agent invocations recorded for the selected scope.",
    },
    {
        "module_id": "skill_analytics",
        "module_name": "Skill Analytics",
        "module_type": "dashboard_projection",
        "docker_profile": None,
        "owns_tables": ["skill_invocations"],
        "source_tables": ["execution_events", "skill_invocations"],
        "dashboard_cards": ["skill_usage", "skill_outcomes"],
        "drilldown_paths": ["project", "milestone", "task", "process_run", "skill"],
        "empty_state": "No skill invocations recorded for the selected scope.",
    },
    {
        "module_id": "workflow_analytics",
        "module_name": "Workflow Analytics",
        "module_type": "dashboard_projection",
        "docker_profile": "workflow-workers",
        "owns_tables": ["workflow_invocations"],
        "source_tables": ["execution_events", "workflow_invocations", "outcome_records"],
        "dashboard_cards": ["workflow_usage", "workflow_success_failure"],
        "drilldown_paths": ["project", "milestone", "task", "process_run", "workflow", "outcome"],
        "empty_state": "No workflow invocations recorded for the selected scope.",
    },
    {
        "module_id": "hook_analytics",
        "module_name": "Hook Analytics",
        "module_type": "dashboard_projection",
        "docker_profile": None,
        "owns_tables": ["hook_invocations"],
        "source_tables": ["execution_events", "hook_invocations"],
        "dashboard_cards": ["hook_firing_counts", "risk_prevention_counts"],
        "drilldown_paths": ["project", "milestone", "task", "process_run", "hook"],
        "empty_state": "No hook invocations recorded for the selected scope.",
    },
    {
        "module_id": "research_decision_analytics",
        "module_name": "Research And Decision Analytics",
        "module_type": "dashboard_projection",
        "docker_profile": None,
        "owns_tables": [
            "research_evidence_records",
            "decision_records",
            "blocker_resolution_records",
        ],
        "source_tables": [
            "research_evidence_records",
            "decision_records",
            "blocker_resolution_records",
        ],
        "dashboard_cards": ["research_confidence", "decision_status", "blocker_routes"],
        "drilldown_paths": ["project", "milestone", "task", "research", "decision", "blocker"],
        "empty_state": "No research, decision, or blocker records for the selected scope.",
    },
    {
        "module_id": "validation_analytics",
        "module_name": "Validation Analytics",
        "module_type": "dashboard_projection",
        "docker_profile": "validation-sandboxes",
        "owns_tables": ["validation_results"],
        "source_tables": ["execution_events", "validation_results"],
        "dashboard_cards": ["validation_status", "validation_failures"],
        "drilldown_paths": ["project", "milestone", "task", "process_run", "validation"],
        "empty_state": "No validation results recorded for the selected scope.",
    },
    {
        "module_id": "artifact_analytics",
        "module_name": "Artifact Analytics",
        "module_type": "dashboard_projection",
        "docker_profile": None,
        "owns_tables": ["artifact_records", "authority_projection_records"],
        "source_tables": ["artifact_records", "authority_projection_records"],
        "dashboard_cards": ["artifact_lifecycle", "authority_projection_status"],
        "drilldown_paths": ["project", "milestone", "task", "artifact", "projection"],
        "empty_state": "No artifact records for the selected scope.",
    },
    {
        "module_id": "route_milestone_analytics",
        "module_name": "Route And Milestone Analytics",
        "module_type": "dashboard_projection",
        "docker_profile": None,
        "owns_tables": ["route_decision_records", "dashboard_attention_items"],
        "source_tables": [
            "execution_events",
            "route_decision_records",
            "dashboard_attention_items",
        ],
        "dashboard_cards": ["route_status", "dashboard_attention"],
        "drilldown_paths": ["project", "milestone", "task", "route", "attention_item"],
        "empty_state": "No route decisions or dashboard attention items for the selected scope.",
    },
)


@dataclass(frozen=True)
class BlockerRoute:
    route_class: str
    prompt_required: bool
    dashboard_approval_required: bool
    continue_allowed: bool
    rationale: str


def _json(value: Any, default: Any) -> str:
    if value is None:
        value = default
    return json.dumps(value, sort_keys=True)


def _execute(conn: sqlite3.Connection, sql: str, values: Mapping[str, Any]) -> None:
    conn.execute(sql, dict(values))


def register_default_modules(conn: sqlite3.Connection) -> None:
    """Insert dashboard module declarations if they are not already present."""

    for module in DASHBOARD_MODULES:
        conn.execute(
            """
            INSERT OR IGNORE INTO telemetry_module_registry (
                module_id, module_name, module_type, enabled, execution_mode,
                docker_profile, owns_tables_json, emits_event_types_json,
                dashboard_cards_json, health_status
            ) VALUES (
                :module_id, :module_name, :module_type, 1, 'local',
                :docker_profile, :owns_tables_json, :emits_event_types_json,
                :dashboard_cards_json, 'declared'
            )
            """,
            {
                "module_id": module["module_id"],
                "module_name": module["module_name"],
                "module_type": module["module_type"],
                "docker_profile": module["docker_profile"],
                "owns_tables_json": _json(module["owns_tables"], []),
                "emits_event_types_json": _json(module["source_tables"], []),
                "dashboard_cards_json": _json(module["dashboard_cards"], []),
            },
        )


def record_process_run(conn: sqlite3.Connection, **values: Any) -> None:
    _execute(
        conn,
        """
        INSERT INTO process_runs (
            process_run_id, project_id, milestone_id, task_id, run_type, status,
            started_at, ended_at, route_id, summary, metadata_json
        ) VALUES (
            :process_run_id, :project_id, :milestone_id, :task_id, :run_type, :status,
            COALESCE(:started_at, datetime('now')), :ended_at, :route_id, :summary, :metadata_json
        )
        """,
        {
            "process_run_id": values["process_run_id"],
            "project_id": values.get("project_id"),
            "milestone_id": values.get("milestone_id"),
            "task_id": values.get("task_id"),
            "run_type": values.get("run_type", "milestone"),
            "status": values.get("status", "completed"),
            "started_at": values.get("started_at"),
            "ended_at": values.get("ended_at"),
            "route_id": values.get("route_id"),
            "summary": values.get("summary"),
            "metadata_json": _json(values.get("metadata"), {}),
        },
    )


def record_execution_event(conn: sqlite3.Connection, **values: Any) -> None:
    # Direct DB write: keeps execution_events populated so FK-constrained tables
    # (agent_invocations, route_decision_records, etc.) remain valid with
    # PRAGMA foreign_keys = ON.  Uses INSERT OR IGNORE to be idempotent.
    def _as_list(v: Any) -> list:
        if v is None:
            return []
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return []
        return list(v)

    try:
        source_refs = _as_list(values.get("source_refs") or values.get("source_refs_json"))
        evidence_refs = _as_list(values.get("evidence_refs") or values.get("evidence_refs_json"))
        conn.execute(
            """
            INSERT OR IGNORE INTO execution_events (
                event_id, event_type, event_name, project_id, milestone_id, task_id,
                process_run_id, actor_type, actor_id, agent_id, skill_id, workflow_id,
                hook_id, tool_id, model_id, source_refs_json, evidence_refs_json, outcome_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values["event_id"],
                values["event_type"],
                values["event_name"],
                values.get("project_id"),
                values.get("milestone_id"),
                values.get("task_id"),
                values.get("process_run_id"),
                values.get("actor_type"),
                values.get("actor_id"),
                values.get("agent_id"),
                values.get("skill_id"),
                values.get("workflow_id"),
                values.get("hook_id"),
                values.get("tool_id"),
                values.get("model_id"),
                json.dumps(source_refs, sort_keys=True),
                json.dumps(evidence_refs, sort_keys=True),
                values.get("outcome_status"),
            ),
        )
    except Exception:  # noqa: BLE001
        pass

    # Also spool as canonical envelope for the v2 event pipeline.
    if CanonicalEventEnvelope is None or _write_envelopes is None:
        return
    try:
        source_refs_spool = _as_list(values.get("source_refs") or values.get("source_refs_json"))
        evidence_refs_spool = _as_list(
            values.get("evidence_refs") or values.get("evidence_refs_json")
        )
        metadata = values.get("metadata") or values.get("metadata_json") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}
        envelope = CanonicalEventEnvelope(
            event_type=values["event_type"],
            session_id=values.get("session_id"),
            project_id=values.get("project_id"),
            trace={
                "domain": "telemetry",
                "project_id": values.get("project_id"),
                "milestone_id": values.get("milestone_id"),
                "task_id": values.get("task_id"),
                "process_run_id": values.get("process_run_id"),
                "agent_id": values.get("agent_id"),
                "skill_id": values.get("skill_id"),
                "workflow_id": values.get("workflow_id"),
                "hook_id": values.get("hook_id"),
                "tool_id": values.get("tool_id"),
                "model_id": values.get("model_id"),
                "adapter_id": values.get("adapter_id"),
            },
            payload={
                "event_name": values["event_name"],
                "outcome_status": values.get("outcome_status"),
                "source_refs": source_refs_spool,
                "evidence_refs": evidence_refs_spool,
                "metadata": metadata,
            },
            severity="info",
        )
        _write_envelopes([envelope])
    except Exception:  # noqa: BLE001
        # Best-effort: if spool is unavailable, silently skip.
        pass


def record_invocation(conn: sqlite3.Connection, invocation_type: str, **values: Any) -> None:
    table_by_type = {
        "agent": ("agent_invocations", "agent_id"),
        "skill": ("skill_invocations", "skill_id"),
        "workflow": ("workflow_invocations", "workflow_id"),
        "hook": ("hook_invocations", "hook_id"),
        "tool": ("tool_invocations", "tool_id"),
    }
    table, component_col = table_by_type[invocation_type]
    extra = ", prevented_risky_action" if invocation_type == "hook" else ""
    extra_values = ", :prevented_risky_action" if invocation_type == "hook" else ""
    params = {
        "invocation_id": values["invocation_id"],
        "project_id": values.get("project_id"),
        "milestone_id": values.get("milestone_id"),
        "task_id": values.get("task_id"),
        "process_run_id": values.get("process_run_id"),
        "event_id": values.get("event_id"),
        component_col: values[f"{invocation_type}_id"],
        "status": values.get("status", "completed"),
        "purpose": values.get("purpose"),
        "metadata_json": _json(values.get("metadata"), {}),
        "prevented_risky_action": 1 if values.get("prevented_risky_action") else 0,
    }
    conn.execute(
        f"""
        INSERT INTO {table} (
            invocation_id, project_id, milestone_id, task_id, process_run_id,
            event_id, {component_col}, status, purpose, metadata_json{extra}
        ) VALUES (
            :invocation_id, :project_id, :milestone_id, :task_id, :process_run_id,
            :event_id, :{component_col}, :status, :purpose, :metadata_json{extra_values}
        )
        """,
        params,
    )


def record_token_usage(conn: sqlite3.Connection, **values: Any) -> None:
    input_tokens = int(values.get("input_tokens", 0))
    output_tokens = int(values.get("output_tokens", 0))
    cached_tokens = int(values.get("cached_tokens", 0))
    billing_mode = values.get("billing_mode", "unknown")
    estimated_cost = float(values.get("estimated_cost", 0))
    cost_visibility = values.get("cost_visibility")
    if cost_visibility is None:
        if billing_mode in {"subscription_plan", "plan_allowance"}:
            cost_visibility = "unavailable"
            estimated_cost = 0.0
        else:
            cost_visibility = "estimated" if estimated_cost > 0 else "unavailable"
    cost_source = values.get("cost_source")
    if cost_source is None:
        cost_source = "local_estimate" if estimated_cost > 0 else "unavailable"
    _execute(
        conn,
        """
        INSERT INTO token_usage_records (
            token_usage_id, project_id, milestone_id, task_id, process_run_id,
            agent_id, skill_id, workflow_id, hook_id, model_id, provider,
            input_tokens, output_tokens, cached_tokens, total_tokens,
            estimated_cost, purpose, adapter_id, billing_mode, token_visibility,
            cost_visibility, usage_source, cost_source, accounting_confidence
        ) VALUES (
            :token_usage_id, :project_id, :milestone_id, :task_id, :process_run_id,
            :agent_id, :skill_id, :workflow_id, :hook_id, :model_id, :provider,
            :input_tokens, :output_tokens, :cached_tokens, :total_tokens,
            :estimated_cost, :purpose, :adapter_id, :billing_mode, :token_visibility,
            :cost_visibility, :usage_source, :cost_source, :accounting_confidence
        )
        """,
        {
            "token_usage_id": values["token_usage_id"],
            "project_id": values.get("project_id"),
            "milestone_id": values.get("milestone_id"),
            "task_id": values.get("task_id"),
            "process_run_id": values.get("process_run_id"),
            "agent_id": values.get("agent_id"),
            "skill_id": values.get("skill_id"),
            "workflow_id": values.get("workflow_id"),
            "hook_id": values.get("hook_id"),
            "model_id": values.get("model_id"),
            "provider": values.get("provider"),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_tokens": cached_tokens,
            "total_tokens": int(
                values.get("total_tokens", input_tokens + output_tokens + cached_tokens)
            ),
            "estimated_cost": estimated_cost,
            "purpose": values.get("purpose"),
            "adapter_id": values.get("adapter_id"),
            "billing_mode": billing_mode,
            "token_visibility": values.get("token_visibility", "exact"),
            "cost_visibility": cost_visibility,
            "usage_source": values.get("usage_source", "local_telemetry"),
            "cost_source": cost_source,
            "accounting_confidence": values.get(
                "confidence", values.get("accounting_confidence", "medium")
            ),
        },
    )


def record_security_finding(conn: sqlite3.Connection, **values: Any) -> None:
    _execute(
        conn,
        """
        INSERT INTO findings (
            finding_id, project_id, milestone_id, task_id, scan_id, process_run_id,
            severity, category, rule_id, file_path, start_line, end_line,
            description, recommendation, status, introduced_by_agent_id,
            introduced_by_skill_id, introduced_by_workflow_id, introduced_by_hook_id,
            evidence_refs_json
        ) VALUES (
            :finding_id, :project_id, :milestone_id, :task_id, :scan_id, :process_run_id,
            :severity, :category, :rule_id, :file_path, :start_line, :end_line,
            :description, :recommendation, :status, :introduced_by_agent_id,
            :introduced_by_skill_id, :introduced_by_workflow_id, :introduced_by_hook_id,
            :evidence_refs_json
        )
        """,
        {
            "finding_id": values["finding_id"],
            "project_id": values.get("project_id"),
            "milestone_id": values.get("milestone_id"),
            "task_id": values.get("task_id"),
            "scan_id": values.get("scan_id"),
            "process_run_id": values.get("process_run_id"),
            "severity": values["severity"],
            "category": values.get("category"),
            "rule_id": values.get("rule_id"),
            "file_path": values.get("file_path"),
            "start_line": values.get("start_line"),
            "end_line": values.get("end_line"),
            "description": values["description"],
            "recommendation": values.get("recommendation"),
            "status": values.get("status", "open"),
            "introduced_by_agent_id": values.get("introduced_by_agent_id"),
            "introduced_by_skill_id": values.get("introduced_by_skill_id"),
            "introduced_by_workflow_id": values.get("introduced_by_workflow_id"),
            "introduced_by_hook_id": values.get("introduced_by_hook_id"),
            "evidence_refs_json": _json(values.get("evidence_refs"), []),
        },
    )


def resolve_security_finding(
    conn: sqlite3.Connection, *, finding_id: str, resolution: str | None = None
) -> bool:
    """Update findings.status for a resolved finding.

    Returns True if the row was found and updated, False if not found.
    """
    valid_resolutions = {"fixed", "mitigated", "accepted", "false_positive"}
    new_status = resolution if resolution in valid_resolutions else "fixed"
    cursor = conn.execute(
        "UPDATE findings SET status = ? WHERE finding_id = ?",
        (new_status, finding_id),
    )
    return cursor.rowcount > 0


def record_route_decision(conn: sqlite3.Connection, **values: Any) -> None:
    _execute(
        conn,
        """
        INSERT INTO route_decision_records (
            route_id, project_id, milestone_id, task_id, process_run_id, event_id,
            route_decision, handoff_required, operator_action_required,
            prompt_required, next_stage_gate, next_milestone,
            recommended_next_work_order, source_refs_json, evidence_refs_json
        ) VALUES (
            :route_id, :project_id, :milestone_id, :task_id, :process_run_id, :event_id,
            :route_decision, :handoff_required, :operator_action_required,
            :prompt_required, :next_stage_gate, :next_milestone,
            :recommended_next_work_order, :source_refs_json, :evidence_refs_json
        )
        """,
        {
            "route_id": values["route_id"],
            "project_id": values.get("project_id"),
            "milestone_id": values.get("milestone_id"),
            "task_id": values.get("task_id"),
            "process_run_id": values.get("process_run_id"),
            "event_id": values.get("event_id"),
            "route_decision": values["route_decision"],
            "handoff_required": 1 if values.get("handoff_required") else 0,
            "operator_action_required": 1 if values.get("operator_action_required") else 0,
            "prompt_required": 1 if values.get("prompt_required") else 0,
            "next_stage_gate": values.get("next_stage_gate"),
            "next_milestone": values.get("next_milestone"),
            "recommended_next_work_order": values.get("recommended_next_work_order"),
            "source_refs_json": _json(values.get("source_refs"), []),
            "evidence_refs_json": _json(values.get("evidence_refs"), []),
        },
    )


def record_dashboard_attention(conn: sqlite3.Connection, **values: Any) -> None:
    _execute(
        conn,
        """
        INSERT INTO dashboard_attention_items (
            attention_id, project_id, milestone_id, task_id, process_run_id,
            event_id, attention_type, severity, title, summary, action_required,
            operator_action_required, prompt_required, status, source_refs_json,
            evidence_refs_json
        ) VALUES (
            :attention_id, :project_id, :milestone_id, :task_id, :process_run_id,
            :event_id, :attention_type, :severity, :title, :summary, :action_required,
            :operator_action_required, :prompt_required, :status, :source_refs_json,
            :evidence_refs_json
        )
        """,
        {
            "attention_id": values["attention_id"],
            "project_id": values.get("project_id"),
            "milestone_id": values.get("milestone_id"),
            "task_id": values.get("task_id"),
            "process_run_id": values.get("process_run_id"),
            "event_id": values.get("event_id"),
            "attention_type": values["attention_type"],
            "severity": values["severity"],
            "title": values["title"],
            "summary": values.get("summary"),
            "action_required": 1 if values.get("action_required") else 0,
            "operator_action_required": 1 if values.get("operator_action_required") else 0,
            "prompt_required": 1 if values.get("prompt_required") else 0,
            "status": values.get("status", "open"),
            "source_refs_json": _json(values.get("source_refs"), []),
            "evidence_refs_json": _json(values.get("evidence_refs"), []),
        },
    )


def record_research_evidence(conn: sqlite3.Connection, **values: Any) -> None:
    _execute(
        conn,
        """
        INSERT INTO research_evidence_records (
            research_id, project_id, milestone_id, task_id, process_run_id, event_id,
            question, decision_class, confidence, sources_json, source_summary,
            decision_impact, operator_verification_required, evidence_refs_json
        ) VALUES (
            :research_id, :project_id, :milestone_id, :task_id, :process_run_id, :event_id,
            :question, :decision_class, :confidence, :sources_json, :source_summary,
            :decision_impact, :operator_verification_required, :evidence_refs_json
        )
        """,
        {
            "research_id": values["research_id"],
            "project_id": values.get("project_id"),
            "milestone_id": values.get("milestone_id"),
            "task_id": values.get("task_id"),
            "process_run_id": values.get("process_run_id"),
            "event_id": values.get("event_id"),
            "question": values["question"],
            "decision_class": values["decision_class"],
            "confidence": values["confidence"],
            "sources_json": _json(values.get("sources"), []),
            "source_summary": values.get("source_summary"),
            "decision_impact": values.get("decision_impact"),
            "operator_verification_required": (
                1 if values.get("operator_verification_required") else 0
            ),
            "evidence_refs_json": _json(values.get("evidence_refs"), []),
        },
    )


def record_blocker_resolution(conn: sqlite3.Connection, **values: Any) -> None:
    _execute(
        conn,
        """
        INSERT INTO blocker_resolution_records (
            blocker_id, project_id, milestone_id, task_id, process_run_id, event_id,
            blocker_class, route_class, confidence, resolution_status,
            prompt_required, dashboard_approval_required, rationale,
            research_refs_json, evidence_refs_json
        ) VALUES (
            :blocker_id, :project_id, :milestone_id, :task_id, :process_run_id, :event_id,
            :blocker_class, :route_class, :confidence, :resolution_status,
            :prompt_required, :dashboard_approval_required, :rationale,
            :research_refs_json, :evidence_refs_json
        )
        """,
        {
            "blocker_id": values["blocker_id"],
            "project_id": values.get("project_id"),
            "milestone_id": values.get("milestone_id"),
            "task_id": values.get("task_id"),
            "process_run_id": values.get("process_run_id"),
            "event_id": values.get("event_id"),
            "blocker_class": values["blocker_class"],
            "route_class": values["route_class"],
            "confidence": values["confidence"],
            "resolution_status": values["resolution_status"],
            "prompt_required": 1 if values.get("prompt_required") else 0,
            "dashboard_approval_required": 1 if values.get("dashboard_approval_required") else 0,
            "rationale": values.get("rationale"),
            "research_refs_json": _json(values.get("research_refs"), []),
            "evidence_refs_json": _json(values.get("evidence_refs"), []),
        },
    )


def record_authority_projection(conn: sqlite3.Connection, **values: Any) -> None:
    _execute(
        conn,
        """
        INSERT INTO authority_projection_records (
            projection_id, project_id, milestone_id, task_id, process_run_id,
            event_id, projection_domain, source_authority, source_refs_json,
            lifecycle_status, authority_role, derived_fields_json, confidence,
            stale_superseded_json, stop_gate_implications_json,
            validation_requirements_json, dashboard_readiness_json
        ) VALUES (
            :projection_id, :project_id, :milestone_id, :task_id, :process_run_id,
            :event_id, :projection_domain, :source_authority, :source_refs_json,
            :lifecycle_status, :authority_role, :derived_fields_json, :confidence,
            :stale_superseded_json, :stop_gate_implications_json,
            :validation_requirements_json, :dashboard_readiness_json
        )
        """,
        {
            "projection_id": values["projection_id"],
            "project_id": values.get("project_id"),
            "milestone_id": values.get("milestone_id"),
            "task_id": values.get("task_id"),
            "process_run_id": values.get("process_run_id"),
            "event_id": values.get("event_id"),
            "projection_domain": values["projection_domain"],
            "source_authority": values["source_authority"],
            "source_refs_json": _json(values.get("source_refs"), []),
            "lifecycle_status": values.get("lifecycle_status", "draft_generated"),
            "authority_role": values["authority_role"],
            "derived_fields_json": _json(values.get("derived_fields"), {}),
            "confidence": values.get("confidence", "unknown"),
            "stale_superseded_json": _json(values.get("stale_superseded"), {}),
            "stop_gate_implications_json": _json(values.get("stop_gate_implications"), []),
            "validation_requirements_json": _json(values.get("validation_requirements"), []),
            "dashboard_readiness_json": _json(values.get("dashboard_readiness"), {}),
        },
    )


def classify_research_blocker(
    *,
    confidence: str,
    sources_sufficient: bool,
    sensitive_or_security_risk: bool = False,
    material_risk_change: bool = False,
    ownership_split: bool = False,
    route_can_pause_or_route_around: bool = True,
) -> BlockerRoute:
    confidence = confidence.lower()
    high_confidence = confidence == "high"
    if (
        high_confidence
        and sources_sufficient
        and not sensitive_or_security_risk
        and not material_risk_change
    ):
        return BlockerRoute(
            "concrete_research_resolved_continue",
            prompt_required=False,
            dashboard_approval_required=False,
            continue_allowed=True,
            rationale="High-confidence local evidence resolves the blocker inside approved scope.",
        )
    if (
        high_confidence
        and sources_sufficient
        and material_risk_change
        and route_can_pause_or_route_around
    ):
        return BlockerRoute(
            "concrete_research_requires_dashboard_approval",
            prompt_required=False,
            dashboard_approval_required=True,
            continue_allowed=True,
            rationale="Material-risk decision is captured as dashboard approval while safe work routes around it.",
        )
    if ownership_split:
        return BlockerRoute(
            "team_or_department_decision_prompt_required",
            prompt_required=True,
            dashboard_approval_required=False,
            continue_allowed=False,
            rationale="Ownership is split across people, teams, or departments.",
        )
    if sensitive_or_security_risk:
        return BlockerRoute(
            "unsafe_hard_stop",
            prompt_required=True,
            dashboard_approval_required=False,
            continue_allowed=False,
            rationale="Sensitive or security context requires a hard stop.",
        )
    return BlockerRoute(
        "true_unknown_prompt_required",
        prompt_required=True,
        dashboard_approval_required=False,
        continue_allowed=False,
        rationale="Confidence or source attribution is insufficient for safe continuation.",
    )


def usage_by_component(
    conn: sqlite3.Connection, table: str, component_column: str
) -> list[sqlite3.Row]:
    return conn.execute(f"""
        SELECT project_id, milestone_id, task_id, {component_column} AS component_id,
               COUNT(*) AS invocation_count
        FROM {table}
        GROUP BY project_id, milestone_id, task_id, {component_column}
        ORDER BY invocation_count DESC, component_id
        """).fetchall()


def token_rollup(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("""
        SELECT project_id, milestone_id, task_id, agent_id, skill_id, workflow_id,
               hook_id, model_id, SUM(total_tokens) AS total_tokens,
               SUM(estimated_cost) AS estimated_cost
        FROM token_usage_records
        GROUP BY project_id, milestone_id, task_id, agent_id, skill_id, workflow_id, hook_id, model_id
        ORDER BY total_tokens DESC
        """).fetchall()


def findings_rollup(conn: sqlite3.Connection) -> list[sqlite3.Row]:

    return conn.execute("""
        SELECT project_id, file_path, severity, COUNT(*) AS finding_count
        FROM findings
        GROUP BY project_id, file_path, severity
        ORDER BY finding_count DESC, severity, file_path
        """).fetchall()


def dashboard_module_declarations() -> tuple[dict[str, Any], ...]:
    """Return immutable dashboard module declarations for tests and docs."""

    return DASHBOARD_MODULES
