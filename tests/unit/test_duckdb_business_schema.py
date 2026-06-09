"""Tests for DuckDB business-entity table schema (WO-TS3 task 1)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import duckdb  # noqa: E402
import pytest  # noqa: E402

from core.analytics.duckdb_store import connect_analytics, ensure_analytics_schema  # noqa: E402

_EXPECTED_BUSINESS_TABLES = {
    "duckdb_projects",
    "duckdb_milestones",
    "duckdb_work_orders",
    "duckdb_tasks",
    "duckdb_design_briefs",
    "duckdb_projection_cursor",
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


def _tables(db_path: Path) -> set:
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
        return {r[0] for r in rows}
    finally:
        conn.close()


class TestBusinessSchema:
    def test_all_business_tables_created(self, tmp_path):
        db = tmp_path / "agg.db"
        conn = connect_analytics(db, read_only=False)
        ensure_analytics_schema(conn)
        conn.close()
        tables = _tables(db)
        for t in _EXPECTED_BUSINESS_TABLES:
            assert t in tables, f"Missing DuckDB business table: {t}"

    def test_all_rollup_tables_still_present(self, tmp_path):
        db = tmp_path / "agg.db"
        conn = connect_analytics(db, read_only=False)
        ensure_analytics_schema(conn)
        conn.close()
        tables = _tables(db)
        for t in _EXPECTED_ROLLUP_TABLES:
            assert t in tables, f"Missing rollup table: {t}"

    def test_schema_idempotent(self, tmp_path):
        db = tmp_path / "agg.db"
        conn = connect_analytics(db, read_only=False)
        ensure_analytics_schema(conn)
        ensure_analytics_schema(conn)
        conn.close()
        tables = _tables(db)
        assert len(tables) == len(_EXPECTED_BUSINESS_TABLES | _EXPECTED_ROLLUP_TABLES)

    def test_projection_cursor_columns(self, tmp_path):
        db = tmp_path / "agg.db"
        conn = connect_analytics(db, read_only=False)
        ensure_analytics_schema(conn)
        conn.execute(
            "INSERT INTO duckdb_projection_cursor VALUES (?, ?, ?, ?)",
            ("test_proj", "evt-001", "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
        )
        row = conn.execute(
            "SELECT projection_name, last_event_id FROM duckdb_projection_cursor"
        ).fetchone()
        conn.close()
        assert row[0] == "test_proj"
        assert row[1] == "evt-001"
