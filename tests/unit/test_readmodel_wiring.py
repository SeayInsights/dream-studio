"""Tests for WO-READMODEL-WIRING: read-models repointed at real data sources.

Verifies:
  - skill_usage_sql prefers execution_events.skill.invoked over dead skill_invocations
  - /api/v1/hooks/executions returns real rows when hook_executions is populated
  - _process_run_drilldowns returns entries from execution_events when process_runs is empty
"""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime, timedelta
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


def _home_with_duckdb_hook_executions(tmp_path: Path, monkeypatch) -> Path:
    """Seed the DuckDB hook_executions source under an isolated DREAM_STUDIO_HOME.

    Migration 129 (WO-READMODELS-DUCKDB) dropped the SQLite hook_executions table;
    /hooks/executions now reads the DuckDB hook_executions VIEW over
    system.hook.execution.logged events in events_fact.

    monkeypatch.setenv, not a raw os.environ assignment: this used to leave
    DREAM_STUDIO_HOME pointed at this test's (torn-down) tmp_path for the rest of the
    pytest session. Harmless while runtime.lib.enforcement read Path.home() directly,
    but once it started honoring DREAM_STUDIO_HOME (this sweep), a subprocess spawned
    by a LATER test -- tests/unit/test_write_posture_reaches_enforcement.py, which
    inherits os.environ -- wrote its session state under the stale path while the
    parent process's already-imported `enforcement` module (which fixes SESSION_DIR at
    import time) kept reading the original one, so the write became invisible.
    """
    import json

    from core.analytics.duckdb_store import connect_analytics, ensure_analytics_schema
    from core.event_store.studio_db import _connect

    home = tmp_path / "ds-home"
    (home / "state").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(home))
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
    db_path = _home_with_duckdb_hook_executions(tmp_path, monkeypatch)
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
        # DREAM_STUDIO_HOME itself is restored by monkeypatch's own teardown now
        # (_home_with_duckdb_hook_executions sets it via monkeypatch.setenv).
        DatabaseRuntime.reset_instance()


def _seed_hook_execution(conn, *, event_id: str, hook_name: str) -> None:
    import json

    payload = {
        "hook_name": hook_name,
        "hook_type": "pre_push",
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
        [event_id, "2026-06-14T00:00:00Z", json.dumps(payload)],
    )


def test_hooks_executions_route_reads_its_own_authoritys_store_not_ambient(
    tmp_path: Path, monkeypatch
) -> None:
    """GET /api/v1/hooks/executions must read the analytics store colocated
    with the request's own SQLite authority, not the ambient one. Four
    hooks.py routes (list_hook_executions, get_hook_execution_details,
    get_hook_performance, list_validation_failures) shared the same
    connect_analytics(read_only=True)-with-no-path leak; this exercises the
    one shared mechanism (analytics_db_path_for_connection(sql_conn)) all
    four now go through.

    Seeds the ambient store (a genuinely separate DREAM_STUDIO_HOME) with a
    hook this authority never ran, binds the TestClient to a SEPARATE
    explicit db_path (via DB_PATH_ENV) whose own aggregate_metrics.db
    sibling holds a DIFFERENT hook, and shows only that authority's hook
    comes back."""
    from core.analytics.duckdb_store import connect_analytics, ensure_analytics_schema

    # Ambient store, under a genuinely separate DREAM_STUDIO_HOME.
    ambient_home = tmp_path / "ambient-home"
    (ambient_home / "state").mkdir(parents=True)
    os.environ["DREAM_STUDIO_HOME"] = str(ambient_home)
    ambient_conn = connect_analytics(
        ambient_home / "state" / "aggregate_metrics.db", read_only=False
    )
    try:
        ensure_analytics_schema(ambient_conn)
        _seed_hook_execution(ambient_conn, event_id="ambient-hook", hook_name="ambient-only-hook")
    finally:
        ambient_conn.close()

    # This authority's OWN db_path + its own sibling aggregate_metrics.db.
    own_dir = tmp_path / "own-authority"
    own_dir.mkdir()
    db_path = own_dir / "studio.db"
    own_conn = connect_analytics(own_dir / "aggregate_metrics.db", read_only=False)
    try:
        ensure_analytics_schema(own_conn)
        _seed_hook_execution(own_conn, event_id="own-hook", hook_name="own-authority-hook")
    finally:
        own_conn.close()

    client = _client_for_db(db_path, monkeypatch)
    try:
        resp = client.get("/api/v1/hooks/executions")
        assert resp.status_code == 200
        data = resp.json()
        hook_names = {e["hook_name"] for e in data["executions"]}
        assert hook_names == {"own-authority-hook"}, hook_names
    finally:
        DatabaseRuntime.reset_instance()
        os.environ.pop("DREAM_STUDIO_HOME", None)


