"""Normalize adapter outputs into SQLite shared-intelligence result records."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from typing import Any

from core.shared_intelligence.authority import (
    record_adapter_result,
    require_shared_intelligence_tables,
)

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
    packet_id: str | None = None,
    project_id: str | None = None,
    milestone_id: str | None = None,
    task_id: str | None = None,
    process_run_id: str | None = None,
) -> dict[str, Any]:
    """Normalize and persist an adapter result into SQLite authority."""

    require_shared_intelligence_tables(conn)
    if not _adapter_exists(conn, adapter_id):
        raise ValueError(f"unknown adapter_id: {adapter_id}")
    normalized = normalize_adapter_result_payload(raw_result)
    record_adapter_result(
        conn,
        result_id=result_id,
        adapter_id=adapter_id,
        packet_id=packet_id,
        project_id=project_id,
        milestone_id=milestone_id,
        task_id=task_id,
        process_run_id=process_run_id,
        **normalized,
    )
    return adapter_result_summary(conn, project_id=project_id)


def adapter_result_summary(
    conn: sqlite3.Connection,
    *,
    project_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Return a read-only summary of normalized adapter results."""

    require_shared_intelligence_tables(conn)
    where = ""
    params: list[Any] = []
    if project_id is not None:
        where = "WHERE project_id = ?"
        params.append(project_id)
    rows = conn.execute(
        f"""
        SELECT *
        FROM adapter_result_records
        {where}
        ORDER BY created_at DESC, result_id DESC
        LIMIT ?
        """,
        (*params, max(1, min(int(limit), 100))),
    ).fetchall()
    results = [_decode_result(row) for row in rows]
    return {
        "model_name": "shared_intelligence_adapter_result_summary",
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "source_tables": ["adapter_result_records"],
        "project_id": project_id,
        "result_count": len(results),
        "adapter_counts": dict(sorted(Counter(result["adapter_id"] for result in results).items())),
        "result_type_counts": dict(
            sorted(Counter(result["result_type"] for result in results).items())
        ),
        "status_counts": dict(
            sorted(Counter(result["normalized_status"] for result in results).items())
        ),
        "results": results,
        "adapter_output_is_authority": False,
        "empty_state": "No normalized adapter results recorded for the selected scope.",
    }


def _adapter_exists(conn: sqlite3.Connection, adapter_id: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM adapter_authority_profiles WHERE adapter_id = ?",
            (adapter_id,),
        ).fetchone()
        is not None
    )


def _decode_result(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["decision_refs"] = _loads(result.pop("decision_refs_json"), [])
    result["code_change_refs"] = _loads(result.pop("code_change_refs_json"), [])
    result["evidence_refs"] = _loads(result.pop("evidence_refs_json"), [])
    result["validation_refs"] = _loads(result.pop("validation_refs_json"), [])
    result["research_refs"] = _loads(result.pop("research_refs_json"), [])
    result["risk_refs"] = _loads(result.pop("risk_refs_json"), [])
    result["artifact_refs"] = _loads(result.pop("artifact_refs_json"), [])
    result["outcome_refs"] = _loads(result.pop("outcome_refs_json"), [])
    result["payload"] = _loads(result.pop("payload_json"), {})
    return result


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def _loads(raw: str | None, default: Any) -> Any:
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default
