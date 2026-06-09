"""SQLite-first shared intelligence authority records.

These helpers deliberately write to an injected SQLite connection. They do not
open the operator's live DB by themselves, which keeps tests and future
rehearsals bounded to explicit temp or approved runtime connections.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from typing import Any

REQUIRED_SHARED_INTELLIGENCE_TABLES: frozenset[str] = frozenset(
    {
        "artifact_authority_records",
        "learning_event_records",
        "hardening_candidate_records",
        "adapter_authority_profiles",
        "model_provider_profiles",
        "shared_context_packets",
        "adapter_result_records",
        "capability_route_records",
    }
)


def require_shared_intelligence_tables(conn: sqlite3.Connection) -> None:
    """Raise if the shared intelligence schema has not been migrated."""

    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN "
        f"({','.join('?' for _ in REQUIRED_SHARED_INTELLIGENCE_TABLES)})",
        tuple(sorted(REQUIRED_SHARED_INTELLIGENCE_TABLES)),
    ).fetchall()
    found = {str(row[0]) for row in rows}
    missing = sorted(REQUIRED_SHARED_INTELLIGENCE_TABLES - found)
    if missing:
        raise RuntimeError(f"shared intelligence schema missing tables: {missing}")


def record_artifact_authority(conn: sqlite3.Connection, **values: Any) -> None:
    require_shared_intelligence_tables(conn)
    conn.execute(
        """
        INSERT OR REPLACE INTO artifact_authority_records (
            record_id, record_type, project_id, milestone_id, task_id,
            process_run_id, source_path, source_hash, authority_status,
            file_is_export, human_export_path, payload_json, source_refs_json,
            evidence_refs_json, supersedes_record_id, updated_at
        ) VALUES (
            :record_id, :record_type, :project_id, :milestone_id, :task_id,
            :process_run_id, :source_path, :source_hash, :authority_status,
            :file_is_export, :human_export_path, :payload_json,
            :source_refs_json, :evidence_refs_json, :supersedes_record_id,
            datetime('now')
        )
        """,
        {
            "record_id": values["record_id"],
            "record_type": values["record_type"],
            "project_id": values.get("project_id"),
            "milestone_id": values.get("milestone_id"),
            "task_id": values.get("task_id"),
            "process_run_id": values.get("process_run_id"),
            "source_path": values.get("source_path"),
            "source_hash": values.get("source_hash"),
            "authority_status": values.get("authority_status", "canonical"),
            "file_is_export": _int_bool(values.get("file_is_export", True)),
            "human_export_path": values.get("human_export_path"),
            "payload_json": _json(values.get("payload"), {}),
            "source_refs_json": _json(values.get("source_refs"), []),
            "evidence_refs_json": _json(values.get("evidence_refs"), []),
            "supersedes_record_id": values.get("supersedes_record_id"),
        },
    )


def record_learning_event(conn: sqlite3.Connection, **values: Any) -> None:
    # Superseded by Phase 19 friction/gap pipeline (WO-LEARN). The pipeline
    # captures learning signals automatically via FrictionSignalHarvester +
    # GapClassifier at end_session(). This function writes to
    # learning_event_records (Shared Intelligence subsystem) which is
    # separate from ds_friction_signals; it remains callable for legacy
    # SI workflows but should not be wired into the Phase 19 loop.
    require_shared_intelligence_tables(conn)
    conn.execute(
        """
        INSERT OR REPLACE INTO learning_event_records (
            learning_event_id, project_id, milestone_id, task_id,
            process_run_id, component_type, component_id, event_class,
            severity, summary, observed_pattern, root_cause, remediation_hint,
            recurrence_key, promotion_status, source_refs_json,
            evidence_refs_json, metadata_json
        ) VALUES (
            :learning_event_id, :project_id, :milestone_id, :task_id,
            :process_run_id, :component_type, :component_id, :event_class,
            :severity, :summary, :observed_pattern, :root_cause,
            :remediation_hint, :recurrence_key, :promotion_status,
            :source_refs_json, :evidence_refs_json, :metadata_json
        )
        """,
        {
            "learning_event_id": values["learning_event_id"],
            "project_id": values.get("project_id"),
            "milestone_id": values.get("milestone_id"),
            "task_id": values.get("task_id"),
            "process_run_id": values.get("process_run_id"),
            "component_type": values.get("component_type"),
            "component_id": values.get("component_id"),
            "event_class": values["event_class"],
            "severity": values.get("severity", "info"),
            "summary": values["summary"],
            "observed_pattern": values.get("observed_pattern"),
            "root_cause": values.get("root_cause"),
            "remediation_hint": values.get("remediation_hint"),
            "recurrence_key": values.get("recurrence_key"),
            "promotion_status": values.get("promotion_status", "observed"),
            "source_refs_json": _json(values.get("source_refs"), []),
            "evidence_refs_json": _json(values.get("evidence_refs"), []),
            "metadata_json": _json(values.get("metadata"), {}),
        },
    )


def record_hardening_candidate(conn: sqlite3.Connection, **values: Any) -> None:
    require_shared_intelligence_tables(conn)
    conn.execute(
        """
        INSERT OR REPLACE INTO hardening_candidate_records (
            candidate_id, learning_event_id, component_type, component_id,
            current_version, proposed_version, hardening_type, status,
            validation_plan_json, recurrence_check_json, rollback_plan,
            source_refs_json, evidence_refs_json, updated_at
        ) VALUES (
            :candidate_id, :learning_event_id, :component_type, :component_id,
            :current_version, :proposed_version, :hardening_type, :status,
            :validation_plan_json, :recurrence_check_json, :rollback_plan,
            :source_refs_json, :evidence_refs_json, datetime('now')
        )
        """,
        {
            "candidate_id": values["candidate_id"],
            "learning_event_id": values.get("learning_event_id"),
            "component_type": values["component_type"],
            "component_id": values["component_id"],
            "current_version": values.get("current_version"),
            "proposed_version": values.get("proposed_version"),
            "hardening_type": values["hardening_type"],
            "status": values.get("status", "candidate"),
            "validation_plan_json": _json(values.get("validation_plan"), []),
            "recurrence_check_json": _json(values.get("recurrence_check"), {}),
            "rollback_plan": values.get("rollback_plan"),
            "source_refs_json": _json(values.get("source_refs"), []),
            "evidence_refs_json": _json(values.get("evidence_refs"), []),
        },
    )


def record_adapter_authority_profile(conn: sqlite3.Connection, **values: Any) -> None:
    require_shared_intelligence_tables(conn)
    conn.execute(
        """
        INSERT OR REPLACE INTO adapter_authority_profiles (
            adapter_id, adapter_type, adapter_name, authority_role,
            owns_source_of_truth, config_projection_path,
            supported_context_packets_json, supported_result_types_json,
            stale_detection_policy_json, source_refs_json, evidence_refs_json,
            updated_at
        ) VALUES (
            :adapter_id, :adapter_type, :adapter_name, :authority_role,
            0, :config_projection_path, :supported_context_packets_json,
            :supported_result_types_json, :stale_detection_policy_json,
            :source_refs_json, :evidence_refs_json, datetime('now')
        )
        """,
        {
            "adapter_id": values["adapter_id"],
            "adapter_type": values["adapter_type"],
            "adapter_name": values["adapter_name"],
            "authority_role": values.get("authority_role", "projection"),
            "config_projection_path": values.get("config_projection_path"),
            "supported_context_packets_json": _json(values.get("supported_context_packets"), []),
            "supported_result_types_json": _json(values.get("supported_result_types"), []),
            "stale_detection_policy_json": _json(values.get("stale_detection_policy"), {}),
            "source_refs_json": _json(values.get("source_refs"), []),
            "evidence_refs_json": _json(values.get("evidence_refs"), []),
        },
    )


def record_model_provider_profile(conn: sqlite3.Connection, **values: Any) -> None:
    require_shared_intelligence_tables(conn)
    conn.execute(
        """
        INSERT OR REPLACE INTO model_provider_profiles (
            model_profile_id, provider, model_id, capability_tags_json,
            context_limit_tokens, cost_profile_json, token_behavior_json,
            output_quality_json, failure_modes_json, best_use_patterns_json,
            source_refs_json, evidence_refs_json, updated_at
        ) VALUES (
            :model_profile_id, :provider, :model_id, :capability_tags_json,
            :context_limit_tokens, :cost_profile_json, :token_behavior_json,
            :output_quality_json, :failure_modes_json, :best_use_patterns_json,
            :source_refs_json, :evidence_refs_json, datetime('now')
        )
        """,
        {
            "model_profile_id": values["model_profile_id"],
            "provider": values["provider"],
            "model_id": values["model_id"],
            "capability_tags_json": _json(values.get("capability_tags"), []),
            "context_limit_tokens": values.get("context_limit_tokens"),
            "cost_profile_json": _json(values.get("cost_profile"), {}),
            "token_behavior_json": _json(values.get("token_behavior"), {}),
            "output_quality_json": _json(values.get("output_quality"), {}),
            "failure_modes_json": _json(values.get("failure_modes"), []),
            "best_use_patterns_json": _json(values.get("best_use_patterns"), []),
            "source_refs_json": _json(values.get("source_refs"), []),
            "evidence_refs_json": _json(values.get("evidence_refs"), []),
        },
    )


def record_shared_context_packet(conn: sqlite3.Connection, **values: Any) -> None:
    require_shared_intelligence_tables(conn)
    conn.execute(
        """
        INSERT OR REPLACE INTO shared_context_packets (
            packet_id, adapter_id, project_id, milestone_id, task_id,
            process_run_id, packet_type, packet_status, source_authority,
            model_private_memory_required, payload_json, source_refs_json,
            evidence_refs_json
        ) VALUES (
            :packet_id, :adapter_id, :project_id, :milestone_id, :task_id,
            :process_run_id, :packet_type, :packet_status, 'sqlite', 0,
            :payload_json, :source_refs_json, :evidence_refs_json
        )
        """,
        {
            "packet_id": values["packet_id"],
            "adapter_id": values["adapter_id"],
            "project_id": values.get("project_id"),
            "milestone_id": values.get("milestone_id"),
            "task_id": values.get("task_id"),
            "process_run_id": values.get("process_run_id"),
            "packet_type": values["packet_type"],
            "packet_status": values.get("packet_status", "generated"),
            "payload_json": _json(values.get("payload"), {}),
            "source_refs_json": _json(values.get("source_refs"), []),
            "evidence_refs_json": _json(values.get("evidence_refs"), []),
        },
    )


def record_adapter_result(conn: sqlite3.Connection, **values: Any) -> None:
    require_shared_intelligence_tables(conn)
    conn.execute(
        """
        INSERT OR REPLACE INTO adapter_result_records (
            result_id, adapter_id, packet_id, project_id, milestone_id,
            task_id, process_run_id, result_type, normalized_status,
            decision_refs_json, code_change_refs_json, evidence_refs_json,
            validation_refs_json, research_refs_json, risk_refs_json,
            artifact_refs_json, outcome_refs_json, payload_json
        ) VALUES (
            :result_id, :adapter_id, :packet_id, :project_id, :milestone_id,
            :task_id, :process_run_id, :result_type, :normalized_status,
            :decision_refs_json, :code_change_refs_json, :evidence_refs_json,
            :validation_refs_json, :research_refs_json, :risk_refs_json,
            :artifact_refs_json, :outcome_refs_json, :payload_json
        )
        """,
        {
            "result_id": values["result_id"],
            "adapter_id": values["adapter_id"],
            "packet_id": values.get("packet_id"),
            "project_id": values.get("project_id"),
            "milestone_id": values.get("milestone_id"),
            "task_id": values.get("task_id"),
            "process_run_id": values.get("process_run_id"),
            "result_type": values["result_type"],
            "normalized_status": values["normalized_status"],
            "decision_refs_json": _json(values.get("decision_refs"), []),
            "code_change_refs_json": _json(values.get("code_change_refs"), []),
            "evidence_refs_json": _json(values.get("evidence_refs"), []),
            "validation_refs_json": _json(values.get("validation_refs"), []),
            "research_refs_json": _json(values.get("research_refs"), []),
            "risk_refs_json": _json(values.get("risk_refs"), []),
            "artifact_refs_json": _json(values.get("artifact_refs"), []),
            "outcome_refs_json": _json(values.get("outcome_refs"), []),
            "payload_json": _json(values.get("payload"), {}),
        },
    )


def record_capability_route(conn: sqlite3.Connection, **values: Any) -> None:
    require_shared_intelligence_tables(conn)
    conn.execute(
        """
        INSERT OR REPLACE INTO capability_route_records (
            capability_route_id, project_id, milestone_id, task_id,
            process_run_id, task_class, selected_adapter_id,
            selected_model_profile_id, route_basis_json, risk_level,
            cost_sensitivity, validation_required, operator_approval_required,
            source_refs_json, evidence_refs_json
        ) VALUES (
            :capability_route_id, :project_id, :milestone_id, :task_id,
            :process_run_id, :task_class, :selected_adapter_id,
            :selected_model_profile_id, :route_basis_json, :risk_level,
            :cost_sensitivity, :validation_required,
            :operator_approval_required, :source_refs_json, :evidence_refs_json
        )
        """,
        {
            "capability_route_id": values["capability_route_id"],
            "project_id": values.get("project_id"),
            "milestone_id": values.get("milestone_id"),
            "task_id": values.get("task_id"),
            "process_run_id": values.get("process_run_id"),
            "task_class": values["task_class"],
            "selected_adapter_id": values.get("selected_adapter_id"),
            "selected_model_profile_id": values.get("selected_model_profile_id"),
            "route_basis_json": _json(values.get("route_basis"), {}),
            "risk_level": values.get("risk_level", "medium"),
            "cost_sensitivity": values.get("cost_sensitivity", "medium"),
            "validation_required": _int_bool(values.get("validation_required", True)),
            "operator_approval_required": _int_bool(
                values.get("operator_approval_required", False)
            ),
            "source_refs_json": _json(values.get("source_refs"), []),
            "evidence_refs_json": _json(values.get("evidence_refs"), []),
        },
    )


def build_adapter_context_packet(
    conn: sqlite3.Connection,
    *,
    adapter_id: str,
    project_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Build an adapter-neutral context packet from SQLite authority records."""

    require_shared_intelligence_tables(conn)
    adapter = conn.execute(
        """
        SELECT adapter_id, adapter_type, adapter_name, authority_role,
               owns_source_of_truth
        FROM adapter_authority_profiles
        WHERE adapter_id = ?
        """,
        (adapter_id,),
    ).fetchone()
    if adapter is None:
        raise ValueError(f"unknown adapter_id: {adapter_id}")

    return {
        "packet_schema": "dream_studio.shared_context.v1",
        "adapter": dict(adapter),
        "project_id": project_id,
        "source_authority": "sqlite",
        "model_private_memory_required": False,
        "artifact_authority_records": _select_records(
            conn,
            "artifact_authority_records",
            project_id=project_id,
            order_by="updated_at",
            limit=limit,
        ),
        "learning_events": _select_records(
            conn,
            "learning_event_records",
            project_id=project_id,
            order_by="created_at",
            limit=limit,
        ),
        "hardening_candidates": _select_records(
            conn,
            "hardening_candidate_records",
            project_id=None,
            order_by="updated_at",
            limit=limit,
        ),
    }


def _select_records(
    conn: sqlite3.Connection,
    table: str,
    *,
    project_id: str | None,
    order_by: str,
    limit: int,
) -> list[dict[str, Any]]:
    where = ""
    params: list[Any] = []
    if project_id is not None and _table_has_column(conn, table, "project_id"):
        where = "WHERE project_id = ?"
        params.append(project_id)
    params.append(max(1, min(int(limit), 100)))
    return [
        dict(row)
        for row in conn.execute(
            f"SELECT * FROM {table} {where} ORDER BY {order_by} DESC LIMIT ?",
            params,
        ).fetchall()
    ]


def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(str(row[1]) == column for row in conn.execute(f"PRAGMA table_info({table})"))


def _json(value: Any, default: Any) -> str:
    if value is None:
        value = default
    return json.dumps(value, sort_keys=True)


def _int_bool(value: Any) -> int:
    return 1 if bool(value) else 0
