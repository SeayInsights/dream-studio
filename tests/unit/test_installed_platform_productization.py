from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

from core.config.sqlite_bootstrap import bootstrap_database
from core.installed_productization import (
    backup_runtime,
    detect_legacy_install,
    final_installed_modular_platform_closeout,
    first_run_setup,
    install_global_command_surface,
    migrate_legacy_install,
    productization_acceptance_report,
    repair_adapter_surfaces,
    rollback_runtime_check,
    restore_runtime_check,
    uninstall_runtime_check,
    update_runtime_check,
)
from core.module_profiles import module_profile_map
from core.release.local_dogfood_stability import REQUIRED_MULTISESSION_CYCLES

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_first_run_setup_bootstraps_fresh_analytics_only_home(tmp_path: Path) -> None:
    home = tmp_path / "fresh-home"
    assert not home.exists()

    result = first_run_setup(
        source_root=REPO_ROOT,
        dream_studio_home=home,
        profiles=["analytics_only"],
        rehearsal=True,
    )

    analytics = module_profile_map()["analytics_only"]
    assert result["fresh_state_created"] is True
    assert result["live_state_mutated"] is False
    assert Path(result["sqlite_path"]).is_file()
    assert Path(result["config_path"]).is_file()
    assert result["selected_profiles"] == ["analytics_only"]
    assert result["profile_status"]["selected"][0]["profile_id"] == "analytics_only"
    assert {item["profile_id"] for item in result["profile_status"]["unselected"]} >= {
        "core",
        "security_only",
        "full",
    }
    assert analytics["hooks_required"] is False
    assert analytics["agents_required"] is False
    assert analytics["workflows_required"] is False
    assert analytics["claude_required"] is False
    assert analytics["codex_required"] is False
    assert analytics["docker_required"] is False
    assert result["dashboard_onboarding"]["dashboard_enabled"] is True
    assert result["adapter_setup"]["unsupported_tools_fallback"] == "context_packet_only"


def test_security_only_and_full_profiles_install_independently(tmp_path: Path) -> None:
    security_home = tmp_path / "security-home"
    full_home = tmp_path / "full-home"

    security = first_run_setup(
        source_root=REPO_ROOT,
        dream_studio_home=security_home,
        profiles=["security_only"],
        rehearsal=True,
    )
    full = first_run_setup(
        source_root=REPO_ROOT,
        dream_studio_home=full_home,
        profiles=["full"],
        rehearsal=True,
    )

    assert security["selected_profiles"] == ["security_only"]
    assert Path(security["sqlite_path"]).is_file()
    assert module_profile_map()["security_only"]["docker_required"] is False
    assert module_profile_map()["security_only"]["claude_required"] is False
    assert module_profile_map()["security_only"]["codex_required"] is False
    assert security["dashboard_onboarding"]["dashboard_enabled"] is False
    assert full["selected_profiles"] == ["full"]
    assert full["dashboard_onboarding"]["dashboard_enabled"] is True
    assert full["adapter_setup"]["status"] == "available"


def test_backup_restore_update_uninstall_checks_are_non_destructive(tmp_path: Path) -> None:
    home = tmp_path / "runtime-home"
    first_run_setup(
        source_root=REPO_ROOT,
        dream_studio_home=home,
        profiles=["core", "full"],
        rehearsal=True,
    )

    backup = backup_runtime(source_root=REPO_ROOT, dream_studio_home=home, execute=True)
    restore = restore_runtime_check(
        source_root=REPO_ROOT,
        dream_studio_home=home,
        backup_path=backup["backup_path"],
    )
    update = update_runtime_check(source_root=REPO_ROOT, dream_studio_home=home)
    uninstall = uninstall_runtime_check(source_root=REPO_ROOT, dream_studio_home=home)

    assert backup["status"] == "created"
    assert backup["destructive"] is False
    assert backup["live_state_mutation"] is False
    assert restore["restore_ready"] is True
    assert restore["restore_executed"] is False
    assert update["update_ready"] is True
    assert update["live_state_mutated"] is False
    assert uninstall["uninstall_executed"] is False
    assert uninstall["delete_authorized"] is False


