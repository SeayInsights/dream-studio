"""Execution telemetry spine helpers for Dream Studio.

The helpers in this module are deliberately local-first and SQLite-native. They
write structured evidence/test records to the approved telemetry tables without
depending on dashboard/API/runtime surfaces.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from datetime import UTC

logger = logging.getLogger(__name__)

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
        "owns_tables": ["security_events", "findings_current_status"],
        "source_tables": ["execution_events", "security_events", "findings_current_status"],
        "dashboard_cards": ["findings_by_severity", "findings_by_file", "component_attribution"],
        "drilldown_paths": ["project", "milestone", "task", "process_run", "file_line", "finding"],
        "empty_state": "No security findings recorded for the selected scope.",
    },
    {
        "module_id": "token_analytics",
        "module_name": "Token Analytics",
        "module_type": "dashboard_projection",
        "docker_profile": None,
        # token_usage_records: dropped migration 138 — token analytics derive
        # from token.consumed canonical events via the spine/DuckDB view.
        "owns_tables": ["execution_events"],
        "source_tables": [
            "execution_events",
            "ai_adapter_accounting_profiles",
            # ai_usage_operational_records: dropped migration 131
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
        "owns_tables": ["execution_events"],
        "source_tables": ["execution_events"],
        "dashboard_cards": ["agent_usage", "agent_outcomes"],
        "drilldown_paths": ["project", "milestone", "task", "process_run", "agent"],
        "empty_state": "No agent invocations recorded for the selected scope.",
    },
    {
        "module_id": "skill_analytics",
        "module_name": "Skill Analytics",
        "module_type": "dashboard_projection",
        "docker_profile": None,
        "owns_tables": ["execution_events"],
        "source_tables": ["execution_events"],
        "dashboard_cards": ["skill_usage", "skill_outcomes"],
        "drilldown_paths": ["project", "milestone", "task", "process_run", "skill"],
        "empty_state": "No skill invocations recorded for the selected scope.",
    },
    {
        "module_id": "workflow_analytics",
        "module_name": "Workflow Analytics",
        "module_type": "dashboard_projection",
        "docker_profile": "workflow-workers",
        "owns_tables": ["execution_events"],
        # outcome_records: dropped migration 139 (WO-AI-SPINE, AD-5) — outcomes are
        # derived from execution_events filtered by event_type + outcome_status.
        "source_tables": ["execution_events"],
        "dashboard_cards": ["workflow_usage", "workflow_success_failure"],
        "drilldown_paths": ["project", "milestone", "task", "process_run", "workflow", "outcome"],
        "empty_state": "No workflow invocations recorded for the selected scope.",
    },
    {
        "module_id": "hook_analytics",
        "module_name": "Hook Analytics",
        "module_type": "dashboard_projection",
        "docker_profile": None,
        "owns_tables": ["execution_events"],
        "source_tables": ["execution_events"],
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
            # blocker_resolution_records: dropped migration 130
            # decision_records: dropped migration 139 (WO-AI-SPINE, AD-5) — decisions
            # are derived from execution_events (event_type='decision.recorded').
        ],
        "source_tables": [
            "research_evidence_records",
            "execution_events",
            # blocker_resolution_records: dropped migration 130
            # decision_records: dropped migration 139 (WO-AI-SPINE, AD-5)
        ],
        "dashboard_cards": ["research_confidence", "decision_status"],
        "drilldown_paths": ["project", "milestone", "task", "research", "decision"],
        "empty_state": "No research or decision records for the selected scope.",
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
    # artifact_analytics module removed: artifact_records + authority_projection_records
    # dropped in migration 130 (aspirational telemetry, 0 rows, no live writers).
    {
        "module_id": "route_milestone_analytics",
        "module_name": "Route And Milestone Analytics",
        "module_type": "dashboard_projection",
        "docker_profile": None,
        # route_decision_records: dropped migration 131
        # dashboard_attention_items: dropped migration 139 (WO-AI-SPINE, AD-5) —
        # attention derives from execution_events; shared spine ownership per
        # the sibling derive-from-spine modules.
        "owns_tables": ["execution_events"],
        "source_tables": [
            "execution_events",
            # route_decision_records: dropped migration 131
            # dashboard_attention_items: dropped migration 139 (WO-AI-SPINE, AD-5)
        ],
        "dashboard_cards": ["dashboard_attention"],
        "drilldown_paths": ["project", "milestone", "task", "attention_item"],
        "empty_state": "No dashboard attention items for the selected scope.",
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


def _resolve_event_project_id(raw_project_id: Any, conn: sqlite3.Connection) -> Any:
    """Resolve a raw project key to a business_projects UUID when possible.

    If raw_project_id is already a UUID or None, return it unchanged.
    If it matches a registered project (by name, slug, or path basename),
    return the UUID. Otherwise return raw_project_id unchanged (never fabricate).
    """
    import re as _re

    if raw_project_id is None:
        return None
    pid = str(raw_project_id).strip()
    if not pid:
        return raw_project_id
    # Already a UUID — skip the lookup
    if _re.match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        pid,
        _re.IGNORECASE,
    ):
        return raw_project_id
    try:
        from core.projects.attribution import resolve_project_uuid as _resolve

        resolved = _resolve(pid, conn)
        return resolved if resolved is not None else raw_project_id
    except Exception:
        return raw_project_id


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

    # Resolve project key → UUID at write time so new events carry UUIDs.
    raw_project_id = values.get("project_id")
    resolved_project_id = _resolve_event_project_id(raw_project_id, conn)

    try:
        source_refs = _as_list(values.get("source_refs") or values.get("source_refs_json"))
        evidence_refs = _as_list(values.get("evidence_refs") or values.get("evidence_refs_json"))
        conn.execute(
            """
            INSERT OR IGNORE INTO execution_events (
                event_id, event_type, event_name, project_id, milestone_id, task_id,
                process_run_id, actor_type, actor_id, agent_id, skill_id, workflow_id,
                hook_id, tool_id, model_id, source_refs_json, evidence_refs_json,
                outcome_status, parent_event_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values["event_id"],
                values["event_type"],
                values["event_name"],
                resolved_project_id,
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
                values.get("parent_event_id"),
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
    try:
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
    except Exception as exc:  # noqa: BLE001
        # Tables may be absent in legacy or migrated DBs (migration 106).
        logger.debug("record_invocation: DB write skipped for %s — %s", table, exc)


def record_security_finding(conn: sqlite3.Connection, **values: Any) -> None:
    # findings table retired in migration 112 (WO-Y). Write to security_events spine.
    try:
        from core.findings.mutations import _now

        conn.execute(
            """INSERT OR IGNORE INTO security_events
               (event_id, parent_event_id, event_kind, correlation_id,
                project_id, work_order_id, scanner_type,
                cwe_id, file_path, line_number, vuln_class,
                severity, title, body, created_at)
               VALUES (?, NULL, 'finding.recorded', ?,
                       ?, ?, NULL,
                       NULL, ?, ?, ?,
                       ?, ?, ?, ?)""",
            (
                values["finding_id"],
                values.get("process_run_id"),
                values.get("project_id"),
                values.get("work_order_id") or values.get("task_id"),
                values.get("file_path"),
                values.get("start_line"),
                values.get("rule_id") or values.get("category"),
                values["severity"],
                values.get("description", ""),
                values.get("recommendation"),
                _now(),
            ),
        )
    except Exception:
        pass

    # If a non-open status was supplied, immediately write a status_changed event
    # so FindingsProjection sees the correct current_status (not the default 'open').
    initial_status = values.get("status", "open")
    if initial_status and initial_status != "open":
        try:
            resolve_security_finding(
                conn, finding_id=values["finding_id"], resolution=initial_status
            )
        except Exception:  # noqa: BLE001
            pass

    # Eagerly refresh findings_current_status projection so read models see the
    # new finding immediately (FindingsProjection.fold_spine is idempotent).
    try:
        from core.projections.findings_projection import FindingsProjection

        FindingsProjection().fold_spine(conn)
    except Exception:  # noqa: BLE001
        pass


def resolve_security_finding(
    conn: sqlite3.Connection, *, finding_id: str, resolution: str | None = None
) -> bool:
    """Record a finding.status_changed event on the security_events spine.

    findings table retired in migration 112 (WO-Y). Checks the spine directly
    (not findings_current_status, which is a projection and may lag). Writes
    the status event via the provided conn to avoid cross-connection writes.
    Returns True if the finding exists and the status event was written.
    """
    import uuid as _uuid
    from datetime import datetime as _dt

    valid_resolutions = {"fixed", "mitigated", "accepted", "false_positive", "resolved", "closed"}
    new_status = resolution if resolution in valid_resolutions else "fixed"
    try:
        row = conn.execute(
            "SELECT event_id FROM security_events"
            " WHERE event_id = ? AND event_kind = 'finding.recorded'",
            (finding_id,),
        ).fetchone()
        if row is None:
            return False
        now = _dt.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
        conn.execute(
            "INSERT INTO security_events"
            " (event_id, parent_event_id, event_kind, body, created_at)"
            " VALUES (?, ?, 'finding.status_changed', ?, ?)",
            (str(_uuid.uuid4()), finding_id, new_status, now),
        )
        return True
    except Exception:
        return False


# record_dashboard_attention() removed: dashboard_attention_items dropped
# migration 139 (WO-AI-SPINE, AD-5) — it was pure duplication of the
# execution_events row each caller already wrote (0 production rows). Dashboard
# attention state is now derived from execution_events in
# core/telemetry/read_models.py, filtered by event_type + outcome_status.


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


def findings_rollup(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    # findings retired in migration 112 (WO-Y); read from findings_current_status spine.
    try:
        return conn.execute("""
            SELECT project_id, file_path, severity, COUNT(*) AS finding_count
            FROM findings_current_status
            GROUP BY project_id, file_path, severity
            ORDER BY finding_count DESC, severity, file_path
            """).fetchall()
    except Exception:
        return []


def dashboard_module_declarations() -> tuple[dict[str, Any], ...]:
    """Return immutable dashboard module declarations for tests and docs."""

    return DASHBOARD_MODULES