# ── T5: /api/v1/metrics/models reads its own authority's analytics store ───
#
# projections/api/routes/metrics.py::get_model_metrics calls token_usage_sql(conn)
# with conn scoped to DB_PATH_ENV's db_path — but until
# core.analytics.duckdb_store.analytics_db_path_for_connection(conn) was threaded
# through, the DuckDB branch resolved connect_analytics()'s ambient default (the
# aggregate_metrics.db sitting in DREAM_STUDIO_HOME) instead, regardless of which
# authority the request's own conn belonged to.


def test_model_metrics_route_reads_its_own_authoritys_store_not_ambient(
    tmp_path: Path, monkeypatch
) -> None:
    """Reproduces the leak directly: seed the ambient store (an isolated
    DREAM_STUDIO_HOME) with a token row for an unrelated model, bind the
    TestClient to a SEPARATE explicit db_path (via DB_PATH_ENV) whose own
    aggregate_metrics.db sibling holds a DIFFERENT model's row, and show only
    that authority's model comes back from GET /api/v1/metrics/models."""
    from core.analytics.duckdb_store import connect_analytics, ensure_analytics_schema

    recent = (datetime.now(UTC) - timedelta(days=1)).isoformat()

    # Ambient store, under an isolated DREAM_STUDIO_HOME: an unrelated model.
    ambient_home = tmp_path / "ambient-home"
    (ambient_home / "state").mkdir(parents=True)
    os.environ["DREAM_STUDIO_HOME"] = str(ambient_home)
    ambient_conn = connect_analytics(
        ambient_home / "state" / "aggregate_metrics.db", read_only=False
    )
    try:
        ensure_analytics_schema(ambient_conn)
        ambient_conn.execute(
            "INSERT INTO events_fact (event_id, event_type, event_timestamp, model_id,"
            " input_tokens, output_tokens, payload)"
            " VALUES ('ambient-tok', 'token.consumed', ?, 'claude-opus-4-8', 9000, 9000, '{}')",
            [recent],
        )
    finally:
        ambient_conn.close()

    # This authority's OWN db_path + its OWN sibling aggregate_metrics.db, at a
    # location unrelated to the ambient DREAM_STUDIO_HOME set above.
    own_dir = tmp_path / "own-authority"
    own_dir.mkdir()
    db_path = own_dir / "studio.db"
    own_conn = connect_analytics(own_dir / "aggregate_metrics.db", read_only=False)
    try:
        ensure_analytics_schema(own_conn)
        own_conn.execute(
            "INSERT INTO events_fact (event_id, event_type, event_timestamp, model_id,"
            " input_tokens, output_tokens, payload)"
            " VALUES ('own-tok', 'token.consumed', ?, 'claude-haiku-4-5', 1000, 500, '{}')",
            [recent],
        )
    finally:
        own_conn.close()

    client = _client_for_db(db_path, monkeypatch)
    try:
        resp = client.get("/api/v1/metrics/models")
        assert resp.status_code == 200
        data = resp.json()
        assert "claude-haiku-4-5" in data["by_model"], data["by_model"]
        assert "claude-opus-4-8" not in data["by_model"], data["by_model"]
    finally:
        DatabaseRuntime.reset_instance()
        os.environ.pop("DREAM_STUDIO_HOME", None)


