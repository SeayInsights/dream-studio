"""Phase 8I read-only database connection semantics."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from core.config import database

pytestmark = pytest.mark.runtime_reliability


def _fake_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> Path:
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    # Clear the env-var override so _default_db_path() falls back to Path.home().
    # conftest sets DREAM_STUDIO_DB_PATH to a guard path; these tests need it absent.
    monkeypatch.delenv("DREAM_STUDIO_DB_PATH", raising=False)
    return home


def _create_db(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO sample(value) VALUES('stable')")
        conn.commit()
    finally:
        conn.close()
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


@pytest.fixture(autouse=True)
def reset_database_runtime():
    database.DatabaseRuntime.reset_instance()
    yield
    database.DatabaseRuntime.reset_instance()


def test_read_only_missing_db_does_not_create_runtime_dirs(tmp_path, monkeypatch):
    fake_home = _fake_home(monkeypatch, tmp_path / "home")

    with pytest.raises(FileNotFoundError):
        database.get_connection(read_only=True)

    assert database.DatabaseRuntime._instance is None
    assert not (fake_home / ".dream-studio").exists()


def test_read_only_existing_db_does_not_initialize_singleton_or_wal(tmp_path, monkeypatch):
    fake_home = _fake_home(monkeypatch, tmp_path / "home")
    db_path = _create_db(fake_home / ".dream-studio" / "state" / "studio.db")
    before = (_sha256(db_path), db_path.stat().st_mtime_ns)

    conn = database.get_connection(read_only=True)
    try:
        row = conn.execute("SELECT value FROM sample WHERE id = 1").fetchone()
        assert row["value"] == "stable"
        assert conn.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO sample(value) VALUES('mutated')")
    finally:
        conn.close()

    after = (_sha256(db_path), db_path.stat().st_mtime_ns)
    assert after == before
    assert database.DatabaseRuntime._instance is None
    assert not db_path.with_name("studio.db-wal").exists()
    assert not db_path.with_name("studio.db-shm").exists()


def test_read_only_respects_initialized_runtime_path(tmp_path):
    db_path = _create_db(tmp_path / "isolated" / "studio.db")
    database.DatabaseRuntime.get_instance(db_path)

    conn = database.get_connection(read_only=True)
    try:
        assert conn.execute("SELECT value FROM sample WHERE id = 1").fetchone()[0] == "stable"
        assert conn.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO sample(value) VALUES('mutated')")
    finally:
        conn.close()


def test_write_mode_still_initializes_isolated_runtime_db(tmp_path, monkeypatch):
    fake_home = _fake_home(monkeypatch, tmp_path / "home")
    db_path = fake_home / ".dream-studio" / "state" / "studio.db"

    conn = database.get_connection()
    try:
        conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO sample(value) VALUES('write-ok')")
        conn.commit()
    finally:
        conn.close()

    verify = sqlite3.connect(db_path)
    try:
        assert verify.execute("SELECT value FROM sample").fetchone()[0] == "write-ok"
    finally:
        verify.close()
    assert db_path.is_file()
    assert database.DatabaseRuntime._instance is not None