def test_productization_acceptance_report_covers_required_profiles(tmp_path: Path) -> None:
    home = tmp_path / "acceptance-home"

    report = productization_acceptance_report(
        source_root=REPO_ROOT,
        dream_studio_home=home,
        profiles=["core", "analytics_only", "security_only", "full"],
    )

    assert report["status"] == "pass"
    assert report["live_state_mutated"] is False
    assert all(report["checks"].values())
    assert report["setup"]["contract_atlas"]["status"] == "available"


def test_productization_ds_commands_run_from_outside_repo(tmp_path: Path) -> None:
    home = tmp_path / "cli-home"
    acceptance_home = tmp_path / "acceptance-home"
    outside = tmp_path / "outside"
    outside.mkdir()
    ds = REPO_ROOT / "interfaces" / "cli" / "ds.py"

    install = _run_ds(
        ds,
        outside,
        "--source-root",
        str(REPO_ROOT),
        "--home",
        str(home),
        "install",
        "--rehearsal",
        "--profile",
        "analytics_only",
    )
    validate = _run_ds(
        ds, outside, "--source-root", str(REPO_ROOT), "--home", str(home), "validate"
    )
    adapters = _run_ds(
        ds, outside, "--source-root", str(REPO_ROOT), "--home", str(home), "adapters"
    )
    acceptance = _run_ds(
        ds,
        outside,
        "--source-root",
        str(REPO_ROOT),
        "--home",
        str(acceptance_home),
        "acceptance",
        "--profile",
        "analytics_only",
        "--profile",
        "security_only",
        "--profile",
        "full",
    )

    assert install["selected_profiles"] == ["analytics_only"]
    assert install["live_state_mutated"] is False
    assert validate["ready"] is True
    assert adapters["execution_authorized"] is False
    assert acceptance["status"] == "pass"


