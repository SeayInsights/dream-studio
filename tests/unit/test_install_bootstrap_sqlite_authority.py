from __future__ import annotations

import sqlite3
from pathlib import Path

from core.config import database
from core.config.database import DatabaseRuntime, initialize_database
from core.config.sqlite_bootstrap import (
    bootstrap_database,
    latest_migration_version,
    run_migrations,
)
from core.event_store.studio_db import _connect, _migrations_dir
from core.telemetry.read_models import global_telemetry_summary

REPO_ROOT = Path(__file__).resolve().parents[2]
LIVE_DB = Path.home() / ".dream-studio" / "state" / "studio.db"


def _schema_version(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        return int(conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0] or 0)
    finally:
        conn.close()


def test_canonical_db_path_uses_home_state_and_env_override(tmp_path, monkeypatch) -> None:
    DatabaseRuntime.reset_instance()
    monkeypatch.delenv(database.DB_PATH_ENV, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))

    assert (
        database._default_db_path() == tmp_path / "home" / ".dream-studio" / "state" / "studio.db"
    )

    override = tmp_path / "override" / "studio.db"
    monkeypatch.setenv(database.DB_PATH_ENV, str(override))
    assert database._default_db_path() == override
    DatabaseRuntime.reset_instance()


def test_fresh_temp_home_runtime_bootstrap_creates_db_and_applies_latest(
    tmp_path, monkeypatch
) -> None:
    DatabaseRuntime.reset_instance()
    monkeypatch.delenv(database.DB_PATH_ENV, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "fresh-home"))

    runtime = initialize_database()
    try:
        expected_db = tmp_path / "fresh-home" / ".dream-studio" / "state" / "studio.db"
        assert runtime.db_path == expected_db
        assert expected_db.is_file()
        assert _schema_version(expected_db) == latest_migration_version()
        assert expected_db != LIVE_DB
    finally:
        DatabaseRuntime.reset_instance()


def test_temp_version_36_db_upgrades_to_37_and_preserves_existing_rows(tmp_path) -> None:
    db_path = tmp_path / "upgrade" / "studio.db"
    assert latest_migration_version() >= 37

    bootstrap_database(db_path, target_version=36)
    conn = sqlite3.connect(str(db_path))
    try:
        current = conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0] or 0
        for version in range(current + 1, 37):
            conn.execute(
                "INSERT INTO _schema_version(version, applied_at) VALUES(?, ?)",
                (version, "2026-05-13T00:00:00+00:00"),
            )
        conn.execute(
            "INSERT INTO raw_sessions(session_id, started_at) VALUES(?, ?)",
            ("session-before-037", "2026-05-13T00:00:00+00:00"),
        )
        conn.commit()
        assert conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0] == 36
        run_migrations(conn)
        assert (
            conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0]
            == latest_migration_version()
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM raw_sessions WHERE session_id = ?", ("session-before-037",)
            ).fetchone()[0]
            == 1
        )
        assert (
            conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='execution_events'"
            ).fetchone()
            is not None
        )
    finally:
        conn.close()


