from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from interfaces.cli.studio_backup import plan_backup

REPO_ROOT = Path(__file__).resolve().parents[2]


def _db(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE _schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO _schema_version(version, applied_at) VALUES(37, '2026-05-13')")
        conn.execute("CREATE TABLE sample_records (id TEXT PRIMARY KEY)")
        conn.commit()
    finally:
        conn.close()
    return path


def test_plan_backup_fingerprints_temp_db_without_writing_backup(tmp_path: Path) -> None:
    db_path = _db(tmp_path / "state" / "studio.db")
    target = tmp_path / "backups" / "studio.db.bak"

    plan = plan_backup(db_path, target)

    assert plan["read_only"] is True
    assert plan["executes_backup"] is False
    assert plan["operator_intent_required"] is True
    assert plan["ready_for_backup"] is True
    assert plan["backup_target"] == str(target.resolve())
    assert plan["source_db"]["path"] == str(db_path.resolve())
    assert plan["source_db"]["schema_version"] == 37
    assert plan["source_db"]["table_count"] == 2
    assert plan["source_db"]["sha256"]
    assert "backup_db_opens_read_only" in plan["verification_requirements"]
    assert "cleanup_execution_allowed" in plan
    assert not target.exists()


def test_plan_backup_reports_missing_db_without_creating_files(tmp_path: Path) -> None:
    db_path = tmp_path / "missing" / "studio.db"

    plan = plan_backup(db_path)

    assert plan["read_only"] is True
    assert plan["ready_for_backup"] is False
    assert plan["source_db"]["exists"] is False
    assert not db_path.exists()


def test_plan_backup_json_cli_uses_fake_home_without_creating_backup(tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    db_path = _db(fake_home / ".dream-studio" / "state" / "studio.db")
    target = db_path.with_suffix(".db.bak")
    import os as _os

    env = {
        **_os.environ,
        "HOME": str(fake_home),
        "USERPROFILE": str(fake_home),
        "PYTHONIOENCODING": "utf-8",
    }
    # conftest sets DREAM_STUDIO_HOME to a session temp path; unset it so that
    # state_dir() falls back to Path.home() and resolves under fake_home.
    env.pop("DREAM_STUDIO_HOME", None)

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "interfaces" / "cli" / "studio_backup.py"),
            "--plan-backup",
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(REPO_ROOT),
        env=env,
    )

    assert result.returncode == 0
    plan = json.loads(result.stdout)
    assert plan["read_only"] is True
    assert plan["executes_backup"] is False
    assert plan["source_db"]["path"] == str(db_path.resolve())
    assert plan["ready_for_backup"] is True
    assert not target.exists()
