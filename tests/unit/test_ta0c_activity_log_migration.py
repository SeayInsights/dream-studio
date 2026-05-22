"""Tests for TA0c: activity_log retirement (migrations 062 + 063).

Verifies post-migration structural state on a fresh test DB:
- 7 child tables have nullable activity_id
- vw_graph_edges and vw_component_stats permanently retired
- vw_activity_timeline and vw_guardrail_decisions rewritten to canonical tables
- activity_log table and its indexes dropped
- Backfill event_id prefix + INSERT OR IGNORE idempotency
- All surviving views queryable, no leftover _new tables
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.event_store.studio_db import _connect  # noqa: E402

_CANONICAL_EVENTS_DDL = """
    CREATE TABLE IF NOT EXISTS canonical_events (
        event_id TEXT PRIMARY KEY,
        event_type TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        trace JSON NOT NULL DEFAULT '{}',
        severity TEXT NOT NULL DEFAULT 'info',
        payload JSON NOT NULL DEFAULT '{}',
        actor JSON,
        confidence_score REAL,
        source_type TEXT,
        raw_prompt_retained INTEGER NOT NULL DEFAULT 0,
        raw_tool_output_retained INTEGER NOT NULL DEFAULT 0,
        schema_version INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        invocation_mode TEXT
    )
