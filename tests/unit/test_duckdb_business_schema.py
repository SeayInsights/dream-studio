"""Tests for DuckDB analytics store schema (WO-TS3 task 1 / WO-TS4 correction).

WO-TS4 correction: wrong-scope business entity tables (duckdb_projects,
duckdb_milestones, duckdb_work_orders, duckdb_tasks, duckdb_design_briefs,
duckdb_projection_cursor) were removed. Only analytics tables belong here.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import duckdb  # noqa: E402
import pytest  # noqa: E402

from core.analytics.duckdb_store import connect_analytics, ensure_analytics_schema  # noqa: E402

_EXPECTED_ANALYTICS_TABLES = {
    "duckdb_execution_events",
    "events_fact",
    # WO-TOKEN-VIEW-WIDEN: pricing projection of core/pricing/claude_models.py,
    # joined by the token_usage_records view to derive estimated_cost.
    "token_model_pricing",
}

_EXPECTED_ROLLUP_TABLES = {
    "finding_rollups",
    "rule_fire_rates",
    "baseline_trends",
    "guard_calibration",
    "pattern_catalog",
    "recommendation_outcomes",
    "_aggregate_meta",
}

# Read-model VIEWS over events_fact (WO-DBA-REPOINT). Readers connection-swap to these;
# they present the old SQLite read-model shapes with complete (canonical-derived) data.
_EXPECTED_PROJECTION_VIEWS = {
    "token_usage_records",
    "hook_executions",
    "validation_failures",
    "raw_sessions",
}


def _tables(db_path: Path) -> set:
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
        return {r[0] for r in rows}
    finally:
        conn.close()


class TestAnalyticsSchema:
    def test_analytics_table_created(self, tmp_path):
        db = tmp_path / "agg.db"
        conn = connect_analytics(db, read_only=False)
        ensure_analytics_schema(conn)
        conn.close()
        tables = _tables(db)
        for t in _EXPECTED_ANALYTICS_TABLES:
            assert t in tables, f"Missing DuckDB analytics table: {t}"

    def test_all_rollup_tables_present(self, tmp_path):
        db = tmp_path / "agg.db"
        conn = connect_analytics(db, read_only=False)
        ensure_analytics_schema(conn)
        conn.close()
        tables = _tables(db)
        for t in _EXPECTED_ROLLUP_TABLES:
            assert t in tables, f"Missing rollup table: {t}"

    def test_no_wrong_scope_business_tables(self, tmp_path):
        db = tmp_path / "agg.db"
        conn = connect_analytics(db, read_only=False)
        ensure_analytics_schema(conn)
        conn.close()
        tables = _tables(db)
        wrong_scope = {
            "duckdb_projects",
            "duckdb_milestones",
            "duckdb_work_orders",
            "duckdb_tasks",
            "duckdb_design_briefs",
            "duckdb_projection_cursor",
        }
        present = wrong_scope & tables
        assert not present, f"Wrong-scope business tables in DuckDB: {present}"

    def test_schema_idempotent(self, tmp_path):
        db = tmp_path / "agg.db"
        conn = connect_analytics(db, read_only=False)
        ensure_analytics_schema(conn)
        ensure_analytics_schema(conn)
        conn.close()
        tables = _tables(db)
        expected = _EXPECTED_ANALYTICS_TABLES | _EXPECTED_ROLLUP_TABLES | _EXPECTED_PROJECTION_VIEWS
        assert tables == expected, f"schema drift: {tables ^ expected}"