def test_legacy_install_detection_and_dry_run_are_non_destructive(tmp_path: Path) -> None:
    old_source = tmp_path / "old-dream-studio"
    old_source.mkdir()
    home = tmp_path / ".dream-studio"
    command_dir = tmp_path / "bin"
    claude_settings = tmp_path / ".claude" / "settings.json"
    first_run_setup(
        source_root=old_source,
        dream_studio_home=home,
        profiles=["core"],
        rehearsal=False,
    )
    (home / "meta" / "handoffs").mkdir(parents=True)
    (home / "meta" / "handoffs" / "legacy.md").write_text("legacy", encoding="utf-8")
    install_global_command_surface(
        source_root=old_source,
        dream_studio_home=home,
        command_dir=command_dir,
        execute=True,
    )
    claude_settings.parent.mkdir(parents=True)
    claude_settings.write_text(
        json.dumps(
            {
                "hooks": {
                    "PostToolUse": [
                        {
                            "hooks": [
                                {
                                    "command": (
                                        f"python {old_source / 'runtime' / 'hooks' / 'dream-studio.py'}"
                                    )
                                }
                            ]
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    detection = detect_legacy_install(
        source_root=REPO_ROOT,
        dream_studio_home=home,
        command_dir=command_dir,
        claude_settings_path=claude_settings,
    )
    dry_run = migrate_legacy_install(
        source_root=REPO_ROOT,
        dream_studio_home=home,
        backup_root=tmp_path / "legacy-backups",
        command_dir=command_dir,
        claude_settings_path=claude_settings,
        execute=False,
    )

    assert detection["status"] == "legacy_detected"
    assert detection["old_source_checkout_detected"] is True
    assert detection["old_file_sprawl_detected"] is True
    assert detection["launcher_paths"]["stale_launcher_count"] == 2
    assert detection["adapter_config_paths"]["stale_adapter_config_count"] == 1
    assert dry_run["status"] == "dry_run"
    assert dry_run["strategy"]["copy_legacy_file_sprawl_forward"] is False
    assert dry_run["strategy"]["merge_unrelated_git_histories"] is False
    assert (home / "meta" / "handoffs" / "legacy.md").exists()


def test_legacy_migration_creates_fresh_home_migrates_sqlite_and_keeps_rollback(
    tmp_path: Path,
) -> None:
    old_source = tmp_path / "old-dream-studio"
    old_source.mkdir()
    home = tmp_path / ".dream-studio"
    backup_root = tmp_path / "legacy-backups"
    command_dir = tmp_path / "bin"
    claude_settings = tmp_path / ".claude" / "settings.json"
    (home / "config").mkdir(parents=True)
    (home / "state").mkdir(parents=True)
    (home / "config" / "runtime.json").write_text(
        json.dumps(
            {
                "source_root": str(old_source),
                "dream_studio_home": str(home),
                "module_profiles": ["core"],
            }
        ),
        encoding="utf-8",
    )
    bootstrap_database(home / "state" / "studio.db")
    with _sqlite(home / "state" / "studio.db") as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO decision_records(
                decision_id, project_id, decision_type, decision_status,
                selected_option, source_refs_json, evidence_refs_json
            ) VALUES (?, ?, ?, ?, ?, '[]', '[]')
            """,
            ("legacy-decision-1", "dream-studio", "operator_decision", "approved", "upgrade"),
        )
        conn.commit()
    (home / "reports").mkdir()
    (home / "reports" / "old-report.md").write_text("do not copy", encoding="utf-8")
    install_global_command_surface(
        source_root=old_source,
        dream_studio_home=home,
        command_dir=command_dir,
        execute=True,
    )
    claude_settings.parent.mkdir(parents=True)
    claude_settings.write_text(
        json.dumps(
            {
                "hooks": {
                    "PostToolUse": [
                        {
                            "hooks": [
                                {
                                    "command": (
                                        f"python {old_source / 'hooks' / 'run.py'} dream-studio"
                                    )
                                }
                            ]
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    result = migrate_legacy_install(
        source_root=REPO_ROOT,
        dream_studio_home=home,
        backup_root=backup_root,
        command_dir=command_dir,
        claude_settings_path=claude_settings,
        execute=True,
    )

    assert result["status"] == "migrated"
    assert result["backup_verified"] is True
    assert result["old_file_sprawl_copied_forward"] is False
    assert not (home / "reports" / "old-report.md").exists()
    assert Path(result["backup_runtime_path"], "reports", "old-report.md").exists()
    with _sqlite(home / "state" / "studio.db") as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM decision_records WHERE decision_id = ?",
            ("legacy-decision-1",),
        ).fetchone()[0]
    assert count == 1
    assert str(REPO_ROOT) in (command_dir / "ds.cmd").read_text(encoding="utf-8")
    settings = json.loads(claude_settings.read_text(encoding="utf-8"))
    repaired_command = settings["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
    assert str(REPO_ROOT) in repaired_command
    rollback = rollback_runtime_check(backup_path=result["backup_path"])
    assert rollback["rollback_ready"] is True
    assert rollback["sqlite_backup_opens_read_only"] is True


def test_repair_adapters_can_refresh_launchers_without_hook_execution(tmp_path: Path) -> None:
    old_source = tmp_path / "old-dream-studio"
    old_source.mkdir()
    home = tmp_path / ".dream-studio"
    command_dir = tmp_path / "bin"
    first_run_setup(
        source_root=old_source,
        dream_studio_home=home,
        profiles=["core"],
        rehearsal=False,
    )
    install_global_command_surface(
        source_root=old_source,
        dream_studio_home=home,
        command_dir=command_dir,
        execute=True,
    )

    planned = repair_adapter_surfaces(
        source_root=REPO_ROOT,
        dream_studio_home=home,
        command_dir=command_dir,
        previous_source_root=old_source,
        execute=False,
    )
    repaired = repair_adapter_surfaces(
        source_root=REPO_ROOT,
        dream_studio_home=home,
        command_dir=command_dir,
        previous_source_root=old_source,
        execute=True,
    )

    assert planned["status"] == "planned"
    assert planned["secret_values_read"] is False
    assert repaired["status"] == "repaired"
    assert repaired["launchers_repaired"] == 2
    assert str(REPO_ROOT) in (command_dir / "ds.ps1").read_text(encoding="utf-8")


def test_windows_ds_launcher_runs_from_outside_repo(tmp_path: Path) -> None:
    home = tmp_path / "launcher-home"
    outside = tmp_path / "outside"
    outside.mkdir()
    launcher = REPO_ROOT / "ds.ps1"

    install = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(launcher),
            "--home",
            str(home),
            "install",
            "--rehearsal",
            "--profile",
            "analytics_only",
        ],
        cwd=outside,
        capture_output=True,
        text=True,
        check=True,
    )
    status = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(launcher),
            "--home",
            str(home),
            "status",
        ],
        cwd=outside,
        capture_output=True,
        text=True,
        check=True,
    )

    install_payload = json.loads(install.stdout)
    status_payload = json.loads(status.stdout)
    assert install_payload["selected_profiles"] == ["analytics_only"]
    assert status_payload["source_build_location"] == str(REPO_ROOT)
    assert status_payload["user_local_state_location"] == str(home.resolve())


def test_repo_cmd_launcher_exposes_plain_ds_surface() -> None:
    launcher = REPO_ROOT / "ds.cmd"
    text = launcher.read_text(encoding="utf-8")

    assert launcher.is_file()
    assert "interfaces\\cli\\ds.py" in text
    assert "--source-root" in text
    assert "%*" in text


def test_global_command_surface_installs_plain_ds_launcher(tmp_path: Path) -> None:
    home = tmp_path / "launcher-home"
    command_dir = tmp_path / "bin"
    outside = tmp_path / "outside"
    outside.mkdir()

    install = install_global_command_surface(
        source_root=REPO_ROOT,
        dream_studio_home=home,
        command_dir=command_dir,
        execute=True,
    )

    assert install["destructive"] is False
    assert install["sqlite_mutation"] is False
    assert (command_dir / "ds.cmd").is_file()
    assert (command_dir / "ds.ps1").is_file()

    if sys.platform == "win32":
        env = os.environ.copy()
        env["PATH"] = f"{command_dir};{Path(sys.executable).parent};{env.get('PATH', '')}"
        install_payload = subprocess.run(
            [
                "cmd.exe",
                "/c",
                "ds",
                "install",
                "--rehearsal",
                "--profile",
                "analytics_only",
            ],
            cwd=outside,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        status_payload = subprocess.run(
            ["cmd.exe", "/c", "ds", "status"],
            cwd=outside,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        assert json.loads(install_payload.stdout)["selected_profiles"] == ["analytics_only"]
        assert json.loads(status_payload.stdout)["user_local_state_location"] == str(home.resolve())


def test_final_installed_modular_platform_closeout_routes_to_operator_decision(
    tmp_path: Path,
) -> None:
    home = tmp_path / "closeout-home"
    first_run_setup(
        source_root=REPO_ROOT,
        dream_studio_home=home,
        profiles=["core", "analytics_only", "security_only", "full"],
        rehearsal=True,
    )
    evidence = {
        "sqlite_hash_before": "hash",
        "sqlite_hash_after": "hash",
        "long_run_cycles": [
            {
                "cycle_id": cycle_id,
                "status": "pass",
                "evidence_refs": [f"evidence/{cycle_id}.json"],
            }
            for cycle_id in REQUIRED_MULTISESSION_CYCLES
        ],
        "release_gate_passed": True,
        "black_passed": True,
        "lint_baseline_passed": True,
        "docs_drift_passed": True,
        "pip_audit_passed": True,
        "live_sqlite_guard_passed": True,
        "repo_clean": True,
        "private_artifacts_tracked": False,
        "adapter_status_documented": True,
        "context_packet_fallback_documented": True,
        "publication_boundary_clean": True,
        "readme_current": True,
        "prd_current": True,
        "contract_atlas_current": True,
        "sanitized_public_export_current": True,
        "apache_2_license_consistent": True,
    }

    closeout = final_installed_modular_platform_closeout(
        source_root=REPO_ROOT,
        dream_studio_home=home,
        validation_evidence=evidence,
    )

    assert closeout["status"] == "pass"
    assert closeout["ready_for_broader_local_use"] is True
    assert closeout["ready_for_public_release"] is False
    assert (
        closeout["route_decision"]
        == "operator_decision_on_public_release_private_dogfood_or_external_project_use"
    )
    assert (
        closeout["verdict"] == "FINAL_INSTALLED_MODULAR_PLATFORM_PRODUCTIZATION_CLOSEOUT_COMPLETE"
    )


def _run_ds(ds: Path, cwd: Path, *args: str) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, str(ds), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


@contextmanager
def _sqlite(path: Path):
    import sqlite3

    conn = sqlite3.connect(path)
    try:
        yield conn
    finally:
        conn.close()
