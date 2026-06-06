"""Scoped agent registry and context-packet policy.

Agents are workers, not authority. This module describes the smallest context
they should receive and how their outputs normalize back into SQLite authority.
It does not spawn agents or call external models.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

SCOPED_AGENT_SCHEMA = "dream_studio.scoped_agents.v1"

FORBIDDEN_CONTEXT_BY_DEFAULT: tuple[str, ...] = (
    "full_conversation_history",
    "unrelated_project_details",
    "career_private_data_without_scope",
    "secrets",
    "raw_local_evidence",
    "unneeded_telemetry",
    "all_work_orders",
    "all_user_memories",
    "private_operator_data_outside_scope",
)

DEFAULT_SCOPED_AGENTS: tuple[dict[str, Any], ...] = (
    {
        "agent_id": "implementation_worker",
        "agent_name": "Implementation Worker",
        "purpose": "Apply a bounded implementation slice in declared files only.",
        "allowed_tools": ["filesystem_patch", "focused_tests"],
        "read_scope": ["assigned_files", "local_contract_refs", "focused_tests"],
        "write_scope": ["assigned_files_only"],
        "data_sensitivity_scope": ["product_source"],
        "required_context": ["task_goal", "editable_files", "validation_plan", "rollback_plan"],
        "output_contract": {"changed_files": "list", "validation": "list", "risks": "list"},
        "validation_requirements": ["focused_tests", "diff_review"],
        "approval_boundaries": ["no_unapproved_file_expansion", "no_external_mutation"],
        "risk_level": "medium",
        "max_context_budget": 9000,
        "allowed_data_classes": ["product_source", "public_docs", "test_fixtures"],
    },
    {
        "agent_id": "review_worker",
        "agent_name": "Review Worker",
        "purpose": "Review a scoped change for bugs, regressions, and missing evidence.",
        "allowed_tools": ["read_only_repo_inspection", "focused_tests"],
        "read_scope": ["changed_files", "relevant_tests", "contracts"],
        "write_scope": ["no_writes_read_only_review"],
        "data_sensitivity_scope": ["product_source"],
        "required_context": ["diff_summary", "changed_files", "review_focus"],
        "output_contract": {"findings": "severity_ordered", "residual_risk": "list"},
        "validation_requirements": ["findings_have_file_line_or_evidence"],
        "approval_boundaries": ["read_only_unless_new_work_order_approved"],
        "risk_level": "low",
        "max_context_budget": 7000,
        "allowed_data_classes": ["product_source", "public_docs"],
    },
    {
        "agent_id": "github_repo_intake_reviewer",
        "agent_name": "GitHub Repo Intake Reviewer",
        "purpose": "Evaluate an external repository before Dream Studio adopts ideas or code.",
        "allowed_tools": ["repo_metadata_read", "license_review", "dependency_review"],
        "read_scope": ["selected_repo_metadata", "selected_commit", "public_docs"],
        "write_scope": ["github_repo_evaluations", "github_repo_adoption_decisions"],
        "data_sensitivity_scope": ["public_repo_metadata"],
        "required_context": ["repo_url", "commit_sha", "review_scope"],
        "output_contract": {"decision": "enum", "evidence_refs": "list", "approval_flags": "list"},
        "validation_requirements": ["license_status", "security_status", "overlap_review"],
        "approval_boundaries": ["no_code_copy_without_license_and_operator_approval"],
        "risk_level": "medium",
        "max_context_budget": 8000,
        "allowed_data_classes": ["public_repo_metadata", "public_docs"],
    },
)


def scoped_agent_registry(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Return default and recorded scoped-agent declarations."""

    recorded = _recorded_agents(conn) if conn is not None else []
    agents_by_id = {agent["agent_id"]: dict(agent) for agent in DEFAULT_SCOPED_AGENTS}
    for agent in recorded:
        agents_by_id[agent["agent_id"]] = {**agents_by_id.get(agent["agent_id"], {}), **agent}
    agents = [agents_by_id[key] for key in sorted(agents_by_id)]
    return {
        "schema": SCOPED_AGENT_SCHEMA,
        "model_name": "dream_studio_scoped_agent_registry",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "derived_view": True,
        "primary_authority": False,
        "agent_is_authority": False,
        "dream_studio_remains_canonical": True,
        "db_write_authorized": False,
        "execution_authorized": False,
        "agent_count": len(agents),
        "agents": agents,
        "forbidden_context_by_default": list(FORBIDDEN_CONTEXT_BY_DEFAULT),
        "source_tables": [
            "agent_registry_records",
            "agent_context_scope_policies",
            "agent_invocations",
        ],
    }


