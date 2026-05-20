"""Workstream 5e gate: 049_work_order_type.sql schema and data assertions."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import split_statements


def _apply_safe(conn: sqlite3.Connection, sql_text: str) -> None:
    """Apply migration SQL skipping 'duplicate column name' errors (mirrors run_migrations)."""
    for stmt in split_statements(sql_text):
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError as exc:
            if "duplicate column name" in str(exc).lower():
                continue
            raise


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_048 = REPO_ROOT / "core" / "event_store" / "migrations" / "048_project_spine.sql"
MIGRATION_049 = REPO_ROOT / "core" / "event_store" / "migrations" / "049_work_order_type.sql"

VALID_TYPE_IDS = frozenset(
    [
        "ui_component",
        "ui_page",
        "api_endpoint",
        "authentication",
        "saas_feature",
        "data_pipeline",
        "game_mechanic",
        "deployment",
        "infrastructure",
        "documentation",
    ]
)

_NOW = "2026-05-16T00:00:00+00:00"


def _fresh_db() -> sqlite3.Connection:
    """Return an in-memory connection with migrations 048 + 049 applied."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(MIGRATION_048.read_text(encoding="utf-8"))
    conn.executescript(MIGRATION_049.read_text(encoding="utf-8"))
    conn.commit()
    return conn


# ── Migration cleanliness ─────────────────────────────────────────────────────


def test_migration_runs_cleanly_on_fresh_db():
    """Both migration files apply without error on a fresh in-memory DB."""
    conn = _fresh_db()
    conn.close()


def test_ds_work_order_types_table_exists():
    conn = _fresh_db()
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='ds_work_order_types'"
    ).fetchone()
    conn.close()
    assert row is not None


def test_ds_work_order_types_has_exactly_10_rows():
    conn = _fresh_db()
    count = conn.execute("SELECT COUNT(*) FROM ds_work_order_types").fetchone()[0]
    conn.close()
    assert count == 10


# ── Column behavioural tests ──────────────────────────────────────────────────


def test_work_order_type_column_accepts_valid_type():
    conn = _fresh_db()
    conn.execute("INSERT INTO ds_projects VALUES ('p1','P','','active',?,?)", (_NOW, _NOW))
    conn.execute(
        "INSERT INTO ds_work_orders"
        " (work_order_id, project_id, title, status, work_order_type, created_at, updated_at)"
        " VALUES ('wo1','p1','WO','open','ui_component',?,?)",
        (_NOW, _NOW),
    )
    row = conn.execute(
        "SELECT work_order_type FROM ds_work_orders WHERE work_order_id='wo1'"
    ).fetchone()
    conn.close()
    assert row[0] == "ui_component"


def test_work_order_type_column_accepts_null_for_backward_compat():
    """Existing rows with no type must remain valid (no NOT NULL constraint)."""
    conn = _fresh_db()
    conn.execute("INSERT INTO ds_projects VALUES ('p1','P','','active',?,?)", (_NOW, _NOW))
    conn.execute(
        "INSERT INTO ds_work_orders"
        " (work_order_id, project_id, title, status, work_order_type, created_at, updated_at)"
        " VALUES ('wo1','p1','WO','open',NULL,?,?)",
        (_NOW, _NOW),
    )
    row = conn.execute(
        "SELECT work_order_type FROM ds_work_orders WHERE work_order_id='wo1'"
    ).fetchone()
    conn.close()
    assert row[0] is None


# ── Type-registry data assertions ─────────────────────────────────────────────


def test_all_type_ids_match_expected_set():
    """Every row in ds_work_order_types has a type_id from the canonical 10."""
    conn = _fresh_db()
    rows = conn.execute("SELECT type_id FROM ds_work_order_types").fetchall()
    conn.close()
    found = {r[0] for r in rows}
    assert found == VALID_TYPE_IDS


@pytest.mark.parametrize("type_id", sorted(VALID_TYPE_IDS - {"documentation"}))
def test_build_executor_non_null_for_non_documentation_types(type_id):
    """Every non-documentation type must ship a build_executor."""
    conn = _fresh_db()
    row = conn.execute(
        "SELECT build_executor FROM ds_work_order_types WHERE type_id = ?",
        (type_id,),
    ).fetchone()
    conn.close()
    assert row is not None, f"type_id '{type_id}' not found"
    assert row[0] is not None, f"build_executor is NULL for type '{type_id}'"


def test_post_build_gate_null_only_for_documentation():
    """post_build_gate must be non-null for every type except documentation."""
    conn = _fresh_db()
    rows = conn.execute("SELECT type_id, post_build_gate FROM ds_work_order_types").fetchall()
    conn.close()
    for type_id, gate in rows:
        if type_id == "documentation":
            assert gate is None, "documentation post_build_gate should be null"
        else:
            assert gate is not None, f"post_build_gate is null for '{type_id}'"


def test_migration_idempotent_via_insert_or_ignore():
    """Applying migration 049 twice must not raise a UNIQUE constraint error."""
    conn = _fresh_db()
    _apply_safe(conn, MIGRATION_049.read_text(encoding="utf-8"))
    count = conn.execute("SELECT COUNT(*) FROM ds_work_order_types").fetchone()[0]
    conn.close()
    assert count == 10
