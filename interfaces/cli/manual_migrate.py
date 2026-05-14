#!/usr/bin/env python3
"""Manually execute migrations 013 and 014 with detailed error reporting."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

from core.event_store.studio_db import _connect, _split_statements


def main():
    conn = _connect()
    migrations_dir = Path(__file__).resolve().parents[1] / "hooks" / "lib" / "migrations"

    for migration_file in ["013_discovery_tables.sql", "014_graph_views.sql"]:
        print(f"\n{'='*70}")
        print(f"Executing {migration_file}")
        print("=" * 70)

        sql_text = (migrations_dir / migration_file).read_text(encoding="utf-8")
        statements = _split_statements(sql_text)

        print(f"Found {len(statements)} statements to execute\n")

        for i, stmt in enumerate(statements, 1):
            # Show first 100 chars of statement
            preview = stmt.replace("\n", " ")[:100]
            print(f"[{i}/{len(statements)}] {preview}...")

            try:
                conn.execute(stmt)
                print("  [OK] Success")
            except Exception as e:
                print(f"  [ERROR] {e}")
                print(f"  Full statement:\n{stmt}\n")

        conn.commit()
        print(f"\n{migration_file} complete")

    conn.close()
    print("\n" + "=" * 70)
    print("All migrations attempted")
    print("=" * 70)


if __name__ == "__main__":
    main()
