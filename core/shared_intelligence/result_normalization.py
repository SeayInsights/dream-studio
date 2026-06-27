"""Normalize adapter outputs into shared-intelligence result records.

adapter_result_records dropped migration 131. record_normalized_adapter_result
is now a no-op stub; adapter_result_summary returns an empty result.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from core.shared_intelligence.authority import require_shared_intelligence_tables

STATUS_ALIASES: dict[str, str] = {
    "ok": "validated",
    "success": "validated",
    "passed": "validated",
    "pass": "validated",
    "done": "completed",
    "complete": "completed",
    "failed": "failed",
    "fail": "failed",
    "blocked": "blocked",
    "partial": "partial",
}


def normalize_adapter_result_payload(raw_result: dict[str, Any]) -> dict[str, Any]:
    """Normalize adapter output into Dream Studio result fields."""

    result_type = str(raw_result.get("result_type") or raw_result.get("type") or "unknown")
    raw_status = str(raw_result.get("normalized_status") or raw_result.get("status") or "completed")
    normalized_status = STATUS_ALIASES.get(raw_status.lower(), raw_status.lower())
    return {
        "result_type": result_type,
        "normalized_status": normalized_status,
        "decision_refs": _list(raw_result.get("decision_refs") or raw_result.get("decisions")),
        "code_change_refs": _list(
            raw_result.get("code_change_refs") or raw_result.get("code_changes")
        ),
        "evidence_refs": _list(raw_result.get("evidence_refs") or raw_result.get("evidence")),
        "validation_refs": _list(
            raw_result.get("validation_refs") or raw_result.get("validations")
        ),
        "research_refs": _list(raw_result.get("research_refs") or raw_result.get("research")),
        "risk_refs": _list(raw_result.get("risk_refs") or raw_result.get("risks")),
        "artifact_refs": _list(raw_result.get("artifact_refs") or raw_result.get("artifacts")),
        "outcome_refs": _list(raw_result.get("outcome_refs") or raw_result.get("outcomes")),
        "payload": {
            "normalization_schema": "dream_studio.adapter_result.v1",
            "raw_result": raw_result,
            "adapter_output_is_authority": False,
        },
    }


def record_normalized_adapter_result(
    conn: sqlite3.Connection,
    *,
    result_id: str,
    adapter_id: str,
    raw_result: dict[str, Any],
    project_id: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """No-op stub — adapter_result_records dropped migration 131."""

    require_shared_intelligence_tables(conn)
    return adapter_result_summary(conn, project_id=project_id)


def adapter_result_summary(
    conn: sqlite3.Connection,
    *,
    project_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Return an empty summary — adapter_result_records dropped migration 131."""

    require_shared_intelligence_tables(conn)
    return {
        "model_name": "shared_intelligence_adapter_result_summary",
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "source_tables": ["adapter_result_records"],
        "source_status": {"status": "table_dropped", "migration": 131},
        "project_id": project_id,
        "result_count": 0,
        "adapter_counts": {},
        "result_type_counts": {},
        "status_counts": {},
        "results": [],
        "adapter_output_is_authority": False,
        "empty_state": "adapter_result_records dropped migration 131.",
    }


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]
