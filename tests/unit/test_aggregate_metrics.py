"""Tests for ML metrics aggregation pipeline (DuckDB backend)."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import duckdb  # noqa: E402

from core.analytics.aggregate_metrics import ensure_aggregate_schema, run_aggregation  # noqa: E402


def _make_source_db(tmp_path: Path) -> Path:
    """Create a minimal source DB with security_events (finding spine) + scan_runs.

    guard_events is NOT created: it was dropped in migration 133 (all writers
    were test-only with no production callers). Tests must not recreate dead tables.

    findings_current_status was dropped in migration 140 (WO dff23cb0) — finding
    rollups are now derived from security_events (finding.recorded /
    finding.status_changed events) at read time via
    core.findings.current_status.FINDINGS_CURRENT_STATUS_SQL. Seed the spine
    directly instead of a materialized status table: f1/f2/f4 stay 'open'
    (no status event), f3 gets a finding.status_changed event to 'fixed'.
    """
    db = tmp_path / "studio.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE scan_runs (
            scan_id TEXT PRIMARY KEY, project_id TEXT, skill_id TEXT,
            is_baseline INTEGER DEFAULT 0, findings_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'completed', started_at TEXT
        );
        CREATE TABLE security_events (
            event_id TEXT PRIMARY KEY, parent_event_id TEXT, event_kind TEXT NOT NULL,
            correlation_id TEXT, project_id TEXT, work_order_id TEXT,
            scanner_type TEXT, cwe_id TEXT, owasp_category TEXT, cve_id TEXT,
            file_path TEXT, line_number INTEGER, vuln_class TEXT, exploitability TEXT,
            severity TEXT, title TEXT, body TEXT, created_at TEXT NOT NULL
        );
        INSERT INTO security_events
            (event_id, parent_event_id, event_kind, project_id, scanner_type, vuln_class, severity, title, created_at)
        VALUES
            ('f1', NULL, 'finding.recorded', 'proj-a', 'security', 'sec-001', 'critical', 'finding f1', datetime('now')),
            ('f2', NULL, 'finding.recorded', 'proj-a', 'security', 'sec-001', 'high', 'finding f2', datetime('now')),
            ('f3', NULL, 'finding.recorded', 'proj-a', 'code-quality', 'cq-001', 'medium', 'finding f3', datetime('now')),
            ('f4', NULL, 'finding.recorded', 'proj-b', 'backend-api', 'api-004', 'critical', 'finding f4', datetime('now'));
        INSERT INTO security_events
            (event_id, parent_event_id, event_kind, project_id, body, created_at)
        VALUES
            ('f3-status', 'f3', 'finding.status_changed', 'proj-a', 'fixed', datetime('now'));
        INSERT INTO scan_runs VALUES
            ('s1', 'proj-a', 'security', 1, 2, 'completed', datetime('now')),
            ('s2', 'proj-a', 'security', 0, 1, 'completed', datetime('now'));
        INSERT INTO security_events
            (event_id, parent_event_id, event_kind, project_id, vuln_class, severity, created_at)
        VALUES
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

        # Verify finding_rollups count matches raw count, both derived from the
        # same security_events spine (findings_current_status dropped migration 140).
        from core.findings.current_status import FINDINGS_CURRENT_STATUS_SQL

        src = sqlite3.connect(str(source_db))
        src.row_factory = sqlite3.Row
        raw_count = src.execute(
            f"SELECT COUNT(*) as c FROM ({FINDINGS_CURRENT_STATUS_SQL}) WHERE project_id = 'proj-a'"
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