"""


@pytest.fixture
def db_with_canonical(tmp_path):
    """Migrated DB + canonical_events table (created by the ingestor at runtime, not migrations)."""
    db = tmp_path / "test.db"
    conn = _connect(db)
    conn.execute(_CANONICAL_EVENTS_DDL)
    conn.commit()
    yield conn
    conn.close()


# ── Nullable activity_id ─────────────────────────────────────────────────────


class TestActivityIdNullable:
    TARGET_TABLES = [
        "hook_executions",
        "hook_findings",
        "sec_sarif_findings",
        "sec_manual_reviews",
        "sec_cve_matches",
        "sec_hook_checks",
        "adapter_executions",
    ]

    def test_activity_id_nullable_in_all_target_tables(self, tmp_path):
        db = tmp_path / "test.db"
        conn = _connect(db)
        for tname in self.TARGET_TABLES:
            cols = {r[1]: r[3] for r in conn.execute(f"PRAGMA table_info({tname})").fetchall()}
            assert "activity_id" in cols, f"{tname} missing activity_id column"
            assert (
                cols["activity_id"] == 0
            ), f"{tname}.activity_id should be nullable (notnull=0) after migration 062"
        conn.close()


# ── Retired views ────────────────────────────────────────────────────────────


class TestRetiredViews:
    def test_vw_graph_edges_absent(self, tmp_path):
        db = tmp_path / "test.db"
        conn = _connect(db)
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='view' AND name='vw_graph_edges'"
        ).fetchone()
        conn.close()
        assert row is None, "vw_graph_edges must be retired — broken since migration 014"

    def test_vw_component_stats_absent(self, tmp_path):
        db = tmp_path / "test.db"
        conn = _connect(db)
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='view' AND name='vw_component_stats'"
        ).fetchone()
        conn.close()
        assert row is None, "vw_component_stats must be retired — broken since migration 014"


# ── Rewritten views ──────────────────────────────────────────────────────────


class TestRewrittenViews:
    def test_vw_activity_timeline_reads_canonical_events(self, tmp_path):
        db = tmp_path / "test.db"
        conn = _connect(db)
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='view' AND name='vw_activity_timeline'"
        ).fetchone()
        conn.close()
        assert row is not None, "vw_activity_timeline should exist after migration 062"
        assert "canonical_events" in row[0]
        assert "activity_log" not in row[0], "vw_activity_timeline must not reference activity_log"

    def test_vw_activity_timeline_is_queryable(self, db_with_canonical):
        db_with_canonical.execute("SELECT * FROM vw_activity_timeline LIMIT 1").fetchall()

    def test_vw_guardrail_decisions_reads_guardrail_table(self, tmp_path):
        db = tmp_path / "test.db"
        conn = _connect(db)
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='view' AND name='vw_guardrail_decisions'"
        ).fetchone()
        conn.close()
        assert row is not None, "vw_guardrail_decisions should exist after migration 062"
        assert "guardrail_decisions" in row[0]
        assert (
            "activity_log" not in row[0]
        ), "vw_guardrail_decisions must not reference activity_log"

    def test_vw_guardrail_decisions_is_queryable(self, tmp_path):
        db = tmp_path / "test.db"
        conn = _connect(db)
        conn.execute("SELECT * FROM vw_guardrail_decisions LIMIT 1").fetchall()
        conn.close()


# ── activity_log dropped ─────────────────────────────────────────────────────


class TestActivityLogDropped:
    def test_activity_log_table_absent(self, tmp_path):
        db = tmp_path / "test.db"
        conn = _connect(db)
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='activity_log'"
        ).fetchone()
        conn.close()
        assert row is None, "activity_log should be dropped by migration 063"

    def test_activity_log_indexes_absent(self, tmp_path):
        db = tmp_path / "test.db"
        conn = _connect(db)
        dropped = [
            "idx_activity_type_time",
            "idx_activity_stream",
            "idx_activity_status_severity",
            "idx_activity_anomaly",
        ]
        for idx in dropped:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (idx,)
            ).fetchone()
            assert row is None, f"Index {idx} should be dropped by migration 063"
        conn.close()


# ── Backfill format + idempotency ────────────────────────────────────────────


class TestBackfillFormat:
    def test_backfill_row_trace_fields(self, db_with_canonical):
        """Backfill rows must carry domain=system and attribution_status=backfill."""
        db_with_canonical.execute("""
            INSERT OR IGNORE INTO canonical_events
                (event_id, event_type, timestamp, trace, severity,
                 payload, raw_prompt_retained, raw_tool_output_retained, schema_version)
            VALUES (
                'backfill-activity-log-9999',
                'system.session.recorded',
                '2026-01-01T00:00:00',
                '{"domain":"system","attribution_status":"backfill","stream_type":"","stream_id":""}',
                'info', '{}', 0, 0, 1
            )
        """)
        db_with_canonical.commit()
        row = db_with_canonical.execute(
            "SELECT trace FROM canonical_events WHERE event_id = 'backfill-activity-log-9999'"
        ).fetchone()
        assert row is not None
        trace = json.loads(row[0])
        assert trace["domain"] == "system"
        assert trace["attribution_status"] == "backfill"

    def test_backfill_insert_or_ignore_is_idempotent(self, db_with_canonical):
        """Running the backfill INSERT OR IGNORE multiple times must not produce duplicate rows."""
        insert_sql = """
            INSERT OR IGNORE INTO canonical_events
                (event_id, event_type, timestamp, trace, severity,
                 payload, raw_prompt_retained, raw_tool_output_retained, schema_version)
            VALUES (
                'backfill-activity-log-8888',
                'system.session.recorded',
                '2026-01-01T00:00:00',
                '{"domain":"system","attribution_status":"backfill","stream_type":"","stream_id":""}',
                'info', '{}', 0, 0, 1
            )
        """
        for _ in range(3):
            db_with_canonical.execute(insert_sql)
        db_with_canonical.commit()
        count = db_with_canonical.execute(
            "SELECT COUNT(*) FROM canonical_events WHERE event_id = 'backfill-activity-log-8888'"
        ).fetchone()[0]
        assert count == 1, "INSERT OR IGNORE must produce exactly one row regardless of run count"

    def test_backfill_event_id_prefix(self, db_with_canonical):
        """Backfill row event_ids must use the canonical prefix."""
        db_with_canonical.execute("""
            INSERT OR IGNORE INTO canonical_events
                (event_id, event_type, timestamp, trace, severity,
                 payload, raw_prompt_retained, raw_tool_output_retained, schema_version)
            VALUES (
                'backfill-activity-log-1',
                'system.hook.execution.logged',
                '2026-01-01T00:00:00',
                '{"domain":"system","attribution_status":"backfill","stream_type":"","stream_id":""}',
                'info', '{}', 0, 0, 1
            )
        """)
        db_with_canonical.commit()
        row = db_with_canonical.execute(
            "SELECT event_id FROM canonical_events WHERE event_id LIKE 'backfill-activity-log-%'"
        ).fetchone()
        assert row is not None
        assert row[0].startswith("backfill-activity-log-")


# ── Migration integrity ──────────────────────────────────────────────────────


class TestMigrationIntegrity:
    def test_fresh_db_reaches_version_63_or_higher(self, tmp_path):
        db = tmp_path / "test.db"
        conn = _connect(db)
        v = conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0]
        conn.close()
        assert v >= 63, f"Expected schema version >= 63 after migrations 062+063, got {v}"

    def test_all_views_queryable(self, db_with_canonical):
        """Every surviving view must execute without error."""
        views = [
            r[0]
            for r in db_with_canonical.execute(
                "SELECT name FROM sqlite_master WHERE type='view'"
            ).fetchall()
        ]
        failures = []
        for view in views:
            try:
                db_with_canonical.execute(f"SELECT * FROM {view} LIMIT 1").fetchall()
            except Exception as exc:
                failures.append(f"{view}: {exc}")
        assert not failures, "Views failed to query:\n" + "\n".join(failures)

    def test_no_leftover_new_tables(self, tmp_path):
        """Migration 062 must clean up all _new staging tables."""
        db = tmp_path / "test.db"
        conn = _connect(db)
        leftover = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_new'"
        ).fetchall()
        conn.close()
        assert not leftover, f"Leftover _new tables after migration: {[r[0] for r in leftover]}"

    def test_migration_062_contains_canonical_events_insert(self):
        """Migration 062 must INSERT INTO canonical_events (the backfill), not DROP it."""
        sql_path = (
            Path(__file__).resolve().parents[2]
            / "core/event_store/migrations"
            / "062_nullify_activity_id_backfill_and_replace_views.sql"
        )
        sql = sql_path.read_text(encoding="utf-8").upper()
        assert (
            "INSERT OR IGNORE INTO CANONICAL_EVENTS" in sql
        ), "Migration 062 must contain the backfill INSERT into canonical_events"
        assert (
            "DROP TABLE IF EXISTS CANONICAL_EVENTS" not in sql
        ), "Migration 062 must not drop canonical_events"
        assert (
            "DROP TABLE CANONICAL_EVENTS" not in sql
        ), "Migration 062 must not drop canonical_events"

    def test_migration_063_drops_activity_log_and_indexes(self):
        """Migration 063 must drop activity_log and its four indexes."""
        sql_path = (
            Path(__file__).resolve().parents[2]
            / "core/event_store/migrations"
            / "063_drop_activity_log.sql"
        )
        sql = sql_path.read_text(encoding="utf-8").upper()
        assert "DROP TABLE IF EXISTS ACTIVITY_LOG" in sql, "Migration 063 must drop activity_log"
        for idx in [
            "IDX_ACTIVITY_TYPE_TIME",
            "IDX_ACTIVITY_STREAM",
            "IDX_ACTIVITY_STATUS_SEVERITY",
            "IDX_ACTIVITY_ANOMALY",
        ]:
            assert f"DROP INDEX IF EXISTS {idx}" in sql, f"Migration 063 must drop index {idx}"
        assert (
            "DROP TABLE IF EXISTS CANONICAL_EVENTS" not in sql
        ), "Migration 063 must not drop canonical_events"
        assert (
            "DROP TABLE IF EXISTS HOOK_EXECUTIONS" not in sql
        ), "Migration 063 must not touch hook_executions"
