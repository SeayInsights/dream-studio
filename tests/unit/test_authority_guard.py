"""A missing authority is restored, never silently re-created.

On 2026-09-23 the operator's authority was replaced by an empty database: a path
resolved to a missing studio.db, sqlite3.connect() created it, the migrations ran,
and every command afterwards worked against a database with no projects in it.
bootstrap_database, _connect and get_connection all create a missing file, and
nothing consulted the evidence (state/installed-version, an integration manifest)
that the home had held a real one. run_migrations() also returned early, silently,
when it found no migration files, leaving a schema-less database behind.

These tests drive the three creation paths in a home that HAS been installed into,
in a home with no migration files, and in a brand-new home (which must still work).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.config import sqlite_bootstrap
from core.config.sqlite_bootstrap import bootstrap_database, latest_migration_version

#: core.config.sqlite_bootstrap.CREATE_AUTHORITY_ENV; AuthorityRefusedError is a RuntimeError.
CREATE_AUTHORITY_ENV = "DREAM_STUDIO_CREATE_AUTHORITY"
REFUSED = RuntimeError


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "ds-home"
    (home / "state").mkdir(parents=True)
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(home))
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(home / "state" / "studio.db"))
    monkeypatch.delenv(CREATE_AUTHORITY_ENV, raising=False)
    # These tests are about creating a database, not the unreleased-migration gate, which
    # holds back the newest shipped migration from any database inside the home.
    monkeypatch.setenv("DREAM_STUDIO_APPLY_UNRELEASED", "1")
    from core.config.database import DatabaseRuntime

    DatabaseRuntime.reset_instance()
    yield home
    DatabaseRuntime.reset_instance()


def _installed(home: Path) -> None:
    (home / "state" / "installed-version").write_text("0.1.0 abc\n", encoding="utf-8")


def _creators(db: Path):
    from core.config.database import get_connection
    from core.event_store.connection import _connect

    return {
        "bootstrap_database": lambda: bootstrap_database(db),
        "_connect": lambda: _connect(db).close(),
        "get_connection": lambda: get_connection().close(),
    }


@pytest.mark.parametrize("creator", ["bootstrap_database", "_connect", "get_connection"])
def test_refuses_to_recreate_a_missing_authority_in_an_installed_home(home, creator):
    _installed(home)
    db = home / "state" / "studio.db"

    with pytest.raises(REFUSED, match="Refusing") as excinfo:
        _creators(db)[creator]()

    message = str(excinfo.value)
    assert "installed-version" in message
    assert str(home / "state" / "backups") in message
    assert "ds restore" in message
    assert not db.exists(), "the refusal must not leave an empty database behind"


def test_an_integration_manifest_also_marks_the_home_as_installed(home):
    manifest = home / "integrations" / "claude_code" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}", encoding="utf-8")

    with pytest.raises(REFUSED, match="manifest.json"):
        bootstrap_database(home / "state" / "studio.db")


@pytest.mark.parametrize("creator", ["bootstrap_database", "_connect", "get_connection"])
def test_refuses_to_create_any_database_with_no_migration_files(
    home, tmp_path, monkeypatch, creator
):
    empty = tmp_path / "no-migrations"
    empty.mkdir()
    monkeypatch.setattr(sqlite_bootstrap, "migrations_dir", lambda: empty)
    db = home / "state" / "studio.db"

    with pytest.raises(REFUSED, match="no migration files"):
        _creators(db)[creator]()
    assert not db.exists()


def test_a_brand_new_home_creates_and_migrates_normally(home):
    db = home / "state" / "studio.db"
    assert bootstrap_database(db) == latest_migration_version()
    assert db.is_file()


def test_an_existing_authority_opens_even_in_an_installed_home(home):
    db = home / "state" / "studio.db"
    bootstrap_database(db)
    _installed(home)
    from core.event_store.connection import _connect

    conn = _connect(db)
    try:
        assert conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0] > 0
    finally:
        conn.close()


def test_explicit_opt_in_creates_a_fresh_authority(home, monkeypatch):
    _installed(home)
    monkeypatch.setenv(CREATE_AUTHORITY_ENV, "1")
    db = home / "state" / "studio.db"
    assert bootstrap_database(db) == latest_migration_version()


def test_a_database_outside_any_home_layout_is_not_guarded(tmp_path):
    db = tmp_path / "scratch.db"
    bootstrap_database(db)
    assert sqlite3.connect(str(db)).execute("SELECT 1").fetchone() == (1,)
