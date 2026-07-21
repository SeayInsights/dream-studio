"""Analytics-only ingestion contract and read-only profile status.

WO-GF-READINESS-INSIGHTS: split from ``core/analytics_ingestion.py``. No logic
changes — extracted verbatim.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from .analytics_ingestion_shared import (
    ANALYTICS_INGESTION_SCHEMA,
    INGESTION_SECTIONS,
    SECTION_TABLES,
    _table_names,
)

ANALYTICS_ONLY_CAPABILITIES: tuple[str, ...] = (
    "normalized_project_import",
    "ci_validation_import",
    "security_finding_import",
    "token_usage_import",
    "operational_ai_usage_import",
    "readiness_scorecard_import",
    "dashboard_api_read_models",
    "honest_empty_states",
)


def analytics_only_ingestion_contract() -> dict[str, Any]:
    """Return the analytics-only ingestion contract."""

    return {
        "schema": ANALYTICS_INGESTION_SCHEMA,
        "model_name": "analytics_only_deployment_profile_and_ingestion_contracts",
        "derived_view": True,
        "primary_authority": False,
        "profile_id": "analytics_only",
        "hooks_required": False,
        "agents_required": False,
        "workflows_required": False,
        "claude_required": False,
        "codex_required": False,
        "docker_required": False,
        "repo_mutation_required": False,
        "default_write_authorized": False,
        "write_authorization": "explicit_ingestion_execute_only",
        "hooks_are_optional_producers": True,
        "sections": [
            {
                "section": section,
                "target_tables": list(SECTION_TABLES[section]),
                "required": False,
                "empty_state": "honest_empty_state",
            }
            for section in INGESTION_SECTIONS
        ],
        "capabilities": list(ANALYTICS_ONLY_CAPABILITIES),
        "dashboard_routes": [
            "/api/v1/projects",
            "/api/v1/projects/{project_id}/details",
            "/api/v1/metrics/*",
            "/api/v1/security/*",
            "/api/shared-intelligence/analytics-only",
            "/api/shared-intelligence/production-readiness",
            "/api/shared-intelligence/ai-usage-accounting",
        ],
    }


def analytics_only_profile_status(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return analytics-only table/read-model readiness without writing data."""

    tables = _table_names(conn)
    section_status = {}
    for section, target_tables in SECTION_TABLES.items():
        available = [table for table in target_tables if table in tables]
        missing = [table for table in target_tables if table not in tables]
        section_status[section] = {
            "status": "available" if available else "unavailable",
            "available_tables": available,
            "missing_tables": missing,
            "honest_empty_state": bool(missing),
        }
    return {
        **analytics_only_ingestion_contract(),
        "model_name": "dream_studio_analytics_only_profile_status",
        "section_status": section_status,
        "table_count": len(tables),
        "source_tables": sorted(
            {table for tables_ in SECTION_TABLES.values() for table in tables_}
        ),
        "dashboard_api_available": True,
        "ingestion_cli": "ds analytics-ingest --file <payload.json> --execute",
        "dry_run_cli": "ds analytics-ingest --file <payload.json>",
        "empty_state": (
            "Analytics-only routes and import contracts are available; missing facts render "
            "as honest empty states."
        ),
    }