# ── T6: dashboard routes read their own authority's analytics store, not
# ambient (round-2 review finding: 9df1eba/06a4d87/8f166e7 threaded
# analytics_db_path_for_connection through every token_usage_sql()/
# fetch_token_usage_records() call in analytics.py, intelligence_domains.py,
# intelligence_overview.py and metrics.py -- but those same route modules also
# call connect_analytics() DIRECTLY (for raw_sessions and hook_executions),
# bypassing token_usage_sql entirely. Those sibling call sites still resolved
# connect_analytics()'s ambient default regardless of which authority the
# request's own conn belonged to. Two representative shapes below: analytics.py
# ::get_performance (already held a conn nearby, via the module's _connect()
# helper) and intelligence_domains.py::get_system_controls_intelligence (held
# no SQLite conn at all before this fix).


def test_analytics_performance_route_reads_its_own_authoritys_store_not_ambient(
    tmp_path: Path, monkeypatch
) -> None:
    """GET /api/v1/analytics/performance reads raw_sessions from the analytics
    store colocated with the request's own authority, not the ambient one.

    Seeds the ambient store (an isolated DREAM_STUDIO_HOME) with sessions whose
    outcome is 'failed', binds the TestClient to a SEPARATE explicit db_path
    (via DB_PATH_ENV) whose own aggregate_metrics.db sibling holds sessions
    whose outcome is 'completed', and shows only that authority's sessions
    come back."""
    import json

    from core.analytics.duckdb_store import connect_analytics, ensure_analytics_schema

    recent = (datetime.now(UTC) - timedelta(days=1)).isoformat()

    # Ambient store, under an isolated DREAM_STUDIO_HOME: 4 failed sessions.
    # Distinct session_id per row (in payload) -- raw_sessions dedupes by
    # session_id via ROW_NUMBER() PARTITION BY, so same-session_id (NULL, if
    # omitted) rows collapse to one.
    ambient_home = tmp_path / "ambient-home"
    (ambient_home / "state").mkdir(parents=True)
    os.environ["DREAM_STUDIO_HOME"] = str(ambient_home)
    ambient_conn = connect_analytics(
        ambient_home / "state" / "aggregate_metrics.db", read_only=False
    )
    try:
        ensure_analytics_schema(ambient_conn)
        for i in range(4):
            sid = f"ambient-sess-{i}"
            ambient_conn.execute(
                "INSERT INTO events_fact (event_id, event_type, event_timestamp, outcome,"
                " payload) VALUES (?, 'system.session.recorded', ?, 'failed', ?)",
                [sid, recent, json.dumps({"session_id": sid})],
            )
    finally:
        ambient_conn.close()

    # This authority's OWN db_path + its OWN sibling aggregate_metrics.db, at a
    # location unrelated to the ambient DREAM_STUDIO_HOME set above: 3 completed
    # sessions.
    own_dir = tmp_path / "own-authority"
    own_dir.mkdir()
    db_path = own_dir / "studio.db"
    own_conn = connect_analytics(own_dir / "aggregate_metrics.db", read_only=False)
    try:
        ensure_analytics_schema(own_conn)
        for i in range(3):
            sid = f"own-sess-{i}"
            own_conn.execute(
                "INSERT INTO events_fact (event_id, event_type, event_timestamp, outcome,"
                " payload) VALUES (?, 'system.session.recorded', ?, 'completed', ?)",
                [sid, recent, json.dumps({"session_id": sid})],
            )
    finally:
        own_conn.close()

    client = _client_for_db(db_path, monkeypatch)
    try:
        resp = client.get("/api/v1/analytics/performance")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_flow"]["completed"] == 3, data["session_flow"]
        assert data["session_flow"]["failed"] == 0, data["session_flow"]
        assert data["session_flow"]["started"] == 3, data["session_flow"]
    finally:
        DatabaseRuntime.reset_instance()
        os.environ.pop("DREAM_STUDIO_HOME", None)