def test_temp_version_38_db_repairs_dashboard_authority_objects(tmp_path) -> None:
    db_path = tmp_path / "dashboard-authority-repair" / "studio.db"
    db_path.parent.mkdir(parents=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "CREATE TABLE _schema_version(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO _schema_version(version, applied_at) VALUES(38, '2026-05-14T00:00:00Z')"
        )
        conn.execute("CREATE TABLE raw_sessions(session_id TEXT PRIMARY KEY, created_at TEXT)")
        conn.execute(
            "CREATE TABLE security_findings("
            "finding_id TEXT PRIMARY KEY, scan_id TEXT, category TEXT, severity TEXT, file_path TEXT, "
            "start_line INTEGER, description TEXT, status TEXT, created_at TEXT)"
        )
        # Full schemas required so migration 062's INSERT...SELECT * succeeds (column-count match).
        conn.execute(
            "CREATE TABLE execution_events("
            "event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL, event_name TEXT NOT NULL, "
            "project_id TEXT, milestone_id TEXT, task_id TEXT, process_run_id TEXT, "
            "parent_event_id TEXT, actor_type TEXT, actor_id TEXT, agent_id TEXT, "
            "skill_id TEXT, workflow_id TEXT, hook_id TEXT, tool_id TEXT, model_id TEXT, "
            "adapter_id TEXT, source_refs_json TEXT NOT NULL DEFAULT '[]', "
            "evidence_refs_json TEXT NOT NULL DEFAULT '[]', metadata_json TEXT NOT NULL DEFAULT '{}', "
            "outcome_status TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')))"
        )
        conn.execute(
            "CREATE TABLE hook_executions("
            "hook_exec_id INTEGER PRIMARY KEY AUTOINCREMENT, activity_id INTEGER, "
            "hook_name TEXT NOT NULL, hook_type TEXT, trigger_context TEXT, "
            "started_at DATETIME NOT NULL, completed_at DATETIME, duration_ms INTEGER, "
            "exit_code INTEGER, status TEXT, output TEXT, error_message TEXT, "
            "cpu_time_ms INTEGER, memory_mb REAL)"
        )
        conn.execute(
            "CREATE TABLE hook_findings("
            "finding_id INTEGER PRIMARY KEY AUTOINCREMENT, activity_id INTEGER, "
            "hook_exec_id INTEGER NOT NULL, finding_type TEXT NOT NULL, "
            "severity TEXT, message TEXT NOT NULL, context TEXT, recommendation TEXT, "
            "status TEXT, resolved_at DATETIME, resolution_notes TEXT, "
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.execute(
            "CREATE TABLE sec_sarif_findings("
            "sarif_finding_id INTEGER PRIMARY KEY AUTOINCREMENT, activity_id INTEGER, "
            "scan_tool TEXT NOT NULL, rule_id TEXT NOT NULL, rule_name TEXT, "
            "severity TEXT, file_path TEXT NOT NULL, line_number INTEGER, "
            "message TEXT NOT NULL, cwe_ids TEXT, cvss_score REAL, "
            "status TEXT DEFAULT 'open', mitigated_at TEXT, mitigation_task_id TEXT, "
            "created_at TEXT DEFAULT (datetime('now')))"
        )
        conn.execute(
            "CREATE TABLE sec_manual_reviews("
            "review_id INTEGER PRIMARY KEY AUTOINCREMENT, activity_id INTEGER, "
            "reviewer TEXT NOT NULL, review_type TEXT, findings TEXT, risk_level TEXT, "
            "recommendations TEXT, status TEXT DEFAULT 'draft', "
            "created_at TEXT DEFAULT (datetime('now')))"
        )
        conn.execute(
            "CREATE TABLE sec_cve_matches("
            "cve_match_id INTEGER PRIMARY KEY AUTOINCREMENT, activity_id INTEGER, "
            "cve_id TEXT NOT NULL, package_name TEXT NOT NULL, package_version TEXT NOT NULL, "
            "severity TEXT, cvss_score REAL, description TEXT, fixed_version TEXT, "
            "status TEXT DEFAULT 'vulnerable', patched_at TEXT, "
            "created_at TEXT DEFAULT (datetime('now')))"
        )
        conn.execute(
            "CREATE TABLE sec_hook_checks("
            "hook_check_id INTEGER PRIMARY KEY AUTOINCREMENT, activity_id INTEGER, "
            "hook_exec_id INTEGER NOT NULL, check_type TEXT, check_result TEXT, "
            "details TEXT, remediation TEXT, created_at TEXT DEFAULT (datetime('now')))"
        )
        conn.execute(
            "CREATE TABLE adapter_executions("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, activity_id INTEGER, "
            "adapter_type TEXT NOT NULL, normalized_at TEXT NOT NULL, "
            "execution_time_ms REAL, metadata TEXT)"
        )
        # Migration 071 does CREATE TABLE ... AS SELECT * FROM raw_workflow_runs/nodes.
        conn.execute(
            "CREATE TABLE raw_workflow_runs("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, run_key TEXT NOT NULL UNIQUE, "
            "workflow TEXT NOT NULL, yaml_path TEXT NOT NULL, status TEXT NOT NULL, "
            "started_at TEXT NOT NULL, finished_at TEXT, node_count INTEGER, "
            "nodes_done INTEGER, activity_id INTEGER, prd_id TEXT, task_id TEXT)"
        )
        conn.execute(
            "CREATE TABLE raw_workflow_nodes("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, run_key TEXT NOT NULL, "
            "node_id TEXT NOT NULL, status TEXT NOT NULL, started_at TEXT, "
            "finished_at TEXT, duration_s REAL, output TEXT, activity_id INTEGER)"
        )
        conn.execute("CREATE VIEW vw_security_summary AS SELECT 1 AS placeholder")
        conn.commit()

        run_migrations(conn)

        assert (
            conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0]
            == latest_migration_version()
        )
        raw_session_columns = {row[1] for row in conn.execute("PRAGMA table_info(raw_sessions)")}
        assert {"session_id", "project_id", "started_at", "ended_at", "outcome"}.issubset(
            raw_session_columns
        )
        assert (
            conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='alert_rules'"
            ).fetchone()
            is not None
        )
        assert (
            conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='alert_history'"
            ).fetchone()
            is not None
        )
        assert (
            conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='dashboard_authority_reconciliation_records'"
            ).fetchone()
            is not None
        )
        security_view_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(vw_security_summary)")
        }
        assert {"source_type", "finding_id", "tool", "created_at"}.issubset(security_view_columns)
    finally:
        conn.close()


