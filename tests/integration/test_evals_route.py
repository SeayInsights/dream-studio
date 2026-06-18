"""Integration tests for WO-EVALS-RENDER: /api/v1/evals/health route.

Covers:
- HTTP 200 with correct payload shape when ds_eval_baselines + ds_eval_runs rows exist
- Honest empty-state (baselines=[], recent_runs=[]) when no data present
- route resolves correctly with FastAPI TestClient
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.config.database import DB_PATH_ENV, DatabaseRuntime
from core.config.sqlite_bootstrap import latest_migration_version
from projections.api.main import app


def _client_for_db(db_path: Path, monkeypatch) -> TestClient:
    DatabaseRuntime.reset_instance()
    monkeypatch.setenv(DB_PATH_ENV, str(db_path))
    return TestClient(app)


def _schema_version_row(conn, version: int) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _schema_version"
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO _schema_version(version, applied_at) VALUES(?, datetime('now'))",
        (version,),
    )


def _db_with_baselines_and_runs(tmp_path: Path) -> Path:
    """Seed a DB with ds_eval_baselines + ds_eval_runs rows."""
    db_path = tmp_path / "evals-populated.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        _schema_version_row(conn, latest_migration_version())

        conn.execute("""
            CREATE TABLE ds_eval_baselines (
                eval_id TEXT NOT NULL,
                version TEXT NOT NULL DEFAULT '1.0.0',
                baseline_score REAL NOT NULL,
                last_run_score REAL,
                last_run_at TEXT,
                regression_flag INTEGER NOT NULL DEFAULT 0,
                regression_threshold REAL NOT NULL DEFAULT 0.10,
                run_count INTEGER NOT NULL DEFAULT 0,
                last_updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                label TEXT DEFAULT NULL,
                PRIMARY KEY (eval_id, version)
            )
        """)
        conn.execute("""
            INSERT INTO ds_eval_baselines
                (eval_id, version, baseline_score, regression_flag, last_run_at)
            VALUES
                ('eval-core-plan', '1.0.0', 0.92, 0, '2026-06-17T10:00:00'),
                ('eval-core-build', '1.0.0', 0.75, 1, '2026-06-17T09:00:00')
        """)

        conn.execute("""
            CREATE TABLE ds_eval_runs (
                run_id TEXT PRIMARY KEY,
                eval_id TEXT NOT NULL,
                eval_version TEXT NOT NULL DEFAULT '1.0.0',
                started_at TEXT NOT NULL,
                completed_at TEXT,
                model_tested TEXT NOT NULL DEFAULT 'claude-sonnet-4-6',
                skill_versions_snapshot TEXT,
                event_score REAL,
                behavior_score REAL,
                total_score REAL,
                passed INTEGER NOT NULL DEFAULT 0,
                failure_reasons TEXT,
                token_cost_usd REAL,
                baseline_run_id TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                run_mode TEXT NOT NULL DEFAULT 'fixture'
            )
        """)
        conn.execute("""
            INSERT INTO ds_eval_runs
                (run_id, eval_id, total_score, passed, started_at, model_tested)
            VALUES
                ('run-001', 'eval-core-plan', 0.92, 1, '2026-06-17T10:00:00', 'claude-sonnet-4-6'),
                ('run-002', 'eval-core-build', 0.70, 0, '2026-06-17T09:00:00', 'claude-sonnet-4-6')
        """)

        conn.commit()
    finally:
        conn.close()
    return db_path


def _db_empty(tmp_path: Path) -> Path:
    """Seed a DB with the eval tables but no rows."""
    db_path = tmp_path / "evals-empty.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        _schema_version_row(conn, latest_migration_version())

        conn.execute("""
            CREATE TABLE ds_eval_baselines (
                eval_id TEXT NOT NULL,
                version TEXT NOT NULL DEFAULT '1.0.0',
                baseline_score REAL NOT NULL,
                last_run_score REAL,
                last_run_at TEXT,
                regression_flag INTEGER NOT NULL DEFAULT 0,
                regression_threshold REAL NOT NULL DEFAULT 0.10,
                run_count INTEGER NOT NULL DEFAULT 0,
                last_updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                label TEXT DEFAULT NULL,
                PRIMARY KEY (eval_id, version)
            )
        """)
        conn.execute("""
            CREATE TABLE ds_eval_runs (
                run_id TEXT PRIMARY KEY,
                eval_id TEXT NOT NULL,
                eval_version TEXT NOT NULL DEFAULT '1.0.0',
                started_at TEXT NOT NULL,
                completed_at TEXT,
                model_tested TEXT NOT NULL DEFAULT 'claude-sonnet-4-6',
                skill_versions_snapshot TEXT,
                event_score REAL,
                behavior_score REAL,
                total_score REAL,
                passed INTEGER NOT NULL DEFAULT 0,
                failure_reasons TEXT,
                token_cost_usd REAL,
                baseline_run_id TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                run_mode TEXT NOT NULL DEFAULT 'fixture'
            )
        """)
        conn.commit()
    finally:
        conn.close()
    return db_path


# ---------------------------------------------------------------------------
# test_evals_health_returns_200_with_data
# ---------------------------------------------------------------------------


def test_evals_health_returns_200_with_data(tmp_path: Path, monkeypatch) -> None:
    """Seed DB with baselines+runs, call /api/v1/evals/health, assert 200 + correct payload."""
    db_path = _db_with_baselines_and_runs(tmp_path)
    client = _client_for_db(db_path, monkeypatch)
    try:
        resp = client.get("/api/v1/evals/health")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        data = resp.json()

        # Top-level summary fields
        assert data["total_evals"] == 2
        assert data["passing"] == 1
        assert data["failing"] == 1
        assert data["pass_rate"] == 50.0

        # Baselines list
        baselines = data["baselines"]
        assert len(baselines) == 2

        passing_baseline = next(b for b in baselines if b["eval_id"] == "eval-core-plan")
        assert passing_baseline["version"] == "1.0.0"
        assert passing_baseline["score"] == pytest.approx(0.92)
        assert passing_baseline["passed"] is True
        assert passing_baseline["last_run_at"] is not None

        failing_baseline = next(b for b in baselines if b["eval_id"] == "eval-core-build")
        assert failing_baseline["passed"] is False

        # Recent runs list
        runs = data["recent_runs"]
        assert len(runs) == 2

        passing_run = next(r for r in runs if r["run_id"] == "run-001")
        assert passing_run["eval_id"] == "eval-core-plan"
        assert passing_run["passed"] is True
        assert passing_run["total_score"] == pytest.approx(0.92)
        assert passing_run["model_tested"] == "claude-sonnet-4-6"
    finally:
        DatabaseRuntime.reset_instance()


# ---------------------------------------------------------------------------
# test_end_to_end
# ---------------------------------------------------------------------------


def test_end_to_end(tmp_path: Path, monkeypatch) -> None:
    """Route returns 200 + non-empty when data present; honest empty when not."""
    # --- with data ---
    populated_dir = tmp_path / "populated"
    populated_dir.mkdir(parents=True, exist_ok=True)
    populated_db = _db_with_baselines_and_runs(populated_dir)

    client_full = _client_for_db(populated_db, monkeypatch)
    try:
        resp = client_full.get("/api/v1/evals/health")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["total_evals"] > 0, "Expected non-zero total_evals when data present"
        assert len(payload["baselines"]) > 0, "Expected non-empty baselines list when data present"
        assert len(payload["recent_runs"]) > 0, "Expected non-empty recent_runs when data present"
    finally:
        DatabaseRuntime.reset_instance()

    # --- empty tables ---
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir(parents=True, exist_ok=True)
    empty_db = _db_empty(empty_dir)

    client_empty = _client_for_db(empty_db, monkeypatch)
    try:
        resp2 = client_empty.get("/api/v1/evals/health")
        assert resp2.status_code == 200
        payload2 = resp2.json()
        assert payload2["total_evals"] == 0, "Expected total_evals=0 with empty tables"
        assert payload2["baselines"] == [], "Expected empty baselines list with no rows"
        assert payload2["recent_runs"] == [], "Expected empty recent_runs list with no rows"
        assert payload2["pass_rate"] is None, "Expected pass_rate=None when no baselines"
    finally:
        DatabaseRuntime.reset_instance()
