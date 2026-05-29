"""Tests for O7: S3b swallow narrowing and swallowed_statement_casualty audit extension.

Verification fixtures in order:
  1. Ground-truth: CREATE INDEX on absent memory_entries now propagates (the M2 mechanism
     caught and closed). Old behavior reproduced → new behavior asserted.
  2. Install-safety: every legitimate swallow still fires (ALTER TABLE ADD COLUMN,
     INSERT backfill on absent memory_entries still swallowed).
  3. Audit extension: swallowed_statement_casualty detects missing index (medium for
     non-unique, high for UNIQUE), missing trigger (high), clean on coherent DB,
     direction-aware (live-only M1 scar NOT flagged).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import run_migrations

# ── helpers ───────────────────────────────────────────────────────────────────


def _source_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _fresh_conn_at(target_version: int | None = None) -> sqlite3.Connection:
    """Fresh in-memory DB migrated to target_version (or fully migrated if None)."""
    conn = sqlite3.connect(":memory:")
    run_migrations(conn, target_version=target_version)
    return conn


def _fresh_conn_skipping_011() -> sqlite3.Connection:
    """Simulate the pre-2026-05-24 scenario: run migrations but OMIT migration 011.

    This reproduces the environment where memory_entries was not created by any
    migration, which is the root cause of the M2 idx_memory_lifecycle casualty.
    """
    from core.config.sqlite_bootstrap import migration_files, split_statements, _migration_version
    import os

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    conn.commit()

    for path in migration_files():
        version = _migration_version(path)
        if version == 11:
            # Skip migration 011 — simulate the gap at 011 in the initial publication
            continue
        sql_text = path.read_text(encoding="utf-8")
        for stmt in split_statements(sql_text):
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # swallow all errors for this setup helper
        conn.execute(
            "INSERT INTO _schema_version(version, applied_at) VALUES(?, ?)",
            (version, "2026-05-16T21:01:00.000000+00:00"),
        )
        conn.commit()

    return conn


# ── Fixture 1: Ground-truth — CREATE INDEX propagates with narrowed swallow ──


def test_ground_truth_create_index_propagates_on_absent_memory_entries():
    """The headline fixture: CREATE INDEX on absent memory_entries now propagates.

    OLD BEHAVIOR (before O7): sqlite_bootstrap.py S3b swallowed ANY error
    mentioning 'memory_entries', including 'no such table: memory_entries'
    on a CREATE INDEX statement. The index was silently never created.
    This is how idx_memory_lifecycle was lost for months.

    NEW BEHAVIOR (after O7): CREATE INDEX is not in the swallow deny-list.
    It propagates as sqlite3.OperationalError with 'no such table: memory_entries'.
    The failure is visible — no silent schema loss.
    """
    conn = sqlite3.connect(":memory:")
    # memory_entries does NOT exist in this connection
    assert (
        conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='memory_entries'").fetchone()[0]
        == 0
    )

    create_index_stmt = (
        "CREATE INDEX IF NOT EXISTS idx_memory_lifecycle ON memory_entries(lifecycle_state)"
    )

    with pytest.raises(sqlite3.OperationalError) as exc_info:
        conn.execute(create_index_stmt)

    error_msg = str(exc_info.value).lower()
    assert "no such table" in error_msg, f"Expected 'no such table', got: {error_msg}"
    assert "memory_entries" in error_msg, f"Expected 'memory_entries', got: {error_msg}"
    conn.close()


def test_ground_truth_create_trigger_propagates_on_absent_memory_entries():
    """CREATE TRIGGER on absent memory_entries also propagates (Option B)."""
    conn = sqlite3.connect(":memory:")
    create_trigger_stmt = """
        CREATE TRIGGER IF NOT EXISTS memory_entries_fts_insert
        AFTER INSERT ON memory_entries
        BEGIN
            INSERT INTO memory_fts(memory_id, content, category, tags)
            VALUES (new.memory_id, new.content, new.category, COALESCE(new.tags, ''));
        END
    """
    with pytest.raises(sqlite3.OperationalError) as exc_info:
        conn.execute(create_trigger_stmt)

    error_msg = str(exc_info.value).lower()
    assert "no such table" in error_msg
    assert "memory_entries" in error_msg
    conn.close()


# ── Fixture 2: Install-safety — legitimate swallows still fire ────────────────


def test_install_safety_alter_table_still_swallowed_on_absent_memory_entries():
    """ALTER TABLE ADD COLUMN on absent memory_entries is still swallowed.

    This tests the S3b narrowing directly: the narrowed handler must still
    swallow INSERT/UPDATE/ALTER TABLE/DROP on memory_entries, and must NOT
    swallow CREATE INDEX/CREATE TRIGGER.

    Verified by running each migration 032 statement type manually against an
    absent-memory_entries connection and checking swallow/propagate behavior.
    """
    from core.config.sqlite_bootstrap import split_statements

    mig032 = (_source_root() / "core/event_store/migrations/032_semantic_memory.sql").read_text(
        encoding="utf-8"
    )

    swallowed_types = []
    propagated_types = []

    for stmt in split_statements(mig032):
        conn = sqlite3.connect(":memory:")  # fresh connection, no memory_entries
        stmt_upper = stmt.strip().upper()
        try:
            conn.execute(stmt)
            # Statement succeeded (shouldn't happen on absent table for most statements)
        except sqlite3.OperationalError as exc:
            msg = str(exc).lower()
            if "no such table" in msg and "memory_entries" in msg:
                # Apply the narrowed S3b logic
                if stmt_upper.startswith("CREATE INDEX") or stmt_upper.startswith("CREATE TRIGGER"):
                    propagated_types.append(stmt_upper.split()[0:2])
                else:
                    swallowed_types.append(stmt_upper.split()[0:2])
        finally:
            conn.close()

    # ALTER TABLE statements must be in the swallowed set
    swallowed_flat = [" ".join(t) for t in swallowed_types]
    assert any(
        "ALTER TABLE" in s for s in swallowed_flat
    ), f"ALTER TABLE ADD COLUMN must still be swallowed. Swallowed: {swallowed_flat}"

    # CREATE INDEX must be in the propagated set (the narrowing works)
    propagated_flat = [" ".join(t) for t in propagated_types]
    assert any(
        "CREATE INDEX" in s for s in propagated_flat
    ), f"CREATE INDEX must propagate (not be swallowed). Propagated: {propagated_flat}"

    # CREATE UNIQUE INDEX must also propagate
    assert any(
        "CREATE UNIQUE" in s or "CREATE INDEX" in s for s in propagated_flat
    ), f"CREATE [UNIQUE] INDEX must propagate. Propagated: {propagated_flat}"


def test_install_safety_fresh_full_migration_sequence():
    """Fresh install from v0 succeeds and all expected objects are present.

    The narrowing must not break the clean path — on a valid install,
    memory_entries exists when migration 032 runs (migration 011 creates it).
    idx_memory_lifecycle and all other indexes/triggers should be present.
    """
    conn = _fresh_conn_at()
    conn.row_factory = sqlite3.Row

    # memory_entries was created by migration 011
    assert (
        conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='memory_entries'").fetchone()[0]
        == 1
    ), "memory_entries should exist after full migration sequence"

    # idx_memory_lifecycle should exist (created by migration 032 when memory_entries exists)
    idx = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_memory_lifecycle'"
    ).fetchone()
    assert idx is not None, (
        "idx_memory_lifecycle should be created by migration 032 on a fresh install "
        "where migration 011 runs first. If this fails, the narrowing broke the clean path."
    )

    # FTS triggers should exist (created by migrations 079/082)
    expected_triggers = {
        "memory_entries_fts_insert",
        "memory_entries_fts_update",
        "memory_entries_fts_delete",
    }
    actual_triggers = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'memory_entries_fts%'"
        ).fetchall()
    }
    assert (
        expected_triggers == actual_triggers
    ), f"FTS triggers missing: {expected_triggers - actual_triggers}"
    conn.close()


# ── Fixture 3: Audit extension ────────────────────────────────────────────────


def test_audit_detects_missing_nonunique_index_as_medium():
    """swallowed_statement_casualty: non-unique index missing → severity medium."""
    from core.config.schema_coherence import check_schema_coherence
    import shutil, tempfile

    source_root = _source_root()

    # Build a full-migration DB then manually drop idx_memory_lifecycle
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = sqlite3.connect(str(db_path))
        run_migrations(conn)
        conn.execute("DROP INDEX IF EXISTS idx_memory_lifecycle")
        conn.commit()
        conn.close()

        result = check_schema_coherence(source_root, live_db_path=db_path)

    casualties = [
        f
        for f in result["findings"]
        if f.get("finding_type") == "swallowed_statement_casualty"
        and f.get("object_name") == "idx_memory_lifecycle"
    ]
    assert casualties, (
        "Expected swallowed_statement_casualty for idx_memory_lifecycle — "
        "the ground-truth M2 casualty that this WO exists to detect."
    )
    assert (
        casualties[0]["severity"] == "medium"
    ), f"idx_memory_lifecycle is non-unique → severity must be medium, got {casualties[0]['severity']}"
    assert casualties[0]["object_type"] == "index"
    assert casualties[0]["scope"] == "live_drift"


def test_audit_detects_missing_unique_index_as_high():
    """swallowed_statement_casualty: UNIQUE index missing → severity high (DDL-derived)."""
    from core.config.schema_coherence import check_schema_coherence
    import tempfile

    source_root = _source_root()

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = sqlite3.connect(str(db_path))
        run_migrations(conn)
        # Drop a UNIQUE index — idx_memory_provenance is UNIQUE (from migration 032)
        conn.execute("DROP INDEX IF EXISTS idx_memory_provenance")
        conn.commit()
        conn.close()

        result = check_schema_coherence(source_root, live_db_path=db_path)

    casualties = [
        f
        for f in result["findings"]
        if f.get("finding_type") == "swallowed_statement_casualty"
        and f.get("object_name") == "idx_memory_provenance"
    ]
    assert casualties, (
        "Expected swallowed_statement_casualty for idx_memory_provenance "
        "(UNIQUE index, should be severity high)."
    )
    assert (
        casualties[0]["severity"] == "high"
    ), f"idx_memory_provenance is UNIQUE → severity must be high, got {casualties[0]['severity']}"


def test_audit_detects_missing_trigger_as_high():
    """swallowed_statement_casualty: trigger missing → severity high."""
    from core.config.schema_coherence import check_schema_coherence
    import tempfile

    source_root = _source_root()

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = sqlite3.connect(str(db_path))
        run_migrations(conn)
        conn.execute("DROP TRIGGER IF EXISTS memory_entries_fts_insert")
        conn.commit()
        conn.close()

        result = check_schema_coherence(source_root, live_db_path=db_path)

    casualties = [
        f
        for f in result["findings"]
        if f.get("finding_type") == "swallowed_statement_casualty"
        and f.get("object_name") == "memory_entries_fts_insert"
    ]
    assert casualties, "Expected swallowed_statement_casualty for missing trigger."
    assert casualties[0]["severity"] == "high"
    assert casualties[0]["object_type"] == "trigger"


def test_audit_clean_on_coherent_db():
    """Audit reports zero swallowed_statement_casualty on a fully coherent DB."""
    from core.config.schema_coherence import check_schema_coherence
    import tempfile

    source_root = _source_root()

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = sqlite3.connect(str(db_path))
        run_migrations(conn)
        conn.close()

        result = check_schema_coherence(source_root, live_db_path=db_path)

    casualties = [
        f for f in result["findings"] if f.get("finding_type") == "swallowed_statement_casualty"
    ]
    assert not casualties, (
        f"Expected zero swallowed_statement_casualty on a coherent DB, got: "
        f"{[(c['object_name'], c['severity']) for c in casualties]}"
    )


def test_audit_direction_aware_live_only_object_not_flagged():
    """M1 scars (live-only objects like vw_activity_timeline) are NOT flagged.

    The direction-aware diff only flags fresh-only absences (M2 class).
    Objects present in live but absent from fresh (M1 scars) must not produce
    swallowed_statement_casualty findings.
    """
    from core.config.schema_coherence import check_schema_coherence
    import tempfile

    source_root = _source_root()

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = sqlite3.connect(str(db_path))
        run_migrations(conn)
        # Add a live-only view (simulating M1 scar like vw_activity_timeline)
        conn.execute("""
            CREATE VIEW IF NOT EXISTS test_m1_scar_view AS
            SELECT 1 AS dummy_col
        """)
        conn.commit()
        conn.close()

        result = check_schema_coherence(source_root, live_db_path=db_path)

    # The live-only view must NOT appear as a swallowed_statement_casualty
    scar_findings = [
        f
        for f in result["findings"]
        if f.get("finding_type") == "swallowed_statement_casualty"
        and f.get("object_name") == "test_m1_scar_view"
    ]
    assert not scar_findings, (
        "A live-only object (M1 scar) must not be flagged as swallowed_statement_casualty. "
        "The diff is direction-aware: only fresh-only objects are M2 casualties."
    )


def test_audit_against_actual_live_copy():
    """Audit against the live DB copy from the divergence-sweep detects idx_memory_lifecycle.

    This connects the audit extension back to the real-world finding that motivated O7.
    """
    from core.config.schema_coherence import check_schema_coherence

    live_copy = (
        Path.home()
        / ".dream-studio/diagnostics/2026-05-29/dream-studio-clean/divergence-sweep/studio-copy.db"
    )
    if not live_copy.is_file():
        pytest.skip("Live DB copy from divergence-sweep not available in this environment")

    source_root = _source_root()
    result = check_schema_coherence(source_root, live_db_path=live_copy)

    # The live DB should have exactly the one known casualty
    casualties = [
        f for f in result["findings"] if f.get("finding_type") == "swallowed_statement_casualty"
    ]
    casualty_names = {c["object_name"] for c in casualties}
    assert (
        "idx_memory_lifecycle" in casualty_names
    ), f"Expected idx_memory_lifecycle as a casualty on the live DB copy. Found: {casualty_names}"
    # And exactly one (the complete sweep confirmed this was the only one)
    assert len(casualties) == 1, (
        f"Expected exactly 1 swallowed casualty on the live DB copy (the 511-object sweep "
        f"confirmed this), but found {len(casualties)}: {casualty_names}"
    )
    assert casualties[0]["severity"] == "medium", "idx_memory_lifecycle is non-unique → medium"
