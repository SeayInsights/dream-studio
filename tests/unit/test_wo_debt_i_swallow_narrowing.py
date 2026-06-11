"""Tests for WO-DEBT-I: swallow-handler narrowing for the two remaining broad
'no such table' clauses in sqlite_bootstrap.py — token_usage_records /
ai_usage_operational_records (migration 081 tolerance) and the ds_* project-spine
tables (migration 070 tolerance).

O7 narrowed memory_entries; WO-I narrowed fts_gotchas/ds_documents/canonical_events.
This applies the same statement-type-aware pattern to the last broad clauses: a
CREATE INDEX / CREATE TRIGGER on an absent table must raise (M2-class casualty —
the schema object would silently never exist), while data statements remain
graceful degradation.

The real-handler tests drive run_migrations() against a synthetic migration set
(monkeypatched migration_files), so the actual handler in sqlite_bootstrap.py is
exercised — not a mirror of its logic.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.config import sqlite_bootstrap
from core.config.sqlite_bootstrap import run_migrations


def _run_synthetic_migration(monkeypatch, tmp_path: Path, sql: str) -> sqlite3.Connection:
    """Run a single synthetic migration through the real run_migrations handler."""
    mig = tmp_path / "001_synthetic.sql"
    mig.write_text(sql, encoding="utf-8")
    monkeypatch.setattr(sqlite_bootstrap, "migration_files", lambda: [mig])
    conn = sqlite3.connect(":memory:")
    run_migrations(conn)
    return conn


# ── token_usage_records / ai_usage_operational_records narrowing ──────────────


def test_create_index_on_absent_token_usage_records_propagates(monkeypatch, tmp_path):
    """CREATE INDEX on absent token_usage_records must raise through the real handler.

    Before WO-DEBT-I the broad clause swallowed ANY 'no such table' error
    mentioning token_usage_records — the same mechanism that ate
    idx_memory_lifecycle from migration 032 (M2 class).
    """
    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        _run_synthetic_migration(
            monkeypatch,
            tmp_path,
            "CREATE INDEX IF NOT EXISTS idx_token_usage_scope "
            "ON token_usage_records(project_id);",
        )


def test_create_trigger_on_absent_ai_usage_operational_records_propagates(monkeypatch, tmp_path):
    """CREATE TRIGGER on absent ai_usage_operational_records must raise."""
    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        _run_synthetic_migration(
            monkeypatch,
            tmp_path,
            "CREATE TRIGGER IF NOT EXISTS trg_ai_usage_test "
            "AFTER INSERT ON ai_usage_operational_records BEGIN SELECT 1; END;",
        )


def test_insert_select_on_absent_token_usage_records_still_swallowed(monkeypatch, tmp_path):
    """Migration 081's INSERT...SELECT shape remains graceful on partial fixtures.

    The narrowing must not break the fixture tolerance the clause exists for:
    data statements on the absent table are swallowed and the migration is
    marked applied.
    """
    conn = _run_synthetic_migration(
        monkeypatch,
        tmp_path,
        "CREATE TABLE IF NOT EXISTS token_usage_records_new (token_usage_id TEXT PRIMARY KEY);\n"
        "INSERT INTO token_usage_records_new SELECT token_usage_id FROM token_usage_records;",
    )
    assert sqlite_bootstrap.applied_schema_version(conn) == 1
    conn.close()


# ── ds_* project-spine narrowing ───────────────────────────────────────────────


def test_create_index_on_absent_ds_milestones_propagates(monkeypatch, tmp_path):
    """Migration 048's idx_ds_milestones_project shape must raise if ds_milestones is absent."""
    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        _run_synthetic_migration(
            monkeypatch,
            tmp_path,
            "CREATE INDEX IF NOT EXISTS idx_ds_milestones_project " "ON ds_milestones(project_id);",
        )


def test_insert_select_on_absent_ds_projects_still_swallowed(monkeypatch, tmp_path):
    """Migration 070's ds_* → business_* copy shape remains graceful degradation."""
    conn = _run_synthetic_migration(
        monkeypatch,
        tmp_path,
        "CREATE TABLE IF NOT EXISTS business_projects (project_id TEXT PRIMARY KEY);\n"
        "INSERT INTO business_projects SELECT project_id FROM ds_projects;",
    )
    assert sqlite_bootstrap.applied_schema_version(conn) == 1
    conn.close()


# ── Clean path: the real migration sequence creates every covered index at the
# schema version where it is expected to exist. ds_* indexes live between
# migrations 048/053 and 070 (which drops the ds_* tables after the business_*
# copy). The usage-table indexes live between 037/043 and 081 (which rebuilds
# both tables and does not recreate their indexes — a pre-existing migration-081
# omission unrelated to the swallow handler; tracked separately).


def _index_names(conn: sqlite3.Connection) -> set[str]:
    return {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
    }


def test_migration_sequence_creates_ds_indexes_before_070():
    conn = sqlite3.connect(":memory:")
    run_migrations(conn, target_version=69)

    expected = {
        "idx_ds_milestones_project",
        "idx_ds_work_orders_project",
        "idx_ds_work_orders_milestone",
        "idx_ds_tasks_work_order",
        "idx_ds_tasks_project",
        "idx_ds_design_briefs_project",
    }
    missing = expected - _index_names(conn)
    assert not missing, f"ds_* indexes missing at schema v69: {missing}"
    conn.close()


def test_migration_sequence_creates_usage_indexes_before_081():
    conn = sqlite3.connect(":memory:")
    run_migrations(conn, target_version=80)

    expected = {
        "idx_token_usage_scope",
        "idx_ai_usage_operational_scope",
        "idx_ai_usage_operational_process",
    }
    missing = expected - _index_names(conn)
    assert not missing, f"usage-table indexes missing at schema v80: {missing}"
    conn.close()


_USAGE_INDEXES = {
    "idx_token_usage_scope",
    "idx_ai_usage_operational_scope",
    "idx_ai_usage_operational_process",
}


def test_migration_117_recreates_usage_indexes_fresh_install():
    """Fresh-install path: full sequence up to latest should include all three indexes."""
    conn = sqlite3.connect(":memory:")
    run_migrations(conn)
    missing = _USAGE_INDEXES - _index_names(conn)
    assert not missing, (
        f"usage-table indexes missing after full migration sequence: {missing}. "
        "Migration 117 should recreate indexes dropped by migration 081."
    )
    conn.close()


def test_migration_117_recreates_usage_indexes_upgrade_path():
    """Upgrade path: run to v116, confirm indexes absent, then complete to HEAD."""
    conn = sqlite3.connect(":memory:")
    run_migrations(conn, target_version=116)

    # After migration 081 the tables are reconstructed and indexes dropped.
    # No migration between 082 and 116 recreates them — confirm absence.
    present_before = _USAGE_INDEXES & _index_names(conn)
    assert (
        not present_before
    ), f"Expected indexes to be absent at v116 (dropped by 081), but found: {present_before}"

    # Continue from v116 to HEAD — migration 117 should recreate them.
    run_migrations(conn)
    missing = _USAGE_INDEXES - _index_names(conn)
    assert not missing, (
        f"usage-table indexes missing after upgrading from v116: {missing}. "
        "Migration 117 should recreate indexes dropped by migration 081."
    )
    conn.close()
