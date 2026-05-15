from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from core.installed_productization import (
    backup_runtime,
    first_run_setup,
    productization_acceptance_report,
    restore_runtime_check,
    uninstall_runtime_check,
    update_runtime_check,
)
from core.module_profiles import module_profile_map

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


def _run_ds(ds: Path, cwd: Path, *args: str) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, str(ds), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)
