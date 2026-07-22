"""Validation state, attention items, component index, and surface availability.

WO-GF-API-ROUTES: split out of project_helpers.py.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from projections.api.routes.sqlite_schema import object_exists, table_columns

from .project_helpers_utils import _json_list

# ── Validation / attention ───────────────────────────────────────────────────


def _recent_validation_state(conn: sqlite3.Connection, project_id: str) -> dict[str, Any]:
    if not object_exists(conn, "validation_results"):
        return {
            "classification": "unavailable",
            "reason": "validation_results table is not present.",
            "recent": [],
            "source_tables": [],
        }
    columns = table_columns(conn, "validation_results")
    validation_id = "validation_id" if "validation_id" in columns else "result_id"
    validation_type = (
        "validation_type" if "validation_type" in columns else "NULL AS validation_type"
    )
    command = "command" if "command" in columns else "NULL AS command"
    summary = "summary" if "summary" in columns else "NULL AS summary"
    evidence = (
        "evidence_refs_json" if "evidence_refs_json" in columns else "'[]' AS evidence_refs_json"
    )
    created = "created_at" if "created_at" in columns else "NULL AS created_at"
    rows = conn.execute(
        f"""
        SELECT {validation_id} AS validation_id, {validation_type}, status, {command},
               {summary}, {evidence}, {created}
        FROM validation_results
        WHERE project_id = ?
        ORDER BY created_at DESC
        LIMIT 10
        """,
        (project_id,),
    ).fetchall()
    recent = [
        {
            **dict(row),
            "evidence_refs": _json_list(row["evidence_refs_json"]),
        }
        for row in rows
    ]
    failed = sum(1 for row in recent if row.get("status") in {"failed", "error", "incomplete"})
    return {
        "classification": "fresh" if recent else "honest_empty_state",
        "recent": recent,
        "recent_count": len(recent),
        "failed_recent_count": failed,
        "source_tables": ["validation_results"],
        "derived_view": True,
        "primary_authority": False,
    }


def _attention_detail_items(conn: sqlite3.Connection, project_id: str) -> dict[str, Any]:
    if not object_exists(conn, "dashboard_attention_items"):
        return {
            "classification": "unavailable",
            "items": [],
            "source_tables": [],
        }
    columns = table_columns(conn, "dashboard_attention_items")
    attention_id = "attention_id" if "attention_id" in columns else "item_id"
    title = "title" if "title" in columns else "NULL AS title"
    summary = "summary" if "summary" in columns else "NULL AS summary"
    severity = "severity" if "severity" in columns else "NULL AS severity"
    evidence = (
        "evidence_refs_json" if "evidence_refs_json" in columns else "'[]' AS evidence_refs_json"
    )
    source_refs = (
        "source_refs_json" if "source_refs_json" in columns else "'[]' AS source_refs_json"
    )
    created = "created_at" if "created_at" in columns else "NULL AS created_at"
    rows = conn.execute(
        f"""
        SELECT {attention_id} AS attention_id, status, {severity}, {title}, {summary},
               {source_refs}, {evidence}, {created}
        FROM dashboard_attention_items
        WHERE project_id = ?
          AND COALESCE(status, 'open') NOT IN ('resolved', 'closed', 'dismissed')
        ORDER BY created_at DESC
        LIMIT 20
        """,
        (project_id,),
    ).fetchall()
    items = [
        {
            **dict(row),
            "source_refs": _json_list(row["source_refs_json"]),
            "evidence_refs": _json_list(row["evidence_refs_json"]),
        }
        for row in rows
    ]
    return {
        "classification": "fresh" if items else "honest_empty_state",
        "items": items,
        "open_count": len(items),
        "source_tables": ["dashboard_attention_items"],
        "derived_view": True,
        "primary_authority": False,
    }


# ── Component index ──────────────────────────────────────────────────────────


def _component_index(conn: sqlite3.Connection, project_id: str) -> dict[str, dict[str, Any]]:
    if not object_exists(conn, "pi_components"):
        return {}
    columns = table_columns(conn, "pi_components")
    select_cols = ["component_id"]
    for column in ("name", "path", "component_type", "lines", "complexity_score", "last_analyzed"):
        if column in columns:
            select_cols.append(column)
    rows = conn.execute(
        f"SELECT {', '.join(select_cols)} FROM pi_components WHERE project_id = ?",
        (project_id,),
    ).fetchall()
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        component_id = str(item.get("component_id") or "")
        if component_id:
            index[component_id] = {
                **item,
                "evidence_refs": [item.get("path")] if item.get("path") else [],
                "source_tables": ["pi_components"],
                "confirmation_status": "confirmed_component_record",
            }
    return index


# ── Surface availability ─────────────────────────────────────────────────────


def _missing_tables(conn: sqlite3.Connection, names: list[str]) -> list[str]:
    return [name for name in names if not object_exists(conn, name)]


def _empty_project_source_status(missing: list[str], *, reason: str) -> dict[str, Any]:
    return {
        "classification": "empty by design",
        "reason": reason,
        "missing": missing,
        "derived_view": True,
        "primary_authority": False,
    }


def _project_surface_availability(conn: sqlite3.Connection) -> dict[str, bool]:
    dependency_columns = (
        table_columns(conn, "pi_dependencies") if object_exists(conn, "pi_dependencies") else []
    )
    return {
        "overview": True,
        "prds": object_exists(conn, "prd_documents"),
        # findings_current_status dropped migration 140 (WO dff23cb0) — security
        # findings now derive from security_events at read time (never a
        # standalone schema object to probe for presence).
        "security": any(object_exists(conn, name) for name in ("security_events", "pi_violations")),
        "dependencies": object_exists(conn, "pi_dependencies")
        and {"from_component", "to_component"}.issubset(dependency_columns),
        "activity": any(
            object_exists(conn, name)
            for name in ("execution_events", "process_runs", "pi_analysis_runs")
        ),
        "health_trend": object_exists(conn, "pi_analysis_runs"),
        "bugs_summary": object_exists(conn, "pi_bugs"),
        "violations_summary": object_exists(conn, "pi_violations"),
    }


def _project_row_for_authority(conn: sqlite3.Connection, project_id: str) -> dict[str, Any] | None:
    # business_projects is Store 3 authority in studio.db — always read directly.
    if not object_exists(conn, "business_projects"):
        return None
    row = conn.execute(
        "SELECT project_id, name AS project_name, description, status, project_path,"
        " total_sessions, total_tokens, last_session_at, created_at, updated_at"
        " FROM business_projects WHERE project_id = ? LIMIT 1",
        (project_id,),
    ).fetchone()
    return dict(row) if row else None


def _unavailable_project_surfaces(availability: dict[str, bool]) -> list[str]:
    return [name for name, available in availability.items() if not available]
