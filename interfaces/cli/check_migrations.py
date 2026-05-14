#!/usr/bin/env python3
"""Check migration status and verify tables/views."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from interfaces.cli.runtime_preflight import (
    format_schema_compatibility,
    inspect_schema_compatibility,
    schema_compatibility_is_blocking,
)


def main():
    compatibility = inspect_schema_compatibility(repo_root=REPO_ROOT)
    if schema_compatibility_is_blocking(compatibility):
        print(format_schema_compatibility(compatibility))
        print("\nRESULT: schema compatibility is blocked; no migration connection was opened.")
        return 1

    from core.event_store.studio_db import _connect  # noqa: PLC0415

    conn = _connect()

    # Check current schema version
    print("Schema versions applied:")
    result = conn.execute(
        "SELECT version, applied_at FROM _schema_version ORDER BY version"
    ).fetchall()
    for v, dt in result:
        print(f"  v{v}: {dt}")

    current = conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0]
    print(f"\nCurrent version: {current}")

    # Check for tables
    print("\nChecking for tables:")
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('tool_registry', 'research_cache')"
    ).fetchall()
    print(f"  Tables found: {len(tables)}")
    for t in tables:
        print(f"    - {t[0]}")

    # Check for views
    print("\nChecking for views:")
    views = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view' AND name = 'vw_graph_edges'"
    ).fetchall()
    print(f"  Views found: {len(views)}")
    for v in views:
        print(f"    - {v[0]}")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
