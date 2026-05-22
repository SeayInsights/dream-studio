"""Tests for ds_projects contamination cleanup and guard_real_homedir hardening (Phase 18.0, C3)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def test_migration_065_removes_test_fixtures(tmp_path):
    """Migration 065 must delete fixture rows and preserve real projects."""
    db_path = tmp_path / "studio.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE applied_migrations (migration_name TEXT PRIMARY KEY)
    """)
    conn.execute("""
        CREATE TABLE ds_projects (
            project_id TEXT PRIMARY KEY,
            name TEXT,
            status TEXT,
            created_at TEXT
        )
    """)
    # Insert real projects
    conn.executemany(
        "INSERT INTO ds_projects VALUES (?,?,?,?)",
        [
            ("real-1", "Dream Studio", "active", "2026-05-22"),
            ("real-2", "Dream Command", "paused", "2026-05-17"),
        ],
    )
    # Insert test fixture rows matching known contamination patterns
    conn.executemany(
        "INSERT INTO ds_projects VALUES (?,?,?,?)",
        [
            ("fix-1", "My Project", "paused", "2026-05-22"),
            ("fix-2", "Programmatic Project", "paused", "2026-05-22"),
            ("fix-3", "API Project", "paused", "2026-05-22"),
            ("fix-4", "TA0 Verification Test", "paused", "2026-05-21"),
            ("fix-5", "TA0 E2E Verify", "paused", "2026-05-21"),
        ],
    )
    conn.commit()

    # Apply migration SQL directly
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "core"
        / "event_store"
        / "migrations"
        / "065_remove_test_fixture_contamination.sql"
    )
    assert migration_path.is_file(), f"Migration not found: {migration_path}"
    sql = migration_path.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.commit()

    rows = conn.execute("SELECT name FROM ds_projects ORDER BY name").fetchall()
    names = [r[0] for r in rows]
    conn.close()

    assert names == [
        "Dream Command",
        "Dream Studio",
    ], f"Expected only real projects after migration, got: {names}"


def test_migration_065_is_idempotent(tmp_path):
    """Applying migration 065 twice must not raise or change the result."""
    db_path = tmp_path / "studio.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE ds_projects (project_id TEXT, name TEXT, status TEXT, created_at TEXT)"
    )
    conn.execute("INSERT INTO ds_projects VALUES ('r1', 'Dream Studio', 'active', '2026-05-22')")
    conn.commit()

    migration_path = (
        Path(__file__).resolve().parents[2]
        / "core"
        / "event_store"
        / "migrations"
        / "065_remove_test_fixture_contamination.sql"
    )
    sql = migration_path.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.executescript(sql)  # second run
    conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM ds_projects").fetchone()[0]
    conn.close()
    assert count == 1


def test_real_db_has_only_real_projects():
    """After migration 065, the production studio.db must have exactly 2 rows."""
    real_db = Path.home() / ".dream-studio" / "state" / "studio.db"
    if not real_db.is_file():
        pytest.skip("Production DB not present")

    conn = sqlite3.connect(str(real_db))
    rows = conn.execute("SELECT name FROM ds_projects ORDER BY name").fetchall()
    conn.close()

    names = [r[0] for r in rows]
    assert len(names) == 2, f"Expected 2 projects, got {len(names)}: {names}"
    assert "Dream Studio" in names
    assert "Dream Command" in names
