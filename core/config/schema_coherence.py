"""Aspirational schema audit — detects schema references that fail at runtime.

Two scopes of finding:
  structural  — detected via migration replay + schema diff + migration grep.
                Same result on every machine; independent of live DB state.
  live_drift  — detected by probing the live DB. Machine-specific.

Usage:
    from core.config.schema_coherence import check_schema_coherence
    result = check_schema_coherence(source_root=source_root)
    result = check_schema_coherence(source_root=source_root, live_db_path=db_path)

WO-GF-CORE-HEALTH-SKILLS: implementation moved to schema_coherence_{registry,
probe,scan,audit}.py; this module re-exports the public+private surface so
existing `from core.config.schema_coherence import X` callers are unchanged.
"""

from __future__ import annotations

from .schema_coherence_audit import check_schema_coherence
from .schema_coherence_probe import (
    _build_migration_object_inventory,
    _build_migration_only_tables,
)
from .schema_coherence_registry import (
    _CANONICAL_EVENTS_PYTHON_COLS,
    _DDL_KEYWORD_FALSE_POSITIVES,
    _DUAL_OWNED_TABLES,
    _FILES_DB_TABLES,
    _PACKETS_DB_TABLES,
    _PYTHON_OWNED_TABLES,
    _SELF_SCAN_EXCLUDE,
    _SWALLOW_INVENTORY,
)
from .schema_coherence_scan import (
    _effective_swallow_classification,
    _migration_insert_columns,
    _migration_references,
    _staleness_guard,
    _swallowed_casualty_severity,
)

__all__ = [
    "_CANONICAL_EVENTS_PYTHON_COLS",
    "_DDL_KEYWORD_FALSE_POSITIVES",
    "_DUAL_OWNED_TABLES",
    "_FILES_DB_TABLES",
    "_PACKETS_DB_TABLES",
    "_PYTHON_OWNED_TABLES",
    "_SELF_SCAN_EXCLUDE",
    "_SWALLOW_INVENTORY",
    "_build_migration_object_inventory",
    "_build_migration_only_tables",
    "_effective_swallow_classification",
    "_migration_insert_columns",
    "_migration_references",
    "_staleness_guard",
    "_swallowed_casualty_severity",
    "check_schema_coherence",
]
