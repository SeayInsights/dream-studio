"""Tests for ML metrics aggregation pipeline (DuckDB backend)."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import duckdb  # noqa: E402
import pytest  # noqa: E402

from core.analytics.aggregate_metrics import ensure_aggregate_schema, run_aggregation  # noqa: E402


def _make_source_db(tmp_path: Path) -> Path:
    """Create a minimal source DB with findings + scan_runs.

    guard_events is NOT created: it was dropped in migration 133 (all writers
    were test-only with no production callers). Tests must not recreate dead tables.
    """
    db = tmp_path / "studio.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE findings_current_status (
            finding_id TEXT PRIMARY KEY, project_id TEXT,
            introduced_by_skill_id TEXT,
            rule_id TEXT, severity TEXT, current_status TEXT DEFAULT 'open',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE scan_runs (
            scan_id TEXT PRIMARY KEY, project_id TEXT, skill_id TEXT,
            is_baseline INTEGER DEFAULT 0, findings_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'completed', started_at TEXT
        );
        CREATE TABLE security_events (
            event_id TEXT PRIMARY KEY, parent_event_id TEXT, event_kind TEXT NOT NULL,
            project_id TEXT, vuln_class TEXT, severity TEXT, created_at TEXT NOT NULL
        );
        INSERT INTO findings_current_status VALUES
            ('f1', 'proj-a', 'security', 'sec-001', 'critical', 'open', datetime('now')),
            ('f2', 'proj-a', 'security', 'sec-001', 'high', 'open', datetime('now')),
            ('f3', 'proj-a', 'code-quality', 'cq-001', 'medium', 'fixed', datetime('now')),
            ('f4', 'proj-b', 'backend-api', 'api-004', 'critical', 'open', datetime('now'));
        INSERT INTO scan_runs VALUES
            ('s1', 'proj-a', 'security', 1, 2, 'completed', datetime('now')),
            ('s2', 'proj-a', 'security', 0, 1, 'completed', datetime('now'));
        INSERT INTO security_events VALUES
            ('e1', NULL, 'finding.recorded', 'proj-a', 'sql-injection', 'high', datetime('now')),
            ('e2', NULL, 'finding.recorded', 'proj-a', 'sql-injection', 'critical', datetime('now'));
    """)
    conn.commit()
    conn.close()
    return db


def _agg_tables(agg_db: Path) -> set:
    """Return set of table names in the DuckDB analytics store."""
    conn = duckdb.connect(str(agg_db), read_only=True)
    try:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
        return {r[0] for r in rows}
    finally:
        conn.close()


class TestAggregateSchema:
    def test_schema_creates_all_tables(self, tmp_path):
        agg_db = tmp_path / "aggregate_metrics.db"
        ensure_aggregate_schema(agg_db)
        tables = _agg_tables(agg_db)
        assert "finding_rollups" in tables
        assert "rule_fire_rates" in tables
        assert "baseline_trends" in tables
        assert "guard_calibration" in tables
        assert "pattern_catalog" in tables
        assert "recommendation_outcomes" in tables
        assert "_aggregate_meta" in tables

    def test_schema_idempotent(self, tmp_path):
        agg_db = tmp_path / "aggregate_metrics.db"
        ensure_aggregate_schema(agg_db)
        ensure_aggregate_schema(agg_db)  # Second call must not error


class TestAggregationPipeline:
    def test_finding_rollups_match_source(self, tmp_path, monkeypatch):
        source_db = _make_source_db(tmp_path)
        agg_db = tmp_path / "aggregate_metrics.db"

        monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(source_db))

        result = run_aggregation(agg_db)
        assert result["status"] == "ok"
        assert isinstance(result["tables_written"].get("finding_rollups"), int)
        assert result["tables_written"]["finding_rollups"] > 0

        # Verify finding_rollups count matches raw count
        src = sqlite3.connect(str(source_db))
        src.row_factory = sqlite3.Row
        raw_count = src.execute(
            "SELECT COUNT(*) as c FROM findings_current_status WHERE project_id = 'proj-a'"
        ).fetchone()["c"]
        src.close()

        agg = duckdb.connect(str(agg_db), read_only=True)
        row = agg.execute(
            "SELECT SUM(finding_count) AS c FROM finding_rollups WHERE project_id = 'proj-a'"
        ).fetchone()
        agg.close()
        agg_count = row[0] if row else 0

        assert agg_count == raw_count, f"finding_rollups {agg_count} != raw {raw_count}"

    def test_idempotency(self, tmp_path, monkeypatch):
        source_db = _make_source_db(tmp_path)
        agg_db = tmp_path / "aggregate_metrics.db"
        monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(source_db))

        run_aggregation(agg_db)
        agg = duckdb.connect(str(agg_db), read_only=True)
        count1 = agg.execute("SELECT COUNT(*) FROM finding_rollups").fetchone()[0]
        agg.close()

        run_aggregation(agg_db)
        agg = duckdb.connect(str(agg_db), read_only=True)
        count2 = agg.execute("SELECT COUNT(*) FROM finding_rollups").fetchone()[0]
        agg.close()

        assert count1 == count2, f"Idempotency failed: {count1} vs {count2}"

    def test_guard_calibration_is_empty(self, tmp_path, monkeypatch):
        """guard_events was dropped in migration 133; guard_calibration stays empty."""
        source_db = _make_source_db(tmp_path)
        agg_db = tmp_path / "aggregate_metrics.db"
        monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(source_db))

        result = run_aggregation(agg_db)
        assert result["tables_written"]["guard_calibration"] == 0

        agg = duckdb.connect(str(agg_db), read_only=True)
        count = agg.execute("SELECT COUNT(*) FROM guard_calibration").fetchone()[0]
        agg.close()
        assert count == 0
