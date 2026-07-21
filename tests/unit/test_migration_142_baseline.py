"""Data-preservation proof for the WO-SQUASH-BASELINE migration (5fd84891).

Migrations 001-141 were collapsed into a single lean baseline,
`142_lean_baseline.sql` (DROP TABLE/VIEW IF EXISTS for tombstoned names,
then CREATE TABLE/INDEX/VIEW/TRIGGER IF NOT EXISTS for the fresh schema).
Since the individual pre-squash migration files no longer exist, the
historical "build a v134 DB, seed legacy rows, replay migration 135" style
test is no longer possible. Instead this proves the property that actually
matters for a live authority DB: applying (or re-applying) the baseline to a
DB that already has data in KEEP tables never loses rows or drifts the
schema, because every statement in the file is DROP ... IF EXISTS or
CREATE ... IF NOT EXISTS.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import latest_migration_version, run_migrations

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = REPO_ROOT / "core" / "event_store" / "migrations" / "142_lean_baseline.sql"

SEED_TABLES = ("business_work_orders", "ai_canonical_events", "raw_sessions", "memory_entries")


@pytest.fixture
def baseline_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    run_migrations(conn, apply_unreleased=True)
    conn.commit()
    return conn


def _seed(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, status, created_at)"
        " VALUES ('wo-preserve-1', 'proj-preserve-1', 'mile-preserve-1',"
        "         'Preserve me', 'in_progress', datetime('now'))"
    )
    conn.execute(
        "INSERT INTO ai_canonical_events (event_id, event_type, event_timestamp, payload, trace)"
        " VALUES ('evt-preserve-1', 'test.preserved', datetime('now'), '{}', '{}')"
    )
    conn.execute(
        "INSERT INTO raw_sessions (session_id, project_id, started_at)"
        " VALUES ('sess-preserve-1', 'proj-preserve-1', datetime('now'))"
    )
    conn.execute(
        "INSERT INTO memory_entries (memory_id, source, category, content, created_at)"
        " VALUES ('mem-preserve-1', 'test', 'gotcha', 'preserve this memory', datetime('now'))"
    )
    conn.commit()


def _row_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
        for table in SEED_TABLES
    }


def _schema_object_count(conn: sqlite3.Connection) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type IN ('table', 'index', 'view', 'trigger')"
    ).fetchone()[0]


def test_baseline_reapply_preserves_seeded_keep_table_rows(baseline_db: sqlite3.Connection) -> None:
    """Seed rows into KEEP tables, re-apply 142_lean_baseline.sql verbatim via
    executescript(), and assert every row survives untouched.

    This is the practical equivalent of what a live authority DB experiences
    on every `ds` invocation once it is at schema version 142 (Design point 3:
    a current DB applies 142 as a no-op) -- proven here directly against the
    baseline's own SQL text (DROP ... IF EXISTS / CREATE ... IF NOT EXISTS),
    independent of the runner's separate version-gate short-circuit.
    """
    conn = baseline_db
    _seed(conn)
    before_counts = _row_counts(conn)
    assert all(count == 1 for count in before_counts.values()), before_counts

    sql_text = BASELINE_PATH.read_text(encoding="utf-8")
    conn.executescript(sql_text)

    after_counts = _row_counts(conn)
    assert after_counts == before_counts, (
        f"row counts changed after re-applying the baseline: "
        f"before={before_counts} after={after_counts}"
    )

    # Spot-check the actual row content (not just the count) survived intact.
    row = conn.execute(
        "SELECT title, status FROM business_work_orders WHERE work_order_id = 'wo-preserve-1'"
    ).fetchone()
    assert row == ("Preserve me", "in_progress")


def test_baseline_sql_is_self_idempotent_on_a_fresh_db() -> None:
    """The baseline's own SQL must be self-idempotent: applying 142 twice to a
    fresh DB creates no duplicate or drifted schema objects, because every
    statement is DROP ... IF EXISTS / CREATE ... IF NOT EXISTS.

    This is tested in ISOLATION (a fresh DB with only 142 applied), NOT against a
    full-chain head DB. Re-applying 142 alone on top of the full chain would
    resurrect the tables that later forward migrations (147/148/149, WO-SCHEMALEAN)
    legitimately DROP — that is the sanctioned immutable-baseline + forward-drop
    pattern (migrations are immutable history; corrections are forward migrations),
    not a defect. The production path — the version-gated runner never re-applying
    142 once a DB is at head — is proven a true no-op by
    test_run_migrations_against_a_db_already_at_head_is_a_true_no_op below.
    """
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    sql_text = BASELINE_PATH.read_text(encoding="utf-8")
    conn.executescript(sql_text)
    before = _schema_object_count(conn)

    conn.executescript(sql_text)

    after = _schema_object_count(conn)
    conn.close()
    assert after == before, f"142 SQL is not self-idempotent: before={before} after={after}"


def test_run_migrations_against_a_db_already_at_head_is_a_true_no_op(
    baseline_db: sqlite3.Connection,
) -> None:
    """run_migrations() against a DB already at the latest schema version must
    not re-execute anything (the version-gate short-circuit) -- the actual code
    path a live authority DB takes on every future `ds` invocation once it has
    migrated to head. Version-agnostic: the baseline is 142, forward migrations
    (143, ...) advance head, and re-running at head stays a no-op."""
    conn = baseline_db
    _seed(conn)
    before_counts = _row_counts(conn)

    version = run_migrations(conn, apply_unreleased=True)

    assert version == latest_migration_version()
    assert _row_counts(conn) == before_counts
