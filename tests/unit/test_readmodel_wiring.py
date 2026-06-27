"""Tests for WO-READMODEL-WIRING: read-models repointed at real data sources.

Verifies:
  - skill_usage_sql prefers execution_events.skill.invoked over dead skill_invocations
  - /api/v1/hooks/executions returns real rows when hook_executions is populated
  - _process_run_drilldowns returns entries from execution_events when process_runs is empty
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from core.config.database import DB_PATH_ENV, DatabaseRuntime
from projections.api.main import app
from projections.core.collectors.authority_sources import skill_usage_sql

_SCHEMA_VER_DDL = (
    "CREATE TABLE _schema_version(" "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
)


def _latest_version() -> int:
    from core.config.sqlite_bootstrap import latest_migration_version

    return latest_migration_version()


def _db_with_execution_events(tmp_path: Path) -> Path:
    db_path = tmp_path / "exec-events.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(_SCHEMA_VER_DDL)
        conn.execute(
            "INSERT INTO _schema_version(version, applied_at) VALUES(?, datetime('now'))",
            (_latest_version(),),
        )
        conn.execute("""
            CREATE TABLE execution_events(
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                event_name TEXT,
                project_id TEXT,
                milestone_id TEXT,
                task_id TEXT,
                process_run_id TEXT,
                parent_event_id TEXT,
                actor_type TEXT,
                actor_id TEXT,
                agent_id TEXT,
                skill_id TEXT,
                workflow_id TEXT,
                hook_id TEXT,
                tool_id TEXT,
                model_id TEXT,
                adapter_id TEXT,
                source_refs_json TEXT,
                evidence_refs_json TEXT,
                metadata_json TEXT,
                outcome_status TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                _built_from_event_id TEXT
            )
            """)
        # Three skill.invoked rows with distinct skill_ids
        for i, (skill, status, run_id) in enumerate(
            [
                ("project:resume", "completed", "run-abc"),
                ("core:plan", "completed", "run-abc"),
                ("core:think", "failed", "run-xyz"),
            ]
        ):
            conn.execute(
                "INSERT INTO execution_events(event_id, event_type, skill_id, outcome_status, process_run_id, created_at)"
                " VALUES(?, 'skill.invoked', ?, ?, ?, datetime('now'))",
                (f"evt-skill-{i}", skill, status, run_id),
            )
        conn.commit()
    finally:
        conn.close()
    return db_path


def _home_with_duckdb_hook_executions(tmp_path: Path) -> Path:
    """Seed the DuckDB hook_executions source under an isolated DREAM_STUDIO_HOME.

    Migration 129 (WO-READMODELS-DUCKDB) dropped the SQLite hook_executions table;
    /hooks/executions now reads the DuckDB hook_executions VIEW over
    system.hook.execution.logged events in events_fact.
    """
    import json

    from core.analytics.duckdb_store import connect_analytics, ensure_analytics_schema
    from core.event_store.studio_db import _connect

    home = tmp_path / "ds-home"
    (home / "state").mkdir(parents=True, exist_ok=True)
    os.environ["DREAM_STUDIO_HOME"] = str(home)
    # Authority SQLite (empty) so DB_PATH_ENV injection has a valid target.
    _connect(home / "state" / "studio.db").close()

    conn = connect_analytics(home / "state" / "aggregate_metrics.db", read_only=False)
    try:
        ensure_analytics_schema(conn)
        for i, (hook_name, hook_type) in enumerate(
            [("on-pre-push", "pre_push"), ("on-post-commit", "post_commit")]
        ):
            payload = {
                "hook_name": hook_name,
                "hook_type": hook_type,
                "started_at": "2026-06-14T00:00:00Z",
                "completed_at": "2026-06-14T00:00:01Z",
                "duration_ms": 100,
                "exit_code": 0,
                "status": "success",
            }
            conn.execute(
                "INSERT INTO events_fact (event_id, source, event_type, event_timestamp, "
                "duration_ms, exit_code, status, payload) VALUES "
                "(?, 'ai', 'system.hook.execution.logged', ?, 100, 0, 'success', ?)",
                [f"evt-hook-{i}", "2026-06-14T00:00:00Z", json.dumps(payload)],
            )
    finally:
        conn.close()
    return home / "state" / "studio.db"


def _db_with_process_run_events(tmp_path: Path) -> Path:
    db_path = tmp_path / "proc-runs.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(_SCHEMA_VER_DDL)
        conn.execute(
            "INSERT INTO _schema_version(version, applied_at) VALUES(?, datetime('now'))",
            (_latest_version(),),
        )
        conn.execute("""
            CREATE TABLE execution_events(
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                event_name TEXT,
                project_id TEXT,
                milestone_id TEXT,
                task_id TEXT,
                process_run_id TEXT,
                parent_event_id TEXT,
                actor_type TEXT,
                actor_id TEXT,
                agent_id TEXT,
                skill_id TEXT,
                workflow_id TEXT,
                hook_id TEXT,
                tool_id TEXT,
                model_id TEXT,
                adapter_id TEXT,
                source_refs_json TEXT,
                evidence_refs_json TEXT,
                metadata_json TEXT,
                outcome_status TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                _built_from_event_id TEXT
            )
            """)
        # process_runs table dropped migration 131; _process_run_drilldowns reads
        # process runs from execution_events.process_run_id, not a process_runs table.
        # Two distinct process runs tracked through execution_events.
        for i, run_id in enumerate(["proc-run-aaa", "proc-run-bbb"]):
            conn.execute(
                "INSERT INTO execution_events(event_id, event_type, process_run_id, created_at)"
                " VALUES(?, 'hook.tool_activity', ?, datetime('now', ?))",
                (f"evt-proc-{i}", run_id, f"-{i} seconds"),
            )
        conn.commit()
    finally:
        conn.close()
    return db_path


# ── T2: skill_usage_sql reads from execution_events ────────────────────────


def test_skill_usage_sql_returns_execution_events_rows(tmp_path: Path) -> None:
    db_path = _db_with_execution_events(tmp_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        sql = skill_usage_sql(conn)
        assert sql is not None, "skill_usage_sql must return SQL when execution_events has rows"
        rows = conn.execute(
            f"SELECT skill_name, success FROM ({sql}) s ORDER BY skill_name"
        ).fetchall()
        skill_names = {r["skill_name"] for r in rows}
        assert "project:resume" in skill_names
        assert "core:plan" in skill_names
        assert "core:think" in skill_names
        assert len(rows) == 3
    finally:
        conn.close()


def test_skill_usage_sql_returns_none_without_skill_data(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        sql = skill_usage_sql(conn)
        assert sql is None, "skill_usage_sql must return None when no skill data available"
    finally:
        conn.close()


def test_skill_usage_sql_no_reference_to_skill_invocations(tmp_path: Path) -> None:
    db_path = _db_with_execution_events(tmp_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        sql = skill_usage_sql(conn)
        assert sql is not None
        assert "skill_invocations" not in sql, "skill_invocations was dropped in migration 106"
    finally:
        conn.close()


# ── T3: hooks executions returns real rows ─────────────────────────────────


def _client_for_db(db_path: Path, monkeypatch) -> TestClient:
    DatabaseRuntime.reset_instance()
    monkeypatch.setenv(DB_PATH_ENV, str(db_path))
    return TestClient(app)


def test_hooks_executions_returns_real_rows_when_hook_executions_populated(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = _home_with_duckdb_hook_executions(tmp_path)
    client = _client_for_db(db_path, monkeypatch)
    try:
        resp = client.get("/api/v1/hooks/executions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 2
        hook_names = {e["hook_name"] for e in data["executions"]}
        assert "on-pre-push" in hook_names
        assert "on-post-commit" in hook_names
    finally:
        DatabaseRuntime.reset_instance()
        os.environ.pop("DREAM_STUDIO_HOME", None)


# ── T4: process_run_drilldowns reads from execution_events ─────────────────


def test_process_run_drilldowns_uses_execution_events_when_process_runs_empty(
    tmp_path: Path,
) -> None:
    from core.telemetry.read_models import _process_run_drilldowns

    db_path = _db_with_process_run_events(tmp_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # process_runs table dropped migration 131; _process_run_drilldowns must
        # return entries derived from execution_events.process_run_id.
        entries = _process_run_drilldowns(conn)
        assert len(entries) >= 2
        entity_ids = {e["entity_id"] for e in entries}
        assert "proc-run-aaa" in entity_ids
        assert "proc-run-bbb" in entity_ids
        for entry in entries:
            assert entry["entity_type"] == "process_run"
            assert "/api/telemetry/process-runs/" in entry["api_path"]
    finally:
        conn.close()
