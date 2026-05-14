#!/usr/bin/env python3
"""Verify migration state without triggering auto-migration."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from interfaces.cli.runtime_preflight import (  # noqa: E402
    canonical_db_path,
    format_schema_compatibility,
    inspect_schema_compatibility,
    schema_compatibility_is_blocking,
)


def _connect_read_only(db_path: Path) -> sqlite3.Connection:
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def main() -> int:
    db_path = canonical_db_path()
    compatibility = inspect_schema_compatibility(repo_root=REPO_ROOT, db_path=db_path)

    print("=" * 70)
    print("SCHEMA COMPATIBILITY")
    print("=" * 70)
    print(format_schema_compatibility(compatibility))

    if not db_path.is_file():
        print("\nRESULT: studio.db is missing; no verification queries were run.")
        return 1

    if schema_compatibility_is_blocking(compatibility):
        print("\nRESULT: schema compatibility is blocked; no migration was attempted.")
        return 1

    required_tables = {"tool_registry", "research_cache"}
    optional_views = {"vw_graph_edges"}

    conn = _connect_read_only(db_path)
    try:
        print("\n" + "=" * 70)
        print("VERIFICATION QUERY 1: tool_registry and research_cache tables")
        print("=" * 70)
        tables = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name IN ('tool_registry', 'research_cache')"
        ).fetchall()
        table_names = {row[0] for row in tables}
        missing_tables = required_tables - table_names
        print(f"Tables found: {len(tables)}")
        for row in tables:
            print(f"  - {row[0]}")
        if missing_tables:
            print(f"Missing required tables: {', '.join(sorted(missing_tables))}")

        print("\n" + "=" * 70)
        print("VERIFICATION QUERY 2: optional legacy views")
        print("=" * 70)
        views = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='view' AND name = 'vw_graph_edges'"
        ).fetchall()
        view_names = {row[0] for row in views}
        missing_optional_views = optional_views - view_names
        print(f"Optional views found: {len(views)}")
        for row in views:
            print(f"  - {row[0]}")
        if missing_optional_views:
            print(
                "Optional legacy views missing: "
                f"{', '.join(sorted(missing_optional_views))} (non-blocking)"
            )
    finally:
        conn.close()

    print("\n" + "=" * 70)
    print("RESULT")
    print("=" * 70)
    if not missing_tables:
        print("SUCCESS: Schema compatibility and required tables verified")
        return 0

    print("FAILED: Missing required tables: " f"{', '.join(sorted(missing_tables))}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
