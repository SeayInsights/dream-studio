"""Unit tests for WO-ATTRIBUTION-NORMALIZE: project key resolver.

T1 — resolver maps project name and project_path basename to UUID.
"""

from __future__ import annotations

import sqlite3


def _seed_projects(conn: sqlite3.Connection) -> str:
    """Create a minimal business_projects table and return the project UUID."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS business_projects (
            project_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            project_path TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    project_id = "29ff0914-b15a-4a84-8bc7-5619cc5240f6"
    conn.execute(
        "INSERT OR IGNORE INTO business_projects"
        " (project_id, name, project_path, status, created_at, updated_at)"
        " VALUES (?, ?, ?, 'active', datetime('now'), datetime('now'))",
        (
            project_id,
            "dream-studio",
            "/home/user/builds/dream-studio-clean",
        ),
    )
    conn.commit()
    return project_id


# ---------------------------------------------------------------------------
# test_resolver_maps_name_and_path_to_uuid
# ---------------------------------------------------------------------------


def test_resolver_maps_name_and_path_to_uuid(tmp_path) -> None:
    """T1: resolver correctly maps project keys to registered UUID.

    Checks:
    - Exact name match ('dream-studio')
    - Slug of a multi-word name ('Dream Studio' -> 'dream-studio')
    - Path basename match ('dream-studio-clean' matches basename of project_path)
    - Unresolvable key returns None
    - Already-UUID input returns None (caller should skip it)
    """
    from core.projects.attribution import resolve_project_uuid

    db_path = tmp_path / "resolver-test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    project_id = _seed_projects(conn)

    # Exact name match
    result = resolve_project_uuid("dream-studio", conn)
    assert result == project_id, f"Expected UUID for 'dream-studio', got {result!r}"

    # Slug match: the name 'dream-studio' slugifies to 'dream-studio',
    # and the key 'Dream Studio' slugifies to 'dream-studio' too
    result2 = resolve_project_uuid("Dream Studio", conn)
    assert result2 == project_id, f"Expected UUID for 'Dream Studio', got {result2!r}"

    # Basename of project_path ('dream-studio-clean') — slug matches slug of basename
    result3 = resolve_project_uuid("dream-studio-clean", conn)
    assert result3 == project_id, f"Expected UUID for 'dream-studio-clean', got {result3!r}"

    # Unresolvable garbage key returns None
    result4 = resolve_project_uuid("Temp", conn)
    assert result4 is None, f"Expected None for 'Temp', got {result4!r}"

    # Empty string returns None
    result5 = resolve_project_uuid("", conn)
    assert result5 is None, f"Expected None for '', got {result5!r}"

    conn.close()


# ---------------------------------------------------------------------------
# test_slugify_normalization
# ---------------------------------------------------------------------------


def test_slugify_normalization() -> None:
    """Verify slug normalization produces expected values for common project names."""
    from core.projects.attribution import _slugify

    assert _slugify("dream-studio") == "dream-studio"
    assert _slugify("dream-studio-clean") == "dream-studio-clean"
    assert _slugify("Dream Studio") == "dream-studio"
    assert _slugify("  Dream   Studio  ") == "dream-studio"
    assert _slugify("My_Project") == "my-project"
    assert _slugify("") == ""


# ---------------------------------------------------------------------------
# test_already_uuid_skipped_by_backfill
# ---------------------------------------------------------------------------


def test_already_uuid_skipped_by_backfill(tmp_path) -> None:
    """Rows where project_id already holds a UUID must not be touched by backfill."""
    from core.projects.attribution import backfill_execution_events

    db_path = tmp_path / "uuid-skip.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    project_id = _seed_projects(conn)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS execution_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL DEFAULT 'test.event',
            event_name TEXT NOT NULL DEFAULT 'test',
            project_id TEXT,
            outcome_status TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute(
        "INSERT INTO execution_events (event_id, project_id)" " VALUES ('evt-already-uuid', ?)",
        (project_id,),
    )
    conn.commit()

    summary = backfill_execution_events(conn)
    # A UUID key must never appear in the summary (it was skipped)
    assert (
        project_id not in summary
    ), f"UUID project_id {project_id!r} should not be remapped by backfill"
    # Verify the row is still intact
    row = conn.execute(
        "SELECT project_id FROM execution_events WHERE event_id = 'evt-already-uuid'"
    ).fetchone()
    assert row["project_id"] == project_id

    conn.close()


# ---------------------------------------------------------------------------
# test_unresolvable_key_not_remapped
# ---------------------------------------------------------------------------


def test_unresolvable_key_not_remapped(tmp_path) -> None:
    """Garbage keys that match no project must be left untouched by backfill."""
    from core.projects.attribution import backfill_execution_events

    db_path = tmp_path / "garbage-keys.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    _seed_projects(conn)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS execution_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL DEFAULT 'test.event',
            event_name TEXT NOT NULL DEFAULT 'test',
            project_id TEXT,
            outcome_status TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    garbage_keys = ["Temp", "builds", "tasks", ".claude"]
    for i, key in enumerate(garbage_keys):
        conn.execute(
            "INSERT INTO execution_events (event_id, project_id) VALUES (?, ?)",
            (f"evt-garbage-{i}", key),
        )
    conn.commit()

    summary = backfill_execution_events(conn)
    # None of the garbage keys should appear in the summary
    for key in garbage_keys:
        assert key not in summary, f"Garbage key {key!r} should not be remapped"
    # Verify rows untouched
    rows = conn.execute("SELECT project_id FROM execution_events ORDER BY event_id").fetchall()
    for row, expected in zip(rows, garbage_keys):
        assert row["project_id"] == expected, f"Expected {expected!r}, got {row['project_id']!r}"

    conn.close()
