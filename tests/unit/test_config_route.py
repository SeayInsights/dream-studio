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


def _db_without_ds_config(tmp_path: Path) -> Path:
    db_path = tmp_path / "no-ds-config.db"
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


def _db_with_empty_ds_config(tmp_path: Path) -> Path:
    db_path = tmp_path / "empty-ds-config.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE _schema_version(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO _schema_version(version, applied_at) VALUES(?, datetime('now'))",
            (latest_migration_version(),),
        )
        conn.execute(
            "CREATE TABLE ds_config("
            "key TEXT PRIMARY KEY, "
            "value TEXT NOT NULL, "
            "updated_at TEXT NOT NULL DEFAULT (datetime('now')))"
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def _db_with_ds_config_rows(tmp_path: Path) -> Path:
    db_path = tmp_path / "populated-ds-config.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE _schema_version(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO _schema_version(version, applied_at) VALUES(?, datetime('now'))",
            (latest_migration_version(),),
        )
        conn.execute(
            "CREATE TABLE ds_config("
            "key TEXT PRIMARY KEY, "
            "value TEXT NOT NULL, "
            "updated_at TEXT NOT NULL DEFAULT (datetime('now')))"
        )
        conn.execute(
            "INSERT INTO ds_config(key, value, updated_at) VALUES('env', 'local', '2026-06-14T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO ds_config(key, value, updated_at)"
            " VALUES('debug_mode', 'false', '2026-06-14T00:00:00Z')"
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_config_returns_empty_list_when_table_missing(tmp_path: Path, monkeypatch) -> None:
    client = _client_for_db(_db_without_ds_config(tmp_path), monkeypatch)
    try:
        resp = client.get("/api/v1/config")
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        DatabaseRuntime.reset_instance()


def test_config_returns_empty_list_when_table_empty(tmp_path: Path, monkeypatch) -> None:
    client = _client_for_db(_db_with_empty_ds_config(tmp_path), monkeypatch)
    try:
        resp = client.get("/api/v1/config")
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        DatabaseRuntime.reset_instance()


def test_config_returns_correct_rows(tmp_path: Path, monkeypatch) -> None:
    client = _client_for_db(_db_with_ds_config_rows(tmp_path), monkeypatch)
    try:
        resp = client.get("/api/v1/config")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        keys = {r["key"] for r in data}
        assert keys == {"env", "debug_mode"}
        env_row = next(r for r in data if r["key"] == "env")
        assert env_row["value"] == "local"
        assert "updated_at" in env_row
    finally:
        DatabaseRuntime.reset_instance()
