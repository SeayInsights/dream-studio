"""Shared constants and helpers for the production-readiness controls split.

WO-GF-READINESS-INSIGHTS: leaf module of the ``controls`` facade split. Holds the
constants/helpers used by more than one sibling. No logic changes — extracted
verbatim from the original ``core/production_readiness/controls.py``.
"""

from __future__ import annotations

import sqlite3

FULL_REVIEW_EVENTS = {
    "project_intake",
    "release",
    "merge",
    "release_merge",
    "publication",
    "deployment",
    "live_cutover",
    "dependency_change",
    "runtime_change",
    "database_change",
    "security_change",
    "docker_change",
    "major_architecture_change",
    "external_project_onboarding",
    "scheduled_dogfood_gate",
}


def _stable_id(prefix: str, *parts: object) -> str:
    raw = "-".join(str(part).strip().lower().replace(" ", "-") for part in parts if part)
    sanitized = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in raw)
    return f"{prefix}-{sanitized[:120]}"


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        (table,),
    ).fetchone()
    return row is not None
