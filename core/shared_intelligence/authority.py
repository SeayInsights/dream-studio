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
        "adapter_authority_profiles",
        "capability_route_records",
        # artifact_authority_records: dropped migration 131
        # learning_event_records: dropped migration 131
        # hardening_candidate_records: dropped migration 131
        # model_provider_profiles: dropped migration 131
        # shared_context_packets: dropped migration 131
        # adapter_result_records: dropped migration 131
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
        # artifact_authority_records: dropped migration 131
        # learning_event_records: dropped migration 131
        # hardening_candidate_records: dropped migration 131
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
