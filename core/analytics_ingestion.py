"""Analytics-only normalized ingestion contracts.

This module lets the analytics-only profile import externally produced facts
into current SQLite authority without depending on hooks, agents, workflows,
Claude, Codex, Docker, repo mutation, or full orchestration.

WO-GF-READINESS-INSIGHTS: implementation moved to the sibling
analytics_ingestion_{shared,contract,rows,core}.py modules; this module
re-exports the public API so existing
``from core.analytics_ingestion import X`` callers are unchanged.
"""

from __future__ import annotations

from .analytics_ingestion_contract import (
    ANALYTICS_ONLY_CAPABILITIES,
    analytics_only_ingestion_contract,
    analytics_only_profile_status,
)
from .analytics_ingestion_core import (
    APPEND_ONLY_TABLES,
    TABLE_KEYS,
    ingest_analytics_payload,
    load_analytics_payload,
)
from .analytics_ingestion_shared import (
    ANALYTICS_INGESTION_SCHEMA,
    INGESTION_SECTIONS,
    SECTION_TABLES,
)

__all__ = [
    "ANALYTICS_INGESTION_SCHEMA",
    "INGESTION_SECTIONS",
    "SECTION_TABLES",
    "TABLE_KEYS",
    "APPEND_ONLY_TABLES",
    "ANALYTICS_ONLY_CAPABILITIES",
    "analytics_only_ingestion_contract",
    "analytics_only_profile_status",
    "ingest_analytics_payload",
    "load_analytics_payload",
]
