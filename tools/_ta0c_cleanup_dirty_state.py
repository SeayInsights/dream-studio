"""One-time recovery from partial migration 062 runs.

Drops hook_executions_new (an empty artifact left by Python 3.12 sqlite3's
CREATE TABLE auto-commit behavior when the migration transaction rolls back).
Safe to run multiple times — all operations are idempotent.

Usage:
    python tools/_ta0c_cleanup_dirty_state.py
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.config.database import get_db_path  # noqa: E402


def main() -> int:
    db_path = get_db_path()
    if not db_path.is_file():
        print(f"ERROR: studio.db not found at {db_path}")
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.isolation_level = None  # autocommit — each statement commits immediately

    print(f"Connected to: {db_path}")
    print()

    # --- Report current state ---
    version = conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0]
    print(f"Schema version: {version}")

    new_tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_new' ORDER BY name"
    ).fetchall()
    print(f"Leftover _new tables: {[r[0] for r in new_tables] or 'none'}")

    al_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='activity_log'"
    ).fetchone()
    if al_exists:
        al_count = conn.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0]
        print(f"activity_log rows: {al_count}")
    else:
        print("activity_log: ABSENT (already dropped)")

    backfill = conn.execute(
        "SELECT COUNT(*) FROM canonical_events WHERE event_id LIKE 'backfill-activity-log-%'"
    ).fetchone()[0]
    print(f"Backfill rows in canonical_events: {backfill}")
    print()

    # --- Drop leftover _new tables ---
    dropped = []
    for (tname,) in new_tables:
        conn.execute(f"DROP TABLE IF EXISTS {tname}")
        dropped.append(tname)
        print(f"Dropped: {tname}")

    if not dropped:
        print("No _new tables to clean up.")

    # --- Final verification ---
    remaining = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_new'"
    ).fetchall()
    if remaining:
        print(f"WARNING: _new tables still present after cleanup: {[r[0] for r in remaining]}")
        conn.close()
        return 1

    print()
    print("DB state is clean. Ready for migration 062.")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
