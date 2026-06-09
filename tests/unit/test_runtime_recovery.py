"""Phase 8D local runtime recovery dry-run isolation tests."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.runtime_reliability

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from interfaces.cli import runtime_preflight, runtime_recovery  # noqa: E402


def _schema_db(path: Path, version: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
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
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _candidate(report: dict, role: str) -> dict:
    for item in report["backup_candidates"]:
        if item["role"] == role:
            return item
    raise AssertionError(f"Missing backup candidate role: {role}")


def test_dry_run_missing_home_does_not_create_runtime_dir(tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    report = runtime_recovery.run_recovery_dry_run(
        runtime_recovery.RecoveryConfig(repo_root=REPO_ROOT, home=fake_home)
    )

    assert report["dry_run"] is True
    assert report["mutations_performed"] is False
    assert report["external_calls_made"] is False
    assert report["current"]["status"] == "missing"
    assert report["current"]["exists"] is False
    assert _candidate(report, "default_backup")["exists"] is False
    assert not (fake_home / ".dream-studio").exists()


def test_dry_run_classifies_current_and_backup_version_skew(tmp_path):
    latest = runtime_preflight._latest_migration_version(REPO_ROOT)
    fake_home = tmp_path / "home"
    state_dir = fake_home / ".dream-studio" / "state"
    current = _schema_db(state_dir / "studio.db", latest + 2)
    compatible_backup = _schema_db(state_dir / "studio.db.bak", latest)
    newer_backup = _schema_db(state_dir / "studio-20260510T010203Z.db.bak", latest + 4)

    report = runtime_recovery.run_recovery_dry_run(
        runtime_recovery.RecoveryConfig(repo_root=REPO_ROOT, home=fake_home)
    )

    assert report["current"]["path"] == str(current)
    assert report["current"]["status"] == "blocked_newer_than_code"
    assert report["current"]["schema_version"] == latest + 2

    default_backup = _candidate(report, "default_backup")
    assert default_backup["path"] == str(compatible_backup)
    assert default_backup["status"] == "compatible"
    assert default_backup["schema_version"] == latest

    timestamped_backup = _candidate(report, "timestamped_export")
    assert timestamped_backup["path"] == str(newer_backup)
    assert timestamped_backup["status"] == "blocked_newer_than_code"
    assert timestamped_backup["schema_version"] == latest + 4

    assert (
        report["recommendation"]["action"] == "use_compatible_checkout_or_review_backup_candidate"
    )
    assert report["recommendation"]["compatible_backup_count"] == 1


def test_dry_run_does_not_mutate_current_db_or_backups(tmp_path):
    latest = runtime_preflight._latest_migration_version(REPO_ROOT)
    fake_home = tmp_path / "home"
    state_dir = fake_home / ".dream-studio" / "state"
    files = [
        _schema_db(state_dir / "studio.db", latest + 2),
        _schema_db(state_dir / "studio.db.bak", latest),
        _schema_db(state_dir / "studio.db.pre-restore.bak", latest - 1),
    ]
    before = {path: (_sha256(path), path.stat().st_mtime_ns) for path in files}

    runtime_recovery.run_recovery_dry_run(
        runtime_recovery.RecoveryConfig(repo_root=REPO_ROOT, home=fake_home)
    )

    after = {path: (_sha256(path), path.stat().st_mtime_ns) for path in files}
    assert after == before


def test_dry_run_reports_missing_backup_when_state_dir_exists(tmp_path):
    latest = runtime_preflight._latest_migration_version(REPO_ROOT)
    fake_home = tmp_path / "home"
    state_dir = fake_home / ".dream-studio" / "state"
    _schema_db(state_dir / "studio.db", latest)

    report = runtime_recovery.run_recovery_dry_run(
        runtime_recovery.RecoveryConfig(repo_root=REPO_ROOT, home=fake_home)
    )

    assert report["current"]["status"] == "compatible"
    assert report["overall"] == "review"
    default_backup = _candidate(report, "default_backup")
    assert default_backup["status"] == "missing"
    assert default_backup["exists"] is False
    assert default_backup["size_bytes"] is None


def test_json_output_is_stable_for_automation(tmp_path, capsys):
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    exit_code = runtime_recovery.main(["--dry-run", "--json", "--home", str(fake_home)])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert {
        "dry_run",
        "notice",
        "overall",
        "repo_root",
        "home",
        "current",
        "backup_candidates",
        "recommendation",
        "summary",
        "mutations_performed",
        "external_calls_made",
    }.issubset(payload)
    assert payload["current"]["status"] == "missing"
    assert payload["backup_candidates"][0]["role"] == "default_backup"
    assert payload["mutations_performed"] is False
    assert payload["external_calls_made"] is False


def test_plan_restore_requires_source(tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    with pytest.raises(SystemExit) as excinfo:
        runtime_recovery.main(["--plan-restore", "--json", "--home", str(fake_home)])

    assert excinfo.value.code == 2
    assert not (fake_home / ".dream-studio").exists()


def test_plan_restore_missing_source_does_not_mutate_current_db(tmp_path):
    latest = runtime_preflight._latest_migration_version(REPO_ROOT)
    fake_home = tmp_path / "home"
    current = _schema_db(fake_home / ".dream-studio" / "state" / "studio.db", latest)
    before = (_sha256(current), current.stat().st_mtime_ns)
    missing_source = tmp_path / "missing.db.bak"

    report = runtime_recovery.run_restore_plan_preview(
        source=missing_source,
        config=runtime_recovery.RecoveryConfig(repo_root=REPO_ROOT, home=fake_home),
    )

    after = (_sha256(current), current.stat().st_mtime_ns)
    assert report["overall"] == "blocked"
    assert report["source"]["status"] == "missing"
    assert "does not exist" in report["errors"][0]
    assert report["mutations_performed"] is False
    assert after == before
    assert not missing_source.exists()


def test_plan_restore_older_backup_reports_data_loss_warning(tmp_path):
    latest = runtime_preflight._latest_migration_version(REPO_ROOT)
    fake_home = tmp_path / "home"
    state_dir = fake_home / ".dream-studio" / "state"
    _schema_db(state_dir / "studio.db", latest + 2)
    source = _schema_db(state_dir / "studio.db.pre-restore.bak", latest - 1)

    report = runtime_recovery.run_restore_plan_preview(
        source=source,
        config=runtime_recovery.RecoveryConfig(repo_root=REPO_ROOT, home=fake_home),
    )

    assert report["overall"] == "warning"
    assert report["schema_relation"] == "source_older_than_current"
    assert report["source"]["status"] == "migration_available"
    assert report["compatibility_impact"]["source_compatible_with_checkout"] is True
    assert "discard newer local runtime state" in "\n".join(report["warnings"])


def test_plan_restore_newer_than_code_source_is_blocked(tmp_path):
    latest = runtime_preflight._latest_migration_version(REPO_ROOT)
    fake_home = tmp_path / "home"
    state_dir = fake_home / ".dream-studio" / "state"
    _schema_db(state_dir / "studio.db", latest)
    source = _schema_db(state_dir / "studio-newer.db.bak", latest + 3)

    report = runtime_recovery.run_restore_plan_preview(
        source=source,
        config=runtime_recovery.RecoveryConfig(repo_root=REPO_ROOT, home=fake_home),
    )

    assert report["overall"] == "blocked"
    assert report["source"]["status"] == "blocked_newer_than_code"
    assert report["compatibility_impact"]["source_compatible_with_checkout"] is False
    assert report["compatibility_impact"]["restore_would_still_be_blocked"] is True
    assert "newer than this checkout" in "\n".join(report["errors"] + report["warnings"])


def test_plan_restore_compatible_source_outputs_complete_future_plan(tmp_path):
    latest = runtime_preflight._latest_migration_version(REPO_ROOT)
    fake_home = tmp_path / "home"
    state_dir = fake_home / ".dream-studio" / "state"
    current = _schema_db(state_dir / "studio.db", latest)
    source = _schema_db(state_dir / "studio.db.bak", latest)

    report = runtime_recovery.run_restore_plan_preview(
        source=source,
        config=runtime_recovery.RecoveryConfig(repo_root=REPO_ROOT, home=fake_home),
    )

    plan = report["future_mutation_plan"]
    safety_path = Path(plan["pre_restore_safety_copy_path"])
    current_hash = _sha256(current)
    source_hash = _sha256(source)

    assert report["overall"] == "ok"
    assert report["schema_relation"] == "source_equal_to_current"
    assert plan["will_execute"] is False
    assert plan["requires_explicit_future_command"] is True
    assert str(current) in plan["would_read"]
    assert str(source) in plan["would_read"]
    assert str(current) in plan["would_write"]
    assert str(safety_path) in plan["would_write"]
    assert safety_path.name == f"studio.db.pre-restore.{current_hash[:12].lower()}.bak"
    assert {step["action"] for step in plan["steps"]} >= {
        "create_pre_restore_safety_copy",
        "verify_safety_copy_hash",
        "copy_source_backup_to_runtime_db",
        "verify_restored_db_hash_and_schema",
        "run_read_only_preflight",
    }
    assert report["read_only_proof"]["current_db"]["sha256_before"] == current_hash
    assert report["read_only_proof"]["source_backup"]["sha256_before"] == source_hash


def test_plan_restore_does_not_mutate_current_db_or_source_backup(tmp_path):
    latest = runtime_preflight._latest_migration_version(REPO_ROOT)
    fake_home = tmp_path / "home"
    state_dir = fake_home / ".dream-studio" / "state"
    files = [
        _schema_db(state_dir / "studio.db", latest + 2),
        _schema_db(state_dir / "source.db.bak", latest - 1),
    ]
    before = {path: (_sha256(path), path.stat().st_mtime_ns) for path in files}

    report = runtime_recovery.run_restore_plan_preview(
        source=files[1],
        config=runtime_recovery.RecoveryConfig(repo_root=REPO_ROOT, home=fake_home),
    )

    after = {path: (_sha256(path), path.stat().st_mtime_ns) for path in files}
    assert after == before
    assert report["read_only_proof"]["current_db"]["unchanged"] is True
    assert report["read_only_proof"]["source_backup"]["unchanged"] is True
    assert report["mutations_performed"] is False
    assert not Path(report["future_mutation_plan"]["pre_restore_safety_copy_path"]).exists()


def test_plan_restore_without_current_db_does_not_create_fake_runtime_dir(tmp_path):
    latest = runtime_preflight._latest_migration_version(REPO_ROOT)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    source = _schema_db(tmp_path / "external-source.db.bak", latest)

    report = runtime_recovery.run_restore_plan_preview(
        source=source,
        config=runtime_recovery.RecoveryConfig(repo_root=REPO_ROOT, home=fake_home),
    )

    assert report["current"]["status"] == "missing"
    assert report["schema_relation"] == "no_current_db"
    assert report["future_mutation_plan"]["pre_restore_safety_copy_path"] is None
    assert "skip_safety_copy_no_current_db" in {
        step["action"] for step in report["future_mutation_plan"]["steps"]
    }
    assert not (fake_home / ".dream-studio").exists()


def test_recovery_module_has_no_external_process_or_provider_calls():
    source = (REPO_ROOT / "interfaces" / "cli" / "runtime_recovery.py").read_text(encoding="utf-8")

    assert "subprocess" not in source
    assert "shutil" not in source
    assert "_rclone_run" not in source
    assert "get_connection(" not in source
    assert "paths.state_dir(" not in source
    assert "restore(" not in source
    assert "backup(" not in source
