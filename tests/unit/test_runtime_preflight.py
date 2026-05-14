"""Phase 8B local runtime preflight isolation tests."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.runtime_reliability

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from interfaces.cli import runtime_preflight  # noqa: E402


def _check(report: dict, name: str) -> dict:
    for item in report["checks"]:
        if item["name"] == name:
            return item
    raise AssertionError(f"Missing preflight check: {name}")


def _schema_db(path: Path, version: int | None) -> Path:
    conn = sqlite3.connect(path)
    try:
        if version is not None:
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
    return path


def test_schema_migration_validation_does_not_import_default_connection():
    source = (REPO_ROOT / "tests" / "integration" / "test_schema_migrations.py").read_text(
        encoding="utf-8"
    )

    assert "from core.config.database import get_connection" not in source
    assert "get_connection(" not in source
    assert "tmp_path" in source


def test_runtime_write_path_verification_is_explicit_opt_in():
    source = (REPO_ROOT / "tests" / "runtime_verification" / "test_write_paths.py").read_text(
        encoding="utf-8"
    )

    assert "DREAM_STUDIO_RUNTIME_WRITE_VERIFY" in source
    assert "allow_module_level=True" in source
    assert "touches the real Dream Studio DB" in source


def test_preflight_module_avoids_runtime_bootstrap_apis():
    source = (REPO_ROOT / "interfaces" / "cli" / "runtime_preflight.py").read_text(encoding="utf-8")

    assert "get_connection(" not in source
    assert "paths.state_dir(" not in source
    assert "subprocess" not in source
    assert "webbrowser" not in source


def test_newer_than_code_schema_is_blocked_with_guidance(tmp_path):
    latest = runtime_preflight._latest_migration_version(REPO_ROOT)
    db = _schema_db(tmp_path / "studio.db", latest + 2)
    db.with_suffix(".db.bak").write_bytes(b"backup")

    result = runtime_preflight.inspect_schema_compatibility(db_path=db, repo_root=REPO_ROOT)

    assert result["status"] == "blocked_newer_than_code"
    assert result["severity"] == "error"
    assert result["compatible"] is False
    assert result["schema_version"] == latest + 2
    assert result["backup_exists"] is True
    assert runtime_preflight.schema_compatibility_is_blocking(result) is True
    assert "Do not manually edit _schema_version" in "\n".join(result["guidance"])


def test_compatible_schema_reports_compatible(tmp_path):
    latest = runtime_preflight._latest_migration_version(REPO_ROOT)
    db = _schema_db(tmp_path / "studio.db", latest)

    result = runtime_preflight.inspect_schema_compatibility(db_path=db, repo_root=REPO_ROOT)

    assert result["status"] == "compatible"
    assert result["severity"] == "info"
    assert result["compatible"] is True
    assert result["schema_current"] is True


def test_older_schema_reports_migration_available_without_mutating(tmp_path):
    latest = runtime_preflight._latest_migration_version(REPO_ROOT)
    db = _schema_db(tmp_path / "studio.db", latest - 1)

    result = runtime_preflight.inspect_schema_compatibility(db_path=db, repo_root=REPO_ROOT)
    conn = sqlite3.connect(db)
    try:
        stored = conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0]
    finally:
        conn.close()

    assert result["status"] == "migration_available"
    assert result["severity"] == "warning"
    assert result["compatible"] is True
    assert stored == latest - 1


def test_missing_schema_version_reports_unknown_without_mutating(tmp_path):
    db = _schema_db(tmp_path / "studio.db", None)

    result = runtime_preflight.inspect_schema_compatibility(db_path=db, repo_root=REPO_ROOT)

    assert result["status"] == "unknown_missing_schema_version"
    assert result["severity"] == "warning"
    assert result["compatible"] is None
    assert result["schema_version"] is None


def test_preflight_reports_missing_db_without_creating_runtime_dirs(tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    report = runtime_preflight.run_preflight(
        runtime_preflight.PreflightConfig(
            repo_root=REPO_ROOT,
            home=fake_home,
            replay_migrations=False,
        )
    )

    runtime_db = _check(report, "runtime_db")
    assert runtime_db["status"] == "missing"
    assert runtime_db["details"]["created"] is False
    assert report["read_only"] is True
    assert not (fake_home / ".dream-studio").exists()


def test_setup_and_dashboard_checks_do_not_create_fake_runtime_db(tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env["USERPROFILE"] = str(fake_home)

    setup = subprocess.run(
        [sys.executable, str(REPO_ROOT / "interfaces" / "cli" / "setup.py"), "--check"],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(REPO_ROOT),
        env=env,
    )
    dashboard = subprocess.run(
        [sys.executable, str(REPO_ROOT / "interfaces" / "cli" / "ds_dashboard.py"), "--check"],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(REPO_ROOT),
        env=env,
    )

    assert setup.returncode == 0
    assert dashboard.returncode == 0
    assert "Schema compatibility: missing" in setup.stdout
    assert "Schema compatibility: missing" in dashboard.stdout
    assert not (fake_home / ".dream-studio").exists()


def test_fresh_migration_replay_uses_temp_db_not_runtime_db(tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    report = runtime_preflight.run_preflight(
        runtime_preflight.PreflightConfig(repo_root=REPO_ROOT, home=fake_home)
    )

    replay = _check(report, "fresh_migration_replay")
    assert replay["status"] == "ok"
    assert replay["details"]["used_canonical_db"] is False
    assert str(fake_home) not in replay["details"]["temp_db_path"]
    assert replay["details"]["canonical_db_path"].endswith(".dream-studio\\state\\studio.db") or (
        replay["details"]["canonical_db_path"].endswith(".dream-studio/state/studio.db")
    )
    assert not (fake_home / ".dream-studio").exists()


def test_hook_dashboard_backup_and_cloud_checks_are_observational(tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    report = runtime_preflight.run_preflight(
        runtime_preflight.PreflightConfig(
            repo_root=REPO_ROOT,
            home=fake_home,
            replay_migrations=False,
        )
    )

    hooks = _check(report, "hooks")
    dashboard = _check(report, "dashboard_preflight")
    backup = _check(report, "backup")
    cloud = _check(report, "optional_cloud_backup")

    assert hooks["status"] == "ok"
    assert hooks["details"]["handler_count"] > 0
    assert hooks["details"]["hooks_lib_exists"] is False

    assert dashboard["status"] == "ok"
    assert dashboard["details"]["mode"] == "static_observational"
    assert dashboard["details"]["server_started"] is False

    assert backup["status"] == "missing"
    assert backup["details"]["exists"] is False
    assert not Path(backup["details"]["backup_path"]).exists()

    assert cloud["status"] == "not_configured"
    assert cloud["details"]["optional"] is True
    assert cloud["details"]["authoritative"] is False
    assert not (fake_home / ".dream-studio").exists()
