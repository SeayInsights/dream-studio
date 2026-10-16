"""Tests for migration-safety guards (WO-MS).

Verifies:
  1. Unreleased migrations are NOT applied to the live authority DB by default.
  2. Released migrations apply normally to the live authority DB.
  3. A timestamped backup is created before the first migration applies to live.
  4. DREAM_STUDIO_APPLY_UNRELEASED=1 overrides the gate.
  5. Non-live (temp/test) DBs are never gated — unreleased migrations apply normally.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import (
    _backup_live_db,
    _is_live_authority_db,
    bootstrap_database,
    released_migration_version,
    run_migrations,
)

# ── helpers ──────────────────────────────────────────────────────────────────


def _make_db(path: Path) -> sqlite3.Connection:
    """Open a fresh SQLite connection suitable for run_migrations()."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _schema_version(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()
        return int((row[0] if row else 0) or 0)
    except sqlite3.OperationalError:
        return 0


def _inject_migration(migrations_dir: Path, version: int, sql: str = "") -> Path:
    """Write a minimal SQL migration file for testing."""
    path = migrations_dir / f"{version:03d}_test_sentinel.sql"
    path.write_text(sql or f"-- migration {version} sentinel\n", encoding="utf-8")
    return path


# ── _is_live_authority_db ─────────────────────────────────────────────────────


def test_live_db_detected_under_dream_studio_home(tmp_path, monkeypatch):
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(tmp_path / ".dream-studio"))
    live_path = str(tmp_path / ".dream-studio" / "state" / "studio.db")
    assert _is_live_authority_db(live_path) is True


def test_live_db_covers_the_home_in_use_and_the_default_home(tmp_path, monkeypatch):
    """An authority under `--home X` is as live as the default one, and the default one
    stays live whatever DREAM_STUDIO_HOME says.

    _is_live_authority_db checked only the default home, so a home set through
    DREAM_STUDIO_HOME was exempt from the unreleased-migration gate and the pre-migration
    backup.
    """
    other_home = tmp_path / "elsewhere"
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(other_home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert _is_live_authority_db(str(other_home / "state" / "studio.db")) is True
    assert _is_live_authority_db(str(tmp_path / ".dream-studio" / "state" / "studio.db")) is True
    assert _is_live_authority_db(str(tmp_path / "scratch" / "studio.db")) is False


def test_temp_db_not_detected_as_live(tmp_path):
    temp_path = str(tmp_path / "studio.db")
    assert _is_live_authority_db(temp_path) is False


def test_empty_db_file_not_live():
    assert _is_live_authority_db("") is False


# ── released_migration_version ────────────────────────────────────────────────


def test_released_version_reads_from_file(tmp_path, monkeypatch):
    """released_migration_version() reads the .released_version sentinel."""
    from core.config import sqlite_bootstrap

    fake_migrations = tmp_path / "migrations"
    fake_migrations.mkdir()
    (fake_migrations / ".released_version").write_text("42\n", encoding="utf-8")
    monkeypatch.setattr(sqlite_bootstrap, "migrations_dir", lambda: fake_migrations)
    assert sqlite_bootstrap.released_migration_version() == 42


def test_released_version_defaults_to_latest_when_file_absent(tmp_path, monkeypatch):
    """When .released_version is absent, all current migrations are treated released."""
    from core.config import sqlite_bootstrap

    fake_migrations = tmp_path / "migrations"
    fake_migrations.mkdir()
    # Write one migration file so latest_migration_version() returns 1
    (fake_migrations / "001_test.sql").write_text("-- test\n", encoding="utf-8")
    monkeypatch.setattr(sqlite_bootstrap, "migrations_dir", lambda: fake_migrations)
    assert sqlite_bootstrap.released_migration_version() == 1


# ── unreleased gate ───────────────────────────────────────────────────────────


def test_unreleased_migration_skipped_on_live_db(tmp_path, monkeypatch):
    """An unreleased migration must NOT apply to the live authority DB."""
    from core.config import sqlite_bootstrap

    # Point home to tmp_path so live-authority check works
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(tmp_path / ".dream-studio"))
    monkeypatch.delenv("DREAM_STUDIO_APPLY_UNRELEASED", raising=False)

    # Set up fake migrations dir with two migrations: 001 (released) and 002 (unreleased)
    fake_migrations = tmp_path / "migrations"
    fake_migrations.mkdir()
    _inject_migration(fake_migrations, 1)
    _inject_migration(fake_migrations, 2)
    (fake_migrations / ".released_version").write_text("1\n", encoding="utf-8")
    monkeypatch.setattr(sqlite_bootstrap, "migrations_dir", lambda: fake_migrations)
    monkeypatch.setattr(
        sqlite_bootstrap, "migration_files", lambda: sorted(fake_migrations.glob("[0-9]*.sql"))
    )

    live_db = tmp_path / ".dream-studio" / "state" / "studio.db"
    conn = _make_db(live_db)
    try:
        with pytest.warns(RuntimeWarning, match="unreleased"):
            run_migrations(conn)
        # Only migration 1 should be applied; 2 is skipped
        assert _schema_version(conn) == 1
    finally:
        conn.close()


