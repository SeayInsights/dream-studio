from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from core.config.database import DB_PATH_ENV, DatabaseRuntime
from core.config.sqlite_bootstrap import latest_migration_version
from projections.api.main import app


def _client_for_db(db_path: Path, monkeypatch) -> TestClient:
    DatabaseRuntime.reset_instance()
    monkeypatch.setenv(DB_PATH_ENV, str(db_path))
    return TestClient(app)


def _db_without_eval_registry(tmp_path: Path) -> Path:
    db_path = tmp_path / "no-eval-registry.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE _schema_version(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO _schema_version(version, applied_at) VALUES(?, datetime('now'))",
            (latest_migration_version(),),
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def _db_with_empty_eval_registry(tmp_path: Path) -> Path:
    db_path = tmp_path / "empty-eval-registry.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE _schema_version(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO _schema_version(version, applied_at) VALUES(?, datetime('now'))",
            (latest_migration_version(),),
        )
        conn.execute("""
            CREATE TABLE eval_registry (
                eval_id TEXT PRIMARY KEY,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                rubric_score INTEGER,
                last_run_at TEXT,
                last_run_id TEXT,
                baseline_run_id TEXT,
                friction_flag INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
    finally:
        conn.close()
    return db_path


def _db_with_eval_registry_rows(tmp_path: Path) -> Path:
    db_path = tmp_path / "populated-eval-registry.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE _schema_version(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO _schema_version(version, applied_at) VALUES(?, datetime('now'))",
            (latest_migration_version(),),
        )
        conn.execute("""
            CREATE TABLE eval_registry (
                eval_id TEXT PRIMARY KEY,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                rubric_score INTEGER,
                last_run_at TEXT,
                last_run_id TEXT,
                baseline_run_id TEXT,
                friction_flag INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute(
            "INSERT INTO eval_registry(eval_id, target_type, target_id, rubric_score, friction_flag) "
            "VALUES('e1', 'skill', 'ds-core', 90, 0)"
        )
        conn.execute(
            "INSERT INTO eval_registry(eval_id, target_type, target_id, rubric_score, friction_flag) "
            "VALUES('e2', 'hook', 'on-pulse', 70, 1)"
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_eval_registry_returns_empty_list_when_table_missing(tmp_path: Path, monkeypatch) -> None:
    client = _client_for_db(_db_without_eval_registry(tmp_path), monkeypatch)
    try:
        resp = client.get("/api/v1/eval/registry")
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        DatabaseRuntime.reset_instance()


def test_eval_registry_returns_empty_list_when_table_empty(tmp_path: Path, monkeypatch) -> None:
    client = _client_for_db(_db_with_empty_eval_registry(tmp_path), monkeypatch)
    try:
        resp = client.get("/api/v1/eval/registry")
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        DatabaseRuntime.reset_instance()


def test_eval_registry_returns_correct_shape(tmp_path: Path, monkeypatch) -> None:
    client = _client_for_db(_db_with_eval_registry_rows(tmp_path), monkeypatch)
    try:
        resp = client.get("/api/v1/eval/registry")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

        skill_row = next(r for r in data if r["target_id"] == "ds-core")
        assert skill_row["target_type"] == "skill"
        assert skill_row["rubric_score"] == 90
        assert skill_row["friction_flag"] is False
        assert "baseline_score" in skill_row
        assert "last_run_at" in skill_row
        assert "last_run_id" in skill_row

        hook_row = next(r for r in data if r["target_id"] == "on-pulse")
        assert hook_row["target_type"] == "hook"
        assert hook_row["rubric_score"] == 70
        assert hook_row["friction_flag"] is True
    finally:
        DatabaseRuntime.reset_instance()
