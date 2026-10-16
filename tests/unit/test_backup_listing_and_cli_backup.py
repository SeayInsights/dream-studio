"""The explicit `studio_backup.py` backup and the backup listing in restore guidance.

- `interfaces/cli/studio_backup.py backup()` copied whatever studio.db held over
  studio.db.bak: run against a 0-byte authority in an installed home, it replaced a
  real backup with a 4 KB empty database. It now goes through the same checks as
  the pulse's backup_db (no empty source, a richer .bak is kept).
- The guidance listed `studio.db.bak*`, so studio.db.bak-wal and -shm came first as
  "backups", and nothing said which backup was itself empty.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _authority(path: Path, projects: int, monkeypatch) -> None:
    from core.config.sqlite_bootstrap import CREATE_AUTHORITY_ENV, bootstrap_database

    monkeypatch.setenv("DREAM_STUDIO_APPLY_UNRELEASED", "1")
    monkeypatch.setenv(CREATE_AUTHORITY_ENV, str(path))
    bootstrap_database(path)
    monkeypatch.delenv(CREATE_AUTHORITY_ENV)
    conn = sqlite3.connect(str(path))
    for i in range(projects):
        conn.execute(
            "INSERT INTO business_projects (project_id, name, status, created_at, updated_at)"
            " VALUES (?, ?, 'active', datetime('now'), datetime('now'))",
            (f"p{i}", f"P{i}"),
        )
    conn.commit()
    conn.close()


@pytest.fixture
def marked(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    (home / "state" / "installed-version").write_text("0.1.0 abc\n", encoding="utf-8")
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(home))
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(home / "state" / "studio.db"))
    return home


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_the_cli_backup_never_replaces_a_backup_with_an_empty_authority(marked, monkeypatch):
    bak = marked / "state" / "studio.db.bak"
    _authority(bak, projects=2, monkeypatch=monkeypatch)
    before = _sha(bak)
    (marked / "state" / "studio.db").write_bytes(b"")

    env = {"DREAM_STUDIO_HOME": str(marked), "PYTHONPATH": str(REPO)}
    full = {
        **{k: v for k, v in os.environ.items() if not k.startswith(("DREAM_STUDIO", "DS_"))},
        **env,
        "DREAM_STUDIO_DB_PATH": str(marked / "state" / "studio.db"),
    }
    proc = subprocess.run(
        [sys.executable, str(REPO / "interfaces" / "cli" / "studio_backup.py")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=full,
        timeout=300,
    )
    assert _sha(bak) == before, "the real backup was replaced"
    assert proc.returncode != 0, proc.stdout + proc.stderr


def test_the_cli_backup_still_backs_up_a_real_authority(marked, monkeypatch):
    from interfaces.cli import studio_backup

    db = marked / "state" / "studio.db"
    _authority(db, projects=1, monkeypatch=monkeypatch)
    bak = studio_backup.backup(db)
    assert bak.is_file() and bak.stat().st_size > 0


def test_the_listing_names_only_backups_and_says_what_each_holds(marked, monkeypatch):
    from core.config.sqlite_bootstrap import present_backups, restore_guidance

    state = marked / "state"
    _authority(state / "studio.db.bak.20261001T000000Z", projects=3, monkeypatch=monkeypatch)
    time.sleep(0.02)
    _authority(state / "studio.db.bak", projects=1, monkeypatch=monkeypatch)
    time.sleep(0.02)
    (state / "studio.db.bak-wal").write_bytes(b"x" * 10)
    (state / "studio.db.bak-shm").write_bytes(b"x" * 10)
    (state / "backups" / "self-install-1").mkdir(parents=True)
    (state / "backups" / "self-install-1" / "studio.db").write_bytes(b"")

    listed = present_backups(marked)
    names = [p.name for p in listed]
    assert "studio.db.bak-wal" not in names and "studio.db.bak-shm" not in names
    assert {"studio.db.bak", "studio.db.bak.20261001T000000Z", "self-install-1"} <= set(names)

    text = restore_guidance(marked, state / "studio.db")
    assert "projects 3" in text and "projects 1" in text
    assert "empty" in text, "an empty newest backup must be visible as empty"


def test_with_no_backup_the_guidance_names_the_deliberate_way_out(marked):
    from core.config.sqlite_bootstrap import CREATE_AUTHORITY_ENV, restore_guidance

    db = marked / "state" / "studio.db"
    text = restore_guidance(marked, db)
    assert f"{CREATE_AUTHORITY_ENV}={db}" in text
