"""Dry-run planning for historical legacy-to-telemetry backfill.

The functions in this module classify candidate legacy rows that could be
promoted into the telemetry spine later. They do not write to SQLite.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

BACKFILL_MAPPINGS: tuple[dict[str, Any], ...] = (
    {
        "domain": "skills",
        "source_table": "raw_skill_telemetry",
        "target_table": "skill_invocations",
        "source_time_column": "invoked_at",
        "target_time_column": "created_at",
        "classification": "missing because telemetry is not backfilled",
    },
    {
        "domain": "workflows",
        "source_table": "raw_workflow_runs",
        "target_table": "workflow_invocations",
        "source_time_column": "started_at",
        "target_time_column": "created_at",
        "classification": "missing because telemetry is not backfilled",
    },
    {
        "domain": "hooks",
        "source_table": "hook_executions",
        "target_table": "hook_invocations",
        "source_time_column": "started_at",
        "target_time_column": "created_at",
        "classification": "missing because telemetry is not backfilled",
    },
    {
        "domain": "security",
        "source_table": "sec_sarif_findings",
        "target_table": "findings",
        "source_time_column": "created_at",
        "target_time_column": "created_at",
        "classification": "legacy source",
    },
)


def plan_legacy_telemetry_backfill(db_path: Path | str) -> dict[str, Any]:
    """Return a non-executable backfill plan for compatible legacy tables."""

    path = Path(db_path)
    conn = _connect_read_only(path)
    try:
        candidates: list[dict[str, Any]] = []
        for mapping in BACKFILL_MAPPINGS:
            source_table = mapping["source_table"]
            target_table = mapping["target_table"]
            source_rows = _count(conn, source_table)
            target_rows = _count(conn, target_table)
            source_latest = _latest(conn, source_table, mapping["source_time_column"])
            target_latest = _latest(conn, target_table, mapping["target_time_column"])
            gap_rows = max(source_rows - target_rows, 0)
            if source_rows == 0:
                status = "empty_by_design"
            elif gap_rows > 0:
                status = "candidate_requires_future_approval"
            else:
                status = "covered_or_no_gap_detected"
            candidates.append(
                {
                    **mapping,
                    "source_exists": _object_exists(conn, source_table),
                    "target_exists": _object_exists(conn, target_table),
                    "source_rows": source_rows,
                    "target_rows": target_rows,
                    "candidate_rows": gap_rows,
                    "source_latest": source_latest,
                    "target_latest": target_latest,
                    "status": status,
                    "mode": "dry_run_only",
                    "execution_authorized": False,
                    "requires_backup": True,
                    "requires_operator_approval": True,
                }
            )

        return {
            "model_name": "legacy_telemetry_backfill_plan",
            "dry_run": True,
            "execution_authorized": False,
            "primary_authority": False,
            "derived_view": True,
            "candidates": candidates,
            "overall_status": _overall_status(candidates),
            "safety_note": "This plan identifies historical backfill candidates only; it does not insert, update, delete, archive, compact, or deduplicate.",
        }
    finally:
        conn.close()


def _connect_read_only(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def _object_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name = ? AND type IN ('table', 'view')",
            (name,),
        ).fetchone()
        is not None
    )


def _columns(conn: sqlite3.Connection, name: str) -> set[str]:
    if not _object_exists(conn, name):
        return set()
    return {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{name}")')}


def _count(conn: sqlite3.Connection, name: str) -> int:
    if not _object_exists(conn, name):
        return 0
    return int(conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] or 0)


def _latest(conn: sqlite3.Connection, name: str, column: str) -> str | None:
    if column not in _columns(conn, name):
        return None
    row = conn.execute(f'SELECT MAX("{column}") FROM "{name}"').fetchone()
    value = row[0] if row else None
    return str(value) if value is not None else None


def _overall_status(candidates: list[dict[str, Any]]) -> str:
    if any(candidate["status"] == "candidate_requires_future_approval" for candidate in candidates):
        return "backfill_candidates_require_future_approval"
    return "no_backfill_gap_detected"
