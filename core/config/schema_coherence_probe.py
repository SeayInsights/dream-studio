"""Schema-coherence live probes — migration replay against an in-memory DB.

Split out of schema_coherence.py (WO-GF-CORE-HEALTH-SKILLS): both functions run
a full migration sequence into ``sqlite3.connect(":memory:")`` and inventory
the resulting schema objects for schema_coherence_audit.py's structural and
live-drift passes.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def _build_migration_object_inventory(source_root: Path) -> dict[str, dict[str, str]]:
    """Build the set of indexes and triggers a full migration sequence should produce.

    Returns:
        {
          "indexes": {name: sql_ddl},   # sql_ddl used to determine UNIQUE vs non-unique
          "triggers": {name: sql_ddl},
        }

    Views are excluded: the M1-scar class (live-only objects like vw_activity_timeline,
    present-in-live/absent-in-fresh) is the opposite direction from a swallowed casualty
    and would false-positive without direction-aware diffing. Revisit when a fresh-only
    view casualty is confirmed.
    """
    from core.config.sqlite_bootstrap import run_migrations

    conn = sqlite3.connect(":memory:")
    try:
        run_migrations(conn)
        indexes = {
            row[0]: (row[1] or "")
            for row in conn.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type='index' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        triggers = {
            row[0]: (row[1] or "")
            for row in conn.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='trigger'"
            ).fetchall()
        }
        return {"indexes": indexes, "triggers": triggers}
    finally:
        conn.close()


def _build_migration_only_tables(source_root: Path) -> set[str]:
    """Run all migrations into a fresh in-memory DB. Return the resulting table and view names.

    VIEWs are included because a migration may convert a table to a view (e.g. migration 102
    retired the canonical_events TABLE and replaced it with a VIEW of the same name). Both
    are migration-owned schema objects and must be excluded from the staleness guard.
    """
    from core.config.sqlite_bootstrap import run_migrations

    conn = sqlite3.connect(":memory:")
    try:
        run_migrations(conn)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master"
            " WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%'"
        )
        return {row[0] for row in cursor.fetchall()}
    finally:
        conn.close()
