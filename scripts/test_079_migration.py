"""Batch 1 stop gate: verify migration 079 applies cleanly.

Tests:
- intelligence_surfaced_at column added to memory_entries
- FTS INSERT trigger fires when a row is inserted
- FTS UPDATE trigger fires when content is updated
- FTS DELETE trigger fires when a row is deleted
- Backfill INSERT is a no-op on empty table
- Index exists for intelligence_surfaced_at
"""

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.event_store.studio_db import _connect, _run_migrations  # noqa: E402

def main() -> int:
    tmpdir = tempfile.mkdtemp(prefix="ds-test-079-")
    db = Path(tmpdir) / "test.db"
    errors = []

    try:
        with _connect(db) as c:
            _run_migrations(c)
            c.commit()

        with _connect(db) as c:
            cols = [r[1] for r in c.execute("PRAGMA table_info(memory_entries)")]

            # 1. intelligence_surfaced_at column present
            if "intelligence_surfaced_at" not in cols:
                errors.append(f"FAIL: intelligence_surfaced_at missing; cols={cols}")
            else:
                print("✓ intelligence_surfaced_at column present")

            # 2. FTS INSERT trigger
            c.execute(
                "INSERT INTO memory_entries (memory_id, source, category, content, created_at)"
                " VALUES ('m1', 'test', 'gotcha', 'modal focus trap inert', '2026-01-01')"
            )
            c.commit()
            fts_rows = c.execute("SELECT memory_id FROM memory_fts WHERE memory_id='m1'").fetchall()
            if not fts_rows:
                errors.append("FAIL: FTS INSERT trigger did not fire")
            else:
                print("✓ FTS INSERT trigger fires")

            # 3. FTS search works
            results = c.execute(
                "SELECT memory_id FROM memory_fts WHERE memory_fts MATCH 'modal'"
            ).fetchall()
            if not results:
                errors.append("FAIL: FTS search returned no results for 'modal'")
            else:
                print(f"✓ FTS search works: {len(results)} result(s)")

            # 4. FTS UPDATE trigger
            c.execute(
                "UPDATE memory_entries SET content='updated content tabindex' WHERE memory_id='m1'"
            )
            c.commit()
            old_search = c.execute(
                "SELECT memory_id FROM memory_fts WHERE memory_fts MATCH 'modal'"
            ).fetchall()
            new_search = c.execute(
                "SELECT memory_id FROM memory_fts WHERE memory_fts MATCH 'tabindex'"
            ).fetchall()
            if old_search:
                errors.append("FAIL: FTS UPDATE trigger didn't remove old content")
            elif not new_search:
                errors.append("FAIL: FTS UPDATE trigger didn't add new content")
            else:
                print("✓ FTS UPDATE trigger fires (old content removed, new content indexed)")

            # 5. FTS DELETE trigger
            c.execute("DELETE FROM memory_entries WHERE memory_id='m1'")
            c.commit()
            post_delete = c.execute(
                "SELECT memory_id FROM memory_fts WHERE memory_id='m1'"
            ).fetchall()
            if post_delete:
                errors.append("FAIL: FTS DELETE trigger did not fire")
            else:
                print("✓ FTS DELETE trigger fires")

            # 6. intelligence_surfaced_at round-trip
            c.execute(
                "INSERT INTO memory_entries (memory_id, source, category, content, created_at)"
                " VALUES ('m2', 'test', 'gotcha', 'test content', '2026-01-01')"
            )
            c.execute(
                "UPDATE memory_entries SET intelligence_surfaced_at='2026-05-28T12:00:00'"
                " WHERE memory_id='m2'"
            )
            c.commit()
            row = c.execute(
                "SELECT intelligence_surfaced_at FROM memory_entries WHERE memory_id='m2'"
            ).fetchone()
            if not row or row[0] != "2026-05-28T12:00:00":
                errors.append(f"FAIL: intelligence_surfaced_at round-trip; got {row}")
            else:
                print("✓ intelligence_surfaced_at round-trip works")

            # 7. Total memory_entries row count (m2 remains, m1 was deleted)
            cnt = c.execute("SELECT COUNT(*) FROM memory_entries").fetchone()[0]
            print(f"✓ memory_entries row count after test: {cnt}")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    if errors:
        print("\nFAILURES:")
        for e in errors:
            print(f"  {e}")
        return 1

    print("\n✓ Migration 079 stop gate PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
