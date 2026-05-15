"""Capability Center read model over skills, workflows, agents, controls, and evaluations."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from core.production_readiness import production_readiness_control_catalog
from core.shared_intelligence.expert_workflows import expert_workflow_catalog
from core.shared_intelligence.scoped_agents import scoped_agent_registry
from core.shared_intelligence.skill_versioning import skill_version_evaluation_report

CAPABILITY_CENTER_SCHEMA = "dream_studio.capability_center.v1"

CAPABILITY_SOURCE_TABLES: tuple[str, ...] = (
    "capability_center_records",
    "skill_invocations",
    "workflow_invocations",
    "agent_invocations",
    "hardening_candidate_records",
    "capability_route_records",
    "production_readiness_control_results",
)


def capability_center_summary(
    conn: sqlite3.Connection, *, project_id: str | None = None, repo_root: Any | None = None
) -> dict[str, Any]:
    """Return dashboard-ready Capability Center sections from authority tables."""

    source_status = _source_status(conn)
    workflows = expert_workflow_catalog(project_id=project_id)
    agents = scoped_agent_registry(conn)
    versioning = skill_version_evaluation_report(conn, limit=100)
    controls = _control_summary(repo_root)
    recorded = _recorded_capabilities(conn)
    return {
        "schema": CAPABILITY_CENTER_SCHEMA,
        "model_name": "dream_studio_capability_center",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": project_id,
        "derived_view": True,
        "primary_authority": False,
        "db_write_authorized": False,
        "execution_authorized": False,
        "authority_note": "Capability Center reads Dream Studio authority; dashboard state is not authority.",
        "source_tables": list(CAPABILITY_SOURCE_TABLES),
        "source_status": source_status,
        "sections": {
            "skills": _skills_section(conn, recorded),
            "workflows": _workflows_section(conn, workflows),
            "agents": _agents_section(conn, agents),
            "controls": controls,
            "evaluations": _evaluations_section(versioning),
            "hardening_candidates": _hardening_section(conn),
        },
        "empty_state": "Capability Center has no recorded invocations or evaluations yet.",
    }


def validate_capability_center_summary(summary: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if summary.get("derived_view") is not True:
        errors.append("derived_view must be true")
    if summary.get("primary_authority") is not False:
        errors.append("primary_authority must be false")
    for section in (
        "skills",
        "workflows",
        "agents",
        "controls",
        "evaluations",
        "hardening_candidates",
    ):
        if section not in summary.get("sections", {}):
            errors.append(f"missing capability center section: {section}")
    return errors


def _skills_section(conn: sqlite3.Connection, recorded: list[dict[str, Any]]) -> dict[str, Any]:
    invocation_counts = _component_counts(conn, "skill_invocations", "skill_id")
    recorded_skills = [item for item in recorded if item.get("component_type") == "skill"]
    skill_ids = sorted(set(invocation_counts) | {item["component_id"] for item in recorded_skills})
    items = [
        {
            "skill_id": skill_id,
            "invocation_count": invocation_counts.get(skill_id, 0),
            "evaluation_status": _recorded_status(recorded_skills, skill_id),
            "score_available": _recorded_score(recorded_skills, skill_id) is not None,
        }
        for skill_id in skill_ids
    ]
    return {
        "count": len(items),
        "items": items,
        "status": "available" if items else "unavailable",
        "unavailable_reason": (
            None if items else "No skill invocations or capability records exist."
        ),
    }


def _workflows_section(conn: sqlite3.Connection, workflows: dict[str, Any]) -> dict[str, Any]:
    invocation_counts = _component_counts(conn, "workflow_invocations", "workflow_id")
    items = []
    for workflow in workflows.get("workflows", []):
        workflow_id = workflow["workflow_id"]
        items.append(
            {
                "workflow_id": workflow_id,
                "purpose": workflow.get("purpose"),
                "invocation_count": invocation_counts.get(workflow_id, 0),
                "validation_requirements": workflow.get("validation_requirements", []),
                "scorecards": workflow.get("scoring_rubric", []),
                "evaluation_status": (
                    "partial" if invocation_counts.get(workflow_id) else "unavailable"
                ),
                "missing_evidence_behavior": "unavailable_with_reason",
            }
        )
    return {"count": len(items), "items": items}


def _agents_section(conn: sqlite3.Connection, agents: dict[str, Any]) -> dict[str, Any]:
    invocation_counts = _component_counts(conn, "agent_invocations", "agent_id")
    items = []
    for agent in agents.get("agents", []):
        agent_id = agent["agent_id"]
        items.append(
            {
                "agent_id": agent_id,
                "purpose": agent.get("purpose"),
                "invocation_count": invocation_counts.get(agent_id, 0),
                "allowed_tools": agent.get("allowed_tools", []),
                "read_scope": agent.get("read_scope", []),
                "write_scope": agent.get("write_scope", []),
                "agent_is_authority": False,
                "evaluation_status": "unavailable",
            }
        )
    return {
        "count": len(items),
        "items": items,
        "context_scoping_policy": agents.get("forbidden_context_by_default", []),
    }


def _control_summary(repo_root: Any | None) -> dict[str, Any]:
    if repo_root is None:
        return {
            "count": 0,
            "status": "unavailable",
            "reason": "Repo root was not supplied for control catalog generation.",
        }
    catalog = production_readiness_control_catalog(repo_root=repo_root)
    return {
        "count": catalog["control_count"],
        "families": catalog["control_families"],
        "status": "available",
        "source": "production_readiness_control_catalog",
    }


def _evaluations_section(versioning: dict[str, Any]) -> dict[str, Any]:
    return {
        "count": versioning.get("candidate_count", 0),
        "status_counts": versioning.get("evaluation_status_counts", {}),
        "ready_for_operator_approval": versioning.get("ready_for_operator_approval", []),
        "manual_review_required": versioning.get("manual_review_required", []),
        "scorecards_are_evidence_backed": True,
    }


def _hardening_section(conn: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists(conn, "hardening_candidate_records"):
        return {"count": 0, "status": "unavailable", "items": []}
    rows = conn.execute("""
        SELECT candidate_id, component_type, component_id, hardening_type, status,
               validation_plan_json, evidence_refs_json
        FROM hardening_candidate_records
        ORDER BY updated_at DESC
        LIMIT 50
        """).fetchall()
    return {
        "count": len(rows),
        "status": "available" if rows else "empty",
        "items": [
            {
                "candidate_id": row["candidate_id"],
                "component_type": row["component_type"],
                "component_id": row["component_id"],
                "hardening_type": row["hardening_type"],
                "status": row["status"],
                "validation_plan": _decode(row["validation_plan_json"], []),
                "evidence_refs": _decode(row["evidence_refs_json"], []),
            }
            for row in rows
        ],
    }


def _recorded_capabilities(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(conn, "capability_center_records"):
        return []
    rows = conn.execute("""
        SELECT component_type, component_id, name, purpose, evaluation_status,
               evaluation_score, known_gaps_json, evidence_refs_json
        FROM capability_center_records
        ORDER BY component_type, component_id
        """).fetchall()
    return [dict(row) for row in rows]


def _component_counts(conn: sqlite3.Connection, table: str, id_col: str) -> dict[str, int]:
    if not _table_exists(conn, table):
        return {}
    rows = conn.execute(
        f"SELECT {id_col}, COUNT(*) AS count FROM {table} GROUP BY {id_col}"
    ).fetchall()
    return {str(row[id_col]): int(row["count"]) for row in rows}


def _recorded_status(records: list[dict[str, Any]], component_id: str) -> str:
    for record in records:
        if record["component_id"] == component_id:
            return record["evaluation_status"]
    return "unavailable"


def _recorded_score(records: list[dict[str, Any]], component_id: str) -> float | None:
    for record in records:
        if record["component_id"] == component_id:
            return record["evaluation_score"]
    return None


def _source_status(conn: sqlite3.Connection) -> dict[str, Any]:
    missing = [table for table in CAPABILITY_SOURCE_TABLES if not _table_exists(conn, table)]
    return {
        "status": "available" if not missing else "partial",
        "missing_tables": missing,
    }


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