def test_studio_db_connect_and_read_models_use_injected_temp_db(tmp_path) -> None:
    db_path = tmp_path / "injected" / "studio.db"
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO execution_events (
                event_id, event_type, event_name, project_id, outcome_status
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "event-temp-bootstrap-test",
                "bootstrap.validation",
                "Temp bootstrap validation",
                "dream-studio",
                "passed",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    summary = global_telemetry_summary(db_path)
    assert summary["entity_counts"]["events"] == 1
    assert summary["entity_counts"]["projects"] == 1
    assert summary["derived_view"] is True
    assert summary["primary_authority"] is False
    assert db_path != LIVE_DB


def test_migration_037_exists_in_repo_and_runtime_state_is_gitignored() -> None:
    assert (_migrations_dir() / "037_execution_telemetry_traceability_spine.sql").is_file()
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".dream-studio/*" in gitignore
    assert "*.db" in gitignore
    assert ".claude/" in gitignore
    assert ".codex/" not in gitignore


def test_no_operator_home_path_is_hardcoded_in_source_files() -> None:
    source_roots = [
        REPO_ROOT / "core",
        REPO_ROOT / "control",
        REPO_ROOT / "interfaces",
        REPO_ROOT / "runtime",
        REPO_ROOT / "hooks",
        REPO_ROOT / "scripts",
    ]
    forbidden = ("C:\\Users\\Example User", "C:/Users/Example User")
    checked: list[Path] = []
    offenders: list[str] = []
    for root in source_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() not in {".py", ".ps1", ".sh", ".sql"}:
                continue
            checked.append(path)
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(item in text for item in forbidden):
                offenders.append(str(path.relative_to(REPO_ROOT)))

    assert checked
    assert offenders == []


def test_tests_do_not_target_live_local_db_for_validation_writes() -> None:
    test_root = REPO_ROOT / "tests"
    live = str(LIVE_DB)
    offenders: list[str] = []
    for path in test_root.rglob("test_*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if live in text or "C:\\Users\\Example User\\.dream-studio\\state\\studio.db" in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))

    assert offenders == []
