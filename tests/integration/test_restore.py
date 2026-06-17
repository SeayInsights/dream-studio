"""Integration tests for the mutating `ds restore` command (WO-RESTORE).

Covers:
- restore from a backup replaces the state-tier db,
- restore takes a pre-restore backup of current state FIRST (reversible),
- restore consumes the exact backup directory named,
- end-to-end dry-run -> execute flow.

All tests run against a rehearsal home under tmp_path; the live ~/.dream-studio
is never touched.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.installed_productization import (
    backup_runtime,
    first_run_setup,
    restore_runtime,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _setup_home(tmp_path: Path) -> Path:
    home = tmp_path / "runtime-home"
    first_run_setup(
        source_root=REPO_ROOT,
        dream_studio_home=home,
        profiles=["core", "analytics_only"],
        rehearsal=True,
    )
    return home


def _set_marker(db_path: Path, value: str) -> None:
    """Write a marker into ds_config and flush WAL so a file copy captures it."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO ds_config(key, value, updated_at)"
            " VALUES('restore_marker', ?, datetime('now'))"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (value,),
        )
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()


def _get_marker(db_path: Path) -> str | None:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT value FROM ds_config WHERE key='restore_marker'").fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def test_restore_from_backup_replaces_state(tmp_path: Path) -> None:
    home = _setup_home(tmp_path)
    db = home / "state" / "studio.db"

    _set_marker(db, "ORIGINAL")
    backup = backup_runtime(source_root=REPO_ROOT, dream_studio_home=home, execute=True)
    _set_marker(db, "CHANGED")
    assert _get_marker(db) == "CHANGED"

    result = restore_runtime(
        source_root=REPO_ROOT,
        dream_studio_home=home,
        backup_path=backup["backup_path"],
        execute=True,
    )

    assert result["status"] == "restored"
    assert "studio.db" in result["restored_files"]
    # State replaced from the backup.
    assert _get_marker(db) == "ORIGINAL"


def test_restore_backs_up_current_state_first(tmp_path: Path) -> None:
    home = _setup_home(tmp_path)
    db = home / "state" / "studio.db"

    _set_marker(db, "V1")
    backup = backup_runtime(source_root=REPO_ROOT, dream_studio_home=home, execute=True)
    _set_marker(db, "V2-CURRENT")  # current state right before restore

    result = restore_runtime(
        source_root=REPO_ROOT,
        dream_studio_home=home,
        backup_path=backup["backup_path"],
        execute=True,
    )

    assert result["status"] == "restored"
    pre = result["pre_restore_backup_path"]
    assert pre, "restore must take a pre-restore backup first"
    pre_path = Path(pre)
    # The pre-restore backup captured the CURRENT state (V2), making restore reversible.
    assert (pre_path / "studio.db").is_file()
    assert _get_marker(pre_path / "studio.db") == "V2-CURRENT"
    # And it lives outside the home so it survives the restore / any later purge.
    assert not pre_path.is_relative_to(home)


def test_restore_selects_correct_backup(tmp_path: Path) -> None:
    home = _setup_home(tmp_path)
    db = home / "state" / "studio.db"

    # Two distinct backups; restore must consume exactly the one named.
    _set_marker(db, "BACKUP-A")
    backup_a = backup_runtime(
        source_root=REPO_ROOT, dream_studio_home=home, backup_dir=tmp_path / "a", execute=True
    )
    _set_marker(db, "BACKUP-B")
    backup_b = backup_runtime(
        source_root=REPO_ROOT, dream_studio_home=home, backup_dir=tmp_path / "b", execute=True
    )
    _set_marker(db, "LIVE")

    result = restore_runtime(
        source_root=REPO_ROOT,
        dream_studio_home=home,
        backup_path=backup_a["backup_path"],
        execute=True,
    )

    assert result["status"] == "restored"
    assert result["backup_path"] == str(Path(backup_a["backup_path"]).resolve())
    # Restored from A specifically, not B or the live state.
    assert _get_marker(db) == "BACKUP-A"
    assert backup_a["backup_path"] != backup_b["backup_path"]


def test_end_to_end(tmp_path: Path) -> None:
    home = _setup_home(tmp_path)
    db = home / "state" / "studio.db"

    _set_marker(db, "SNAPSHOT")
    backup = backup_runtime(source_root=REPO_ROOT, dream_studio_home=home, execute=True)
    _set_marker(db, "DRIFTED")

    # 1) Dry-run validates and plans, mutates nothing.
    plan = restore_runtime(
        source_root=REPO_ROOT,
        dream_studio_home=home,
        backup_path=backup["backup_path"],
        execute=False,
    )
    assert plan["status"] == "planned"
    assert plan["restore_ready"] is True
    assert plan["restore_executed"] is False
    assert _get_marker(db) == "DRIFTED"  # unchanged

    # 2) Execute restores from the snapshot and records the pre-restore backup.
    done = restore_runtime(
        source_root=REPO_ROOT,
        dream_studio_home=home,
        backup_path=backup["backup_path"],
        execute=True,
    )
    assert done["status"] == "restored"
    assert _get_marker(db) == "SNAPSHOT"
    assert (Path(done["pre_restore_backup_path"]) / "studio.db").is_file()


def test_not_ready_backup_is_refused_without_force(tmp_path: Path) -> None:
    home = _setup_home(tmp_path)
    empty_backup = tmp_path / "empty-backup"
    empty_backup.mkdir()

    result = restore_runtime(
        source_root=REPO_ROOT,
        dream_studio_home=home,
        backup_path=empty_backup,
        execute=True,
    )

    assert result["status"] == "refused"
    assert result["restore_executed"] is False