def scoped_context_packet(
    conn: sqlite3.Connection,
    *,
    agent_id: str,
    task_summary: str,
    project_id: str | None = None,
    requested_data_classes: list[str] | None = None,
    career_scope_approved: bool = False,
) -> dict[str, Any]:
    """Preview a scoped agent context packet without execution or persistence."""

    registry = scoped_agent_registry(conn)
    agents = {agent["agent_id"]: agent for agent in registry["agents"]}
    if agent_id not in agents:
        raise ValueError(f"unknown scoped agent: {agent_id}")
    agent = agents[agent_id]
    # Career Ops has been removed; career data is never enabled and is always
    # excluded. The career_scope_approved parameter is retained for API/packet
    # shape compatibility but no longer grants any access.
    excluded = list(FORBIDDEN_CONTEXT_BY_DEFAULT)
    included_context = {
        "task_summary": task_summary,
        "project_id": project_id,
        "agent_id": agent_id,
        "required_context": agent.get("required_context", []),
        "read_scope": agent.get("read_scope", []),
        "write_scope": agent.get("write_scope", []),
        "allowed_tools": agent.get("allowed_tools", []),
        "career_private_scope": "excluded",
    }
    return {
        "schema": "dream_studio.scoped_agent_context_packet.v1",
        "model_name": "dream_studio_scoped_agent_context_packet",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "derived_view": True,
        "primary_authority": False,
        "agent_is_authority": False,
        "execution_authorized": False,
        "db_write_authorized": False,
        "agent_id": agent_id,
        "project_id": project_id,
        "included_context": included_context,
        "excluded_context": excluded,
        "max_context_budget": agent.get("max_context_budget"),
        "forbidden_context_by_default": list(FORBIDDEN_CONTEXT_BY_DEFAULT),
        "result_normalization_targets": [
            "agent_invocations",
            "decision_records",
            "validation_results",
            "artifact_records",
        ],
    }


def normalize_agent_result(
    *,
    agent_id: str,
    result_status: str,
    payload: dict[str, Any] | None = None,
    project_id: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Return the normalized authority shape for an agent result."""

    return {
        "schema": "dream_studio.normalized_agent_result.v1",
        "agent_id": agent_id,
        "project_id": project_id,
        "task_id": task_id,
        "result_status": result_status,
        "agent_is_authority": False,
        "normalized_target_tables": [
            "agent_invocations",
            "decision_records",
            "validation_results",
            "artifact_records",
        ],
        "result_payload": payload or {},
        "requires_authority_write": True,
    }


def validate_scoped_agent_registry(registry: dict[str, Any] | None = None) -> list[str]:
    payload = registry or scoped_agent_registry()
    errors: list[str] = []
    if payload.get("agent_is_authority") is not False:
        errors.append("agents must not be authority")
    for agent in payload.get("agents", []):
        agent_id = str(agent.get("agent_id") or "")
        for key in (
            "purpose",
            "allowed_tools",
            "read_scope",
            "write_scope",
            "data_sensitivity_scope",
            "required_context",
            "output_contract",
            "validation_requirements",
            "approval_boundaries",
            "risk_level",
            "max_context_budget",
            "allowed_data_classes",
        ):
            if agent.get(key) in (None, "", [], {}):
                errors.append(f"agent {agent_id} missing {key}")
        forbidden = set(agent.get("forbidden_context", []))
        if not forbidden and set(FORBIDDEN_CONTEXT_BY_DEFAULT).isdisjoint(forbidden):
            # Default agents inherit the global forbidden list, so this remains advisory.
            pass
    return errors


def _recorded_agents(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(conn, "agent_registry_records"):
        return []
    rows = conn.execute("""
        SELECT agent_id, agent_name, purpose, allowed_tools_json, read_scope_json,
               write_scope_json, data_sensitivity_scope_json, required_context_json,
               forbidden_context_json, output_contract_json, validation_requirements_json,
               approval_boundaries_json, risk_level, max_context_budget,
               allowed_data_classes_json, result_schema_json
        FROM agent_registry_records
        WHERE enabled = 1
        ORDER BY agent_id
        """).fetchall()
    parsed: list[dict[str, Any]] = []
    for row in rows:
        data = dict(row)
        parsed.append(
            {
                "agent_id": data["agent_id"],
                "agent_name": data["agent_name"],
                "purpose": data["purpose"],
                "allowed_tools": _decode(data["allowed_tools_json"], []),
                "read_scope": _decode(data["read_scope_json"], []),
                "write_scope": _decode(data["write_scope_json"], []),
                "data_sensitivity_scope": _decode(data["data_sensitivity_scope_json"], []),
                "required_context": _decode(data["required_context_json"], []),
                "forbidden_context": _decode(data["forbidden_context_json"], []),
                "output_contract": _decode(data["output_contract_json"], {}),
                "validation_requirements": _decode(data["validation_requirements_json"], []),
                "approval_boundaries": _decode(data["approval_boundaries_json"], []),
                "risk_level": data["risk_level"],
                "max_context_budget": data["max_context_budget"],
                "allowed_data_classes": _decode(data["allowed_data_classes_json"], []),
                "result_schema": _decode(data["result_schema_json"], {}),
            }
        )
    return parsed


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return bool(row)


def _decode(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default