def test_released_migration_applies_to_live_db(tmp_path, monkeypatch):
    """A released migration applies normally to the live authority DB."""
    from core.config import sqlite_bootstrap

    monkeypatch.setenv("DREAM_STUDIO_HOME", str(tmp_path / ".dream-studio"))
    monkeypatch.delenv("DREAM_STUDIO_APPLY_UNRELEASED", raising=False)

    fake_migrations = tmp_path / "migrations"
    fake_migrations.mkdir()
    _inject_migration(fake_migrations, 1)
    (fake_migrations / ".released_version").write_text("1\n", encoding="utf-8")
    monkeypatch.setattr(sqlite_bootstrap, "migrations_dir", lambda: fake_migrations)
    monkeypatch.setattr(
        sqlite_bootstrap, "migration_files", lambda: sorted(fake_migrations.glob("[0-9]*.sql"))
    )

    live_db = tmp_path / ".dream-studio" / "state" / "studio.db"
    conn = _make_db(live_db)
    try:
        run_migrations(conn)
        assert _schema_version(conn) == 1
    finally:
        conn.close()


def test_apply_unreleased_opt_in_applies_unreleased_migration(tmp_path, monkeypatch):
    """DREAM_STUDIO_APPLY_UNRELEASED=1 allows unreleased migrations on live DB."""
    from core.config import sqlite_bootstrap

    monkeypatch.setenv("DREAM_STUDIO_HOME", str(tmp_path / ".dream-studio"))
    monkeypatch.setenv("DREAM_STUDIO_APPLY_UNRELEASED", "1")

    fake_migrations = tmp_path / "migrations"
    fake_migrations.mkdir()
    _inject_migration(fake_migrations, 1)
    _inject_migration(fake_migrations, 2)
    (fake_migrations / ".released_version").write_text("1\n", encoding="utf-8")
    monkeypatch.setattr(sqlite_bootstrap, "migrations_dir", lambda: fake_migrations)
    monkeypatch.setattr(
        sqlite_bootstrap, "migration_files", lambda: sorted(fake_migrations.glob("[0-9]*.sql"))
    )

    live_db = tmp_path / ".dream-studio" / "state" / "studio.db"
    conn = _make_db(live_db)
    try:
        run_migrations(conn)
        # Both migrations should apply
        assert _schema_version(conn) == 2
    finally:
        conn.close()


def test_unreleased_migration_applies_to_non_live_db(tmp_path, monkeypatch):
    """Temp/test DBs are never gated — unreleased migrations apply normally."""
    from core.config import sqlite_bootstrap

    # Use a real tmp_path home so the live check uses a different base
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(tmp_path / "some-other-home" / ".dream-studio"))
    monkeypatch.delenv("DREAM_STUDIO_APPLY_UNRELEASED", raising=False)

    fake_migrations = tmp_path / "migrations"
    fake_migrations.mkdir()
    _inject_migration(fake_migrations, 1)
    _inject_migration(fake_migrations, 2)
    (fake_migrations / ".released_version").write_text("1\n", encoding="utf-8")
    monkeypatch.setattr(sqlite_bootstrap, "migrations_dir", lambda: fake_migrations)
    monkeypatch.setattr(
        sqlite_bootstrap, "migration_files", lambda: sorted(fake_migrations.glob("[0-9]*.sql"))
    )

    # DB is in tmp_path, NOT under ~/.dream-studio/
    temp_db = tmp_path / "test-studio.db"
    conn = _make_db(temp_db)
    try:
        run_migrations(conn)
        assert _schema_version(conn) == 2
    finally:
        conn.close()


# ── backup ────────────────────────────────────────────────────────────────────