def test_work_rhythm_route_reads_its_own_authoritys_store_not_ambient(
    tmp_path: Path, monkeypatch
) -> None:
    """GET /api/v1/insights/rhythm reads raw_sessions from the analytics store
    colocated with the request's own authority, not the ambient one.
    get_work_rhythm held no SQLite conn at all before this fix -- it called
    connect_analytics(read_only=True) with nothing to scope it.

    Seeds the ambient store (a genuinely separate DREAM_STUDIO_HOME) with 5
    sessions, binds the TestClient to a SEPARATE explicit db_path (via
    DB_PATH_ENV) whose own aggregate_metrics.db sibling holds 1 session, and
    shows the busiest-day count reflects only that authority's 1 session."""
    import json

    from core.analytics.duckdb_store import connect_analytics, ensure_analytics_schema

    recent = (datetime.now(UTC) - timedelta(days=1)).isoformat()

    def _session_row(sid: str) -> tuple:
        return (
            sid,
            "system.session.recorded",
            recent,
            json.dumps({"session_id": sid}),
        )

    # Ambient store, under a genuinely separate DREAM_STUDIO_HOME: 5 sessions.
    ambient_home = tmp_path / "ambient-home"
    (ambient_home / "state").mkdir(parents=True)
    os.environ["DREAM_STUDIO_HOME"] = str(ambient_home)
    ambient_conn = connect_analytics(
        ambient_home / "state" / "aggregate_metrics.db", read_only=False
    )
    try:
        ensure_analytics_schema(ambient_conn)
        for i in range(5):
            ambient_conn.execute(
                "INSERT INTO events_fact (event_id, event_type, event_timestamp, payload)"
                " VALUES (?, ?, ?, ?)",
                _session_row(f"ambient-sess-{i}"),
            )
    finally:
        ambient_conn.close()

    # This authority's OWN db_path + its own sibling aggregate_metrics.db: 1 session.
    own_dir = tmp_path / "own-authority"
    own_dir.mkdir()
    db_path = own_dir / "studio.db"
    own_conn = connect_analytics(own_dir / "aggregate_metrics.db", read_only=False)
    try:
        ensure_analytics_schema(own_conn)
        own_conn.execute(
            "INSERT INTO events_fact (event_id, event_type, event_timestamp, payload)"
            " VALUES (?, ?, ?, ?)",
            _session_row("own-sess-0"),
        )
    finally:
        own_conn.close()

    client = _client_for_db(db_path, monkeypatch)
    try:
        resp = client.get("/api/v1/insights/rhythm")
        assert resp.status_code == 200
        data = resp.json()
        assert data["busiest_day_count"] == 1, data
    finally:
        DatabaseRuntime.reset_instance()
        os.environ.pop("DREAM_STUDIO_HOME", None)


def test_system_controls_route_reads_its_own_authoritys_store_not_ambient(
    tmp_path: Path, monkeypatch
) -> None:
    """GET /api/v1/intelligence/system-controls reads hook_executions from the
    analytics store colocated with the request's own authority, not the
    ambient one.

    get_system_controls_intelligence held no SQLite conn at all before this
    fix -- it called connect_analytics(read_only=True) with nothing to scope
    it. Seeds the ambient store with a failing hook, the request's own store
    (a separate db_path via DB_PATH_ENV) with a DIFFERENT, healthy hook, and
    shows the response reflects only the request's own hook."""
    import json

    from core.analytics.duckdb_store import connect_analytics, ensure_analytics_schema

    recent = (datetime.now(UTC) - timedelta(days=1)).isoformat()

    def _hook_row(hook_name: str, status: str) -> dict:
        return {
            "hook_name": hook_name,
            "hook_type": "pre_push",
            "started_at": recent,
            "completed_at": recent,
            "duration_ms": 50,
            "exit_code": 0 if status == "success" else 1,
            "status": status,
        }

    # Ambient store: a hook that fails consistently (attention_needed material).
    ambient_home = tmp_path / "ambient-home"
    (ambient_home / "state").mkdir(parents=True)
    os.environ["DREAM_STUDIO_HOME"] = str(ambient_home)
    ambient_conn = connect_analytics(
        ambient_home / "state" / "aggregate_metrics.db", read_only=False
    )
    try:
        ensure_analytics_schema(ambient_conn)
        for i in range(6):
            payload = _hook_row("ambient-flaky-hook", "failed")
            ambient_conn.execute(
                "INSERT INTO events_fact (event_id, source, event_type, event_timestamp,"
                " duration_ms, exit_code, status, payload) VALUES"
                " (?, 'ai', 'system.hook.execution.logged', ?, 50, 1, 'failed', ?)",
                [f"ambient-hook-{i}", recent, json.dumps(payload)],
            )
    finally:
        ambient_conn.close()

    # Own authority: a DIFFERENT hook, all successful.
    own_dir = tmp_path / "own-authority"
    own_dir.mkdir()
    db_path = own_dir / "studio.db"
    own_conn = connect_analytics(own_dir / "aggregate_metrics.db", read_only=False)
    try:
        ensure_analytics_schema(own_conn)
        for i in range(6):
            payload = _hook_row("own-healthy-hook", "success")
            own_conn.execute(
                "INSERT INTO events_fact (event_id, source, event_type, event_timestamp,"
                " duration_ms, exit_code, status, payload) VALUES"
                " (?, 'ai', 'system.hook.execution.logged', ?, 50, 0, 'success', ?)",
                [f"own-hook-{i}", recent, json.dumps(payload)],
            )
    finally:
        own_conn.close()

    client = _client_for_db(db_path, monkeypatch)
    try:
        resp = client.get("/api/v1/intelligence/system-controls")
        assert resp.status_code == 200
        data = resp.json()
        titles = [issue["title"] for issue in data["attention_needed"]]
        assert not any("ambient-flaky-hook" in t for t in titles), titles
        assert data["health"]["hook_success_rate"]["display"] == "6 executions", data["health"]
        assert data["health"]["hook_success_rate"]["value"] == "100.0%", data["health"]
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


