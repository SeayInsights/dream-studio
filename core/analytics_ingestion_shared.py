"""Shared constants and helpers for the analytics-ingestion split.

WO-GF-READINESS-INSIGHTS: leaf module of the ``analytics_ingestion`` facade split.
Holds the section constants and small helpers used by more than one sibling. No
logic changes — extracted verbatim from the original ``core/analytics_ingestion.py``.
"""

from __future__ import annotations

import sqlite3
from typing import Any

ANALYTICS_INGESTION_SCHEMA = "dream_studio.analytics_only_ingestion.v1"

INGESTION_SECTIONS: tuple[str, ...] = (
    "projects",
    "validations",
    "findings",
    "token_usage",
    "ai_usage",
    "components",
    "dependencies",
    "readiness_assessments",
)

SECTION_TABLES: dict[str, tuple[str, ...]] = {
    "projects": ("business_projects",),
    "validations": ("validation_results",),
    "findings": ("security_events",),  # findings retired in migration 112 → security_events spine
    "token_usage": ("token_usage_records",),
    "ai_usage": ("ai_usage_operational_records",),
    "components": (),  # pi_components dropped in migration 084
    "dependencies": (),  # pi_dependencies dropped in migration 084
    "readiness_assessments": (
        "readiness_events",
    ),  # production_readiness_* dropped in migration 112
}


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        ).fetchall()
    }


def _json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        return [value]
    return [value]