def test_backup_created_before_migration_on_live_db(tmp_path, monkeypatch):
    """A timestamped backup is written to ~/.dream-studio/state/backups/ before migration."""
    from core.config import sqlite_bootstrap

    monkeypatch.setenv("DREAM_STUDIO_HOME", str(tmp_path / ".dream-studio"))
    monkeypatch.delenv("DREAM_STUDIO_APPLY_UNRELEASED", raising=False)

    fake_migrations = tmp_path / "migrations"
    fake_migrations.mkdir()
    _inject_migration(fake_migrations, 1)
    (fake_migrations / ".released_version").write_text("1\n", encoding="utf-8")
    monkeypatch.setattr(sqlite_bootstrap, "migrations_dir", lambda: fake_migrations)
    monkeypatch.setattr(
        sqlite_bootstrap, "migration_files", lambda: sorted(fake_migrations.glob("[0-9]*.sql"))
    )

    live_db = tmp_path / ".dream-studio" / "state" / "studio.db"
    conn = _make_db(live_db)
    try:
        run_migrations(conn)
        backup_dir = tmp_path / ".dream-studio" / "state" / "backups"
        backups = list(backup_dir.glob("studio-pre-*.db"))
        assert len(backups) == 1, f"Expected 1 backup, got {backups}"
    finally:
        conn.close()


def test_no_backup_on_non_live_db(tmp_path, monkeypatch):
    """No backup is written for temp/test DBs."""
    from core.config import sqlite_bootstrap

    monkeypatch.setenv("DREAM_STUDIO_HOME", str(tmp_path / "other-home" / ".dream-studio"))
    monkeypatch.delenv("DREAM_STUDIO_APPLY_UNRELEASED", raising=False)

    fake_migrations = tmp_path / "migrations"
    fake_migrations.mkdir()
    _inject_migration(fake_migrations, 1)
    (fake_migrations / ".released_version").write_text("1\n", encoding="utf-8")
    monkeypatch.setattr(sqlite_bootstrap, "migrations_dir", lambda: fake_migrations)
    monkeypatch.setattr(
        sqlite_bootstrap, "migration_files", lambda: sorted(fake_migrations.glob("[0-9]*.sql"))
    )

    temp_db = tmp_path / "studio.db"
    conn = _make_db(temp_db)
    try:
        run_migrations(conn)
        # No backups directory under the other-home
        backup_dir = tmp_path / "other-home" / ".dream-studio" / "state" / "backups"
        assert not backup_dir.exists() or not list(backup_dir.glob("studio-pre-*.db"))
    finally:
        conn.close()


def test_backup_only_taken_once_per_run_migrations_call(tmp_path, monkeypatch):
    """Only one backup is created per run_migrations() call, regardless of migration count."""
    from core.config import sqlite_bootstrap

    monkeypatch.setenv("DREAM_STUDIO_HOME", str(tmp_path / ".dream-studio"))
    monkeypatch.delenv("DREAM_STUDIO_APPLY_UNRELEASED", raising=False)

    fake_migrations = tmp_path / "migrations"
    fake_migrations.mkdir()
    _inject_migration(fake_migrations, 1)
    _inject_migration(fake_migrations, 2)
    _inject_migration(fake_migrations, 3)
    (fake_migrations / ".released_version").write_text("3\n", encoding="utf-8")
    monkeypatch.setattr(sqlite_bootstrap, "migrations_dir", lambda: fake_migrations)
    monkeypatch.setattr(
        sqlite_bootstrap, "migration_files", lambda: sorted(fake_migrations.glob("[0-9]*.sql"))
    )

    live_db = tmp_path / ".dream-studio" / "state" / "studio.db"
    conn = _make_db(live_db)
    try:
        run_migrations(conn)
        backup_dir = tmp_path / ".dream-studio" / "state" / "backups"
        backups = list(backup_dir.glob("studio-pre-*.db"))
        assert len(backups) == 1, f"Expected exactly 1 backup, got {backups}"
    finally:
        conn.close()


def test_activation_state_beside_an_authority_raises_only_its_released_version(
    tmp_path, monkeypatch
):
    """`ds migrate activate` records its activation beside the authority it activated
    (ACTIVATED_VERSION_FILE), never in the shipped migrations directory: one authority's
    activation must not release a migration for another."""
    from core.config import sqlite_bootstrap

    fake_migrations = tmp_path / "migrations"
    fake_migrations.mkdir()
    for version in (1, 2, 3):
        _inject_migration(fake_migrations, version)
    (fake_migrations / ".released_version").write_text("1\n", encoding="utf-8")
    monkeypatch.setattr(sqlite_bootstrap, "migrations_dir", lambda: fake_migrations)

    activated = tmp_path / "home-a" / "state" / "studio.db"
    other = tmp_path / "home-b" / "state" / "studio.db"
    activated.parent.mkdir(parents=True)
    (activated.parent / sqlite_bootstrap.ACTIVATED_VERSION_FILE).write_text("3", encoding="utf-8")

    assert released_migration_version(activated) == 3
    assert released_migration_version(other) == 1
    assert (fake_migrations / ".released_version").read_text(encoding="utf-8") == "1\n"
