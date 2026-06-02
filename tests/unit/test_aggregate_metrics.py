"""Tests for ML metrics aggregation pipeline."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402
from core.analytics.aggregate_metrics import ensure_aggregate_schema, run_aggregation  # noqa: E402


def _make_source_db(tmp_path: Path) -> Path:
    """Create a minimal source DB with findings + scan_runs."""
    db = tmp_path / "studio.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE findings (
            finding_id TEXT PRIMARY KEY, project_id TEXT,
            introduced_by_skill_id TEXT,
            rule_id TEXT, severity TEXT, status TEXT DEFAULT 'new',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE scan_runs (
            scan_id TEXT PRIMARY KEY, project_id TEXT, skill_id TEXT,
            is_baseline INTEGER DEFAULT 0, findings_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'completed', started_at TEXT
        );
        CREATE TABLE guard_events (
            event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL, rule_id TEXT,
            severity TEXT, source_type TEXT NOT NULL, project_id TEXT,
            action TEXT DEFAULT 'logged', confidence REAL,
            details TEXT DEFAULT '{}', created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        INSERT INTO findings VALUES ('f1', 'proj-a', 'security', 'sec-001', 'critical', 'new', datetime('now'));
        INSERT INTO findings VALUES ('f2', 'proj-a', 'security', 'sec-001', 'high', 'new', datetime('now'));
        INSERT INTO findings VALUES ('f3', 'proj-a', 'code-quality', 'cq-001', 'medium', 'fixed', datetime('now'));
        INSERT INTO findings VALUES ('f4', 'proj-b', 'backend-api', 'api-004', 'critical', 'new', datetime('now'));
        INSERT INTO scan_runs VALUES ('s1', 'proj-a', 'security', 1, 2, 'completed', datetime('now'));
        INSERT INTO scan_runs VALUES ('s2', 'proj-a', 'security', 0, 1, 'completed', datetime('now'));
        INSERT INTO guard_events VALUES ('g1', 'guard_finding_logged', 'guard-001', 'critical', 'repo_file', 'proj-a', 'logged', 0.9, '{}', datetime('now'));
        INSERT INTO guard_events VALUES ('g2', 'guard_finding_logged', 'guard-001', 'critical', 'repo_file', 'proj-a', 'dismissed', 0.9, '{}', datetime('now'));
    """)
    conn.commit()
    conn.close()
    return db


class TestAggregateSchema:
    def test_schema_creates_all_tables(self, tmp_path):
        agg_db = tmp_path / "aggregate_metrics.db"
        ensure_aggregate_schema(agg_db)
        conn = sqlite3.connect(str(agg_db))
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        conn.close()
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
        ensure_aggregate_schema(agg_db)  # Second call should not error


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
            "SELECT COUNT(*) as c FROM findings WHERE project_id = 'proj-a'"
        ).fetchone()["c"]
        src.close()

        agg = sqlite3.connect(str(agg_db))
        agg.row_factory = sqlite3.Row
        agg_count = agg.execute(
            "SELECT SUM(finding_count) as c FROM finding_rollups WHERE project_id = 'proj-a'"
        ).fetchone()["c"]
        agg.close()

        assert agg_count == raw_count, f"finding_rollups {agg_count} != raw {raw_count}"

    def test_idempotency(self, tmp_path, monkeypatch):
        source_db = _make_source_db(tmp_path)
        agg_db = tmp_path / "aggregate_metrics.db"
        monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(source_db))

        run_aggregation(agg_db)
        conn = sqlite3.connect(str(agg_db))
        count1 = conn.execute("SELECT COUNT(*) FROM finding_rollups").fetchone()[0]
        conn.close()

        run_aggregation(agg_db)
        conn = sqlite3.connect(str(agg_db))
        count2 = conn.execute("SELECT COUNT(*) FROM finding_rollups").fetchone()[0]
        conn.close()

        assert count1 == count2, f"Idempotency failed: {count1} vs {count2}"

    def test_guard_calibration_fp_rate(self, tmp_path, monkeypatch):
        source_db = _make_source_db(tmp_path)
        agg_db = tmp_path / "aggregate_metrics.db"
        monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(source_db))

        run_aggregation(agg_db)
        conn = sqlite3.connect(str(agg_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM guard_calibration WHERE rule_id = 'guard-001'").fetchone()
        conn.close()

        assert row is not None
        assert row["total_fires"] == 2
        assert row["dismiss_count"] == 1
        assert abs(row["fp_rate"] - 0.5) < 0.01
