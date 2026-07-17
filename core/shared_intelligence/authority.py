"""SQLite-first shared intelligence authority records.

These helpers deliberately write to an injected SQLite connection. They do not
open the operator's live DB by themselves, which keeps tests and future
rehearsals bounded to explicit temp or approved runtime connections.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

REQUIRED_SHARED_INTELLIGENCE_TABLES: frozenset[str] = frozenset(
    {
        "adapter_authority_profiles",
        # capability_route_records: dropped migration 147 (WO-SCHEMALEAN) — dead
        # persist=False writer; the recommendation preview is kept and does not
        # require the table.
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


# record_capability_route: removed migration 147 (WO-SCHEMALEAN) — dead persist=False
# writer for the dropped capability_route_records table (recommend_capability_route only
# ever ran with persist=False in production).


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


# _select_records / _table_has_column / _int_bool: removed migration 147
# (WO-SCHEMALEAN) — only record_capability_route (removed) used them.


def _json(value: Any, default: Any) -> str:
    if value is None:
        value = default
    return json.dumps(value, sort_keys=True)
