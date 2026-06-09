"""Phase 8G native runtime readiness gate consistency tests."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.runtime_reliability

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from interfaces.cli import (
    check_migrations,
    ds_dashboard,
    runtime_preflight,
)  # noqa: E402


def _schema_db(home: Path, version: int) -> Path:
    db_path = home / ".dream-studio" / "state" / "studio.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE _schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO _schema_version(version, applied_at) VALUES(?, '2026-05-10')",
            (version,),
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def _fingerprint(path: Path) -> tuple[str, int]:
    return (hashlib.sha256(path.read_bytes()).hexdigest().upper(), path.stat().st_mtime_ns)


def _env_for(home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run_cli(script: str, *args: str, home: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / script), *args],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(REPO_ROOT),
        env=_env_for(home),
    )


def test_setup_check_is_advisory_but_names_blocked_newer_than_code(tmp_path):
    latest = runtime_preflight._latest_migration_version(REPO_ROOT)
    fake_home = tmp_path / "home"
    db_path = _schema_db(fake_home, latest + 2)
    before = _fingerprint(db_path)

    result = _run_cli("interfaces/cli/setup.py", "--check", home=fake_home)

    assert result.returncode == 0
    assert "Schema compatibility: blocked_newer_than_code" in result.stdout
    assert "Readiness: blocked" in result.stdout
    assert "setup --check policy: advisory exit 0" in result.stdout
    assert "python interfaces/cli/runtime_preflight.py --json" in result.stdout
    assert "python interfaces/cli/runtime_recovery.py --dry-run --json" in result.stdout
    assert _fingerprint(db_path) == before


def test_setup_check_json_reports_readiness_without_mutating_db(tmp_path):
    latest = runtime_preflight._latest_migration_version(REPO_ROOT)
    fake_home = tmp_path / "home"
    db_path = _schema_db(fake_home, latest + 2)
    before = _fingerprint(db_path)

    result = _run_cli("interfaces/cli/setup.py", "--check", "--json", home=fake_home)

    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["mode"] == "check"
    assert report["read_only"] is True
    assert report["ready_for_apply"] is False
    assert report["check_policy"]["blocked_newer_than_code"] == "advisory_exit_0_for_check"
    assert report["schema_compatibility"]["result"]["status"] == "blocked_newer_than_code"
    assert any(item["label"] == "hooks.json" and item["exists"] for item in report["files"])
    assert _fingerprint(db_path) == before


def test_dashboard_check_blocks_newer_than_code_with_recovery_guidance(tmp_path):
    latest = runtime_preflight._latest_migration_version(REPO_ROOT)
    fake_home = tmp_path / "home"
    db_path = _schema_db(fake_home, latest + 2)
    before = _fingerprint(db_path)

    result = _run_cli("interfaces/cli/ds_dashboard.py", "--check", home=fake_home)

    assert result.returncode == 1
    assert "Schema compatibility: blocked_newer_than_code" in result.stdout
    assert "[FAIL] Runtime DB readiness blocked: blocked_newer_than_code" in result.stdout
    assert "python interfaces/cli/runtime_preflight.py --json" in result.stdout
    assert "python interfaces/cli/runtime_recovery.py --dry-run --json" in result.stdout
    assert "Starting analytics server" not in result.stdout
    assert _fingerprint(db_path) == before


def test_dashboard_bootstrap_blocks_before_connect_on_newer_than_code(tmp_path, monkeypatch):
    latest = runtime_preflight._latest_migration_version(REPO_ROOT)
    fake_home = tmp_path / "home"
    _schema_db(fake_home, latest + 2)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))

    with patch(
        "core.event_store.studio_db._connect", side_effect=AssertionError("_connect called")
    ):
        with pytest.raises(RuntimeError, match="newer than this checkout"):
            ds_dashboard.bootstrap_db()


def test_check_migrations_blocks_before_connect_on_newer_than_code(tmp_path, monkeypatch, capsys):
    latest = runtime_preflight._latest_migration_version(REPO_ROOT)
    fake_home = tmp_path / "home"
    _schema_db(fake_home, latest + 2)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))

    with patch(
        "core.event_store.studio_db._connect", side_effect=AssertionError("_connect called")
    ):
        assert check_migrations.main() == 1

    output = capsys.readouterr().out
    assert "Schema compatibility: blocked_newer_than_code" in output
    assert "no migration connection was opened" in output



def test_native_readiness_checks_do_not_mutate_newer_than_code_db(tmp_path):
    latest = runtime_preflight._latest_migration_version(REPO_ROOT)
    fake_home = tmp_path / "home"
    db_path = _schema_db(fake_home, latest + 2)
    before = _fingerprint(db_path)

    commands = [
        ("interfaces/cli/setup.py", ["--check"], 0),
        ("interfaces/cli/ds_dashboard.py", ["--check"], 1),
        ("interfaces/cli/check_migrations.py", [], 1),
    ]
    for script, args, expected_code in commands:
        result = _run_cli(script, *args, home=fake_home)
        assert result.returncode == expected_code
        assert "blocked_newer_than_code" in result.stdout
        assert _fingerprint(db_path) == before