def test_attribution_breakouts_route_reads_its_own_authoritys_store_not_ambient(
    tmp_path: Path, monkeypatch
) -> None:
    """GET /api/v1/insights/attribution-breakouts reads token_usage_records
    from the analytics store colocated with the request's own authority, not
    the ambient one. get_attribution_breakouts held a conn only for the
    SQLite project-name enrichment step, opened AFTER duck_conn was already
    connected with nothing to scope it.

    Seeds the ambient store (a genuinely separate DREAM_STUDIO_HOME) with 900
    tokens under one skill, binds the TestClient to a SEPARATE explicit
    db_path (via DB_PATH_ENV) whose own aggregate_metrics.db sibling holds
    150 tokens under a different skill, and shows total_tokens reflects only
    that authority's own 150."""
    from core.analytics.duckdb_store import connect_analytics, ensure_analytics_schema

    recent = (datetime.now(UTC) - timedelta(days=1)).isoformat()

    # Ambient store, under a genuinely separate DREAM_STUDIO_HOME.
    ambient_home = tmp_path / "ambient-home"
    (ambient_home / "state").mkdir(parents=True)
    os.environ["DREAM_STUDIO_HOME"] = str(ambient_home)
    ambient_conn = connect_analytics(
        ambient_home / "state" / "aggregate_metrics.db", read_only=False
    )
    try:
        ensure_analytics_schema(ambient_conn)
        ambient_conn.execute(
            "INSERT INTO events_fact (event_id, event_type, event_timestamp,"
            " input_tokens, output_tokens, skill_id, payload)"
            " VALUES ('ambient-tok', 'token.consumed', ?, 600, 300, 'ambient-skill', '{}')",
            [recent],
        )
    finally:
        ambient_conn.close()

    # This authority's OWN db_path + its own sibling aggregate_metrics.db.
    own_dir = tmp_path / "own-authority"
    own_dir.mkdir()
    db_path = own_dir / "studio.db"
    own_conn = connect_analytics(own_dir / "aggregate_metrics.db", read_only=False)
    try:
        ensure_analytics_schema(own_conn)
        own_conn.execute(
            "INSERT INTO events_fact (event_id, event_type, event_timestamp,"
            " input_tokens, output_tokens, skill_id, payload)"
            " VALUES ('own-tok', 'token.consumed', ?, 100, 50, 'own-skill', '{}')",
            [recent],
        )
    finally:
        own_conn.close()

    client = _client_for_db(db_path, monkeypatch)
    try:
        resp = client.get("/api/v1/insights/attribution-breakouts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_tokens"] == 150, data
        skill_ids = {row["skill_id"] for row in data["by_skill"]}
        assert skill_ids == {"own-skill"}, skill_ids
    finally:
        DatabaseRuntime.reset_instance()
        os.environ.pop("DREAM_STUDIO_HOME", None)
