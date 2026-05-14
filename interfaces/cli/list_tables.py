#!/usr/bin/env python3
"""List all tables and views in studio.db."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

from core.event_store.studio_db import _connect


def main():
    conn = _connect()

    # List all tables
    print("TABLES:")
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    for t in tables:
        print(f"  - {t[0]}")

    # List all views
    print("\nVIEWS:")
    views = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view' ORDER BY name"
    ).fetchall()
    for v in views:
        print(f"  - {v[0]}")

    conn.close()


if __name__ == "__main__":
    main()
