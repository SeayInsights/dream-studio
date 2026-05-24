"""
Verify the full migration sequence runs cleanly against a fresh database.
Regression test for B2 (2026-05-24 audit): migration sequence broke at 032
because memory_entries table was created by application code, not migration.

Uses the production run_migrations() function so the same error-skip logic
that runs in production is also tested here.
"""

import sqlite3
import pathlib
import pytest

from core.config.sqlite_bootstrap import run_migrations

MIGRATIONS_DIR = pathlib.Path("core/event_store/migrations")


def _all_migration_files():
    return sorted(MIGRATIONS_DIR.glob("[0-9]*.sql"))


def _fresh_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_all_migrations_apply_to_empty_memory_db():
    """Every migration applies via the production runner against :memory: without error."""
    conn = _fresh_conn()
    try:
        version = run_migrations(conn)
        assert version > 0, "No migrations applied"
    except Exception as e:
        pytest.fail(f"run_migrations failed on :memory:: {e}")
    finally:
        conn.close()


def test_all_migrations_apply_to_fresh_on_disk_db(tmp_path):
    """Same as above but against an on-disk DB (catches issues that :memory: hides)."""
    db_path = tmp_path / "test_migrations.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        version = run_migrations(conn)
        assert version > 0, "No migrations applied"
    except Exception as e:
        pytest.fail(f"run_migrations failed on disk DB: {e}")
    finally:
        conn.close()


def test_no_gaps_in_migration_numbering():
    """Migration filenames are sequential with no gaps, or gaps are documented in README."""
    files = _all_migration_files()
    numbers = sorted([int(f.name[:3]) for f in files if f.name[:3].isdigit()])
    if not numbers:
        pytest.skip("No migration files found")
    expected = set(range(min(numbers), max(numbers) + 1))
    actual = set(numbers)
    gaps = expected - actual
    if gaps:
        readme = MIGRATIONS_DIR / "README.md"
        if not readme.exists():
            pytest.fail(f"Migration numbering has gaps {sorted(gaps)} and no README documents them")
        readme_text = readme.read_text(encoding="utf-8")
        for gap in gaps:
            assert f"{gap:03d}" in readme_text, f"Gap {gap:03d} not documented in migrations README"


def test_memory_entries_exists_after_011():
    """Migration 011 must create memory_entries table (required by 032)."""
    conn = _fresh_conn()
    try:
        run_migrations(conn, target_version=11)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_entries'"
        )
        assert cursor.fetchone() is not None, "memory_entries table missing after migration 011"
    finally:
        conn.close()
