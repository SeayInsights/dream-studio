"""Analytics ingestion orchestration and SQLite upsert.

WO-GF-READINESS-INSIGHTS: split from ``core/analytics_ingestion.py``. No logic
changes — extracted verbatim.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .analytics_ingestion_contract import analytics_only_ingestion_contract
from .analytics_ingestion_rows import (
    _ai_usage_rows,
    _component_rows,
    _dependency_rows,
    _project_rows,
    _readiness_rows,
    _security_finding_rows,
    _token_usage_rows,
    _validation_rows,
)
from .analytics_ingestion_shared import (
    ANALYTICS_INGESTION_SCHEMA,
    INGESTION_SECTIONS,
    SECTION_TABLES,
    _json_list,
    _table_names,
)

TABLE_KEYS: dict[str, str] = {
    "business_projects": "project_id",
    "validation_results": "validation_id",
    "security_events": "event_id",
    "token_usage_records": "token_usage_id",
    "ai_usage_operational_records": "usage_record_id",
    "readiness_events": "event_id",
}

# These tables are append-only event spines — never update existing rows on re-import.
APPEND_ONLY_TABLES: frozenset[str] = frozenset({"security_events", "readiness_events"})


def ingest_analytics_payload(
    conn: sqlite3.Connection,
    payload: dict[str, Any],
    *,
    execute: bool = False,
) -> dict[str, Any]:
    """Ingest a normalized analytics payload into current SQLite authority.

    Dry-run is the default. Set execute=True to write idempotent records.
    """

    if not isinstance(payload, dict):
        raise ValueError("analytics ingestion payload must be a JSON object")

    source_refs = _json_list(payload.get("source_refs"))
    evidence_refs = _json_list(payload.get("evidence_refs"))
    ingested_at = str(payload.get("ingested_at") or datetime.now(UTC).isoformat())
    tables = _table_names(conn)
    written: Counter[str] = Counter()
    planned: Counter[str] = Counter()
    skipped: list[dict[str, Any]] = []

    section_handlers = {
        "projects": _project_rows,
        "validations": _validation_rows,
        "findings": _security_finding_rows,
        "token_usage": _token_usage_rows,
        "ai_usage": _ai_usage_rows,
        "components": _component_rows,
        "dependencies": _dependency_rows,
        "readiness_assessments": _readiness_rows,
    }

    for section in INGESTION_SECTIONS:
        records = payload.get(section) or []
        if not isinstance(records, list):
            skipped.append(
                {
                    "section": section,
                    "reason": "section_is_not_a_list",
                    "target_tables": list(SECTION_TABLES[section]),
                }
            )
            continue
        missing = [table for table in SECTION_TABLES[section] if table not in tables]
        if missing:
            skipped.append(
                {
                    "section": section,
                    "reason": "target_tables_missing",
                    "missing_tables": missing,
                }
            )
            continue
        for record in records:
            if not isinstance(record, dict):
                skipped.append({"section": section, "reason": "record_is_not_an_object"})
                continue
            rows = section_handlers[section](
                record,
                source_refs=source_refs,
                evidence_refs=evidence_refs,
                ingested_at=ingested_at,
            )
            for table, row in rows:
                planned[table] += 1
                if execute:
                    _upsert(conn, table, row)
                    written[table] += 1

    if execute:
        conn.commit()
        # findings_current_status dropped migration 140 (WO dff23cb0) — status
        # readers derive current_status from security_events at read time
        # (core/findings/current_status.py); no projection to fold here.

    return {
        "schema": ANALYTICS_INGESTION_SCHEMA,
        "model_name": "dream_studio_analytics_only_ingestion_result",
        "derived_view": True,
        "primary_authority": False,
        "execute": execute,
        "dry_run": not execute,
        "db_write_authorized": execute,
        "hooks_required": False,
        "agents_required": False,
        "workflows_required": False,
        "claude_required": False,
        "codex_required": False,
        "docker_required": False,
        "repo_mutation_required": False,
        "records_planned": dict(planned),
        "records_written": dict(written),
        "skipped": skipped,
        "source_refs": source_refs,
        "evidence_refs": evidence_refs,
        "dashboard_api_consumers": analytics_only_ingestion_contract()["dashboard_routes"],
        "empty_state_policy": "missing sections are skipped and exposed as honest empty states",
    }


def load_analytics_payload(path: str | Path) -> dict[str, Any]:
    """Load a normalized analytics ingestion payload from JSON."""

    payload_path = Path(path)
    with payload_path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("analytics ingestion file must contain a JSON object")
    refs = _json_list(payload.get("source_refs"))
    payload["source_refs"] = [*refs, f"file:{payload_path.resolve()}"]
    return payload


def _upsert(conn: sqlite3.Connection, table: str, row: dict[str, Any]) -> None:
    columns = _table_columns(conn, table)
    filtered = {key: value for key, value in row.items() if key in columns}
    if not filtered:
        return
    col_sql = ", ".join(filtered)
    placeholders = ", ".join("?" for _ in filtered)
    if table in APPEND_ONLY_TABLES:
        # Event spines are append-only — INSERT OR IGNORE on duplicate PK for idempotent re-import.
        conn.execute(
            f"INSERT OR IGNORE INTO {table}({col_sql}) VALUES ({placeholders})",
            tuple(filtered.values()),
        )
        return
    key = TABLE_KEYS.get(table)
    if key and key in filtered:
        update_columns = [column for column in filtered if column != key]
        if update_columns:
            set_sql = ", ".join(f"{column} = ?" for column in update_columns)
            values = [filtered[column] for column in update_columns]
            values.append(filtered[key])
            cursor = conn.execute(
                f"UPDATE {table} SET {set_sql} WHERE {key} = ?",
                tuple(values),
            )
            if cursor.rowcount:
                return
    conn.execute(
        f"INSERT INTO {table}({col_sql}) VALUES ({placeholders})",
        tuple(filtered.values()),
    )


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
