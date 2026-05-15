from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from core.config.database import DB_PATH_ENV, DatabaseRuntime
from core.event_store.studio_db import _connect
from core.installed_runtime import (
    adapter_access_mode_summary,
    adapter_router_status,
    bootstrap_rehearsal_runtime,
    installed_runtime_model,
)
from core.module_profiles import module_profile_map, module_profiles, validate_module_profiles
from core.shared_intelligence.adapter_alignment import register_default_adapter_authority_profiles
from projections.api.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_installed_runtime_model_separates_source_state_and_router_paths(tmp_path: Path) -> None:
    home = tmp_path / "dream-home"

    model = installed_runtime_model(source_root=REPO_ROOT, dream_studio_home=home)

    assert model["source_build_location"] == str(REPO_ROOT)
    assert model["user_local_state_location"] == str(home.resolve())
    assert model["canonical_sqlite_path"].endswith(".dream-studio") is False
    assert model["adapter_runtime_path"].endswith("adapters")
    assert model["router_api_service"]["api_routes"] == ["/api/shared-intelligence/adapter-router"]
    assert model["source_state_separation"] is True
    assert model["live_db_write_authorized"] is False
    assert "ds install" in model["global_command_surface"]
    assert "ds router" in model["global_command_surface"]
    assert model["productization_surface"]["acceptance_tests"] == "ds acceptance"


def test_module_profiles_are_independent_and_analytics_only_is_minimal() -> None:
    profiles = module_profiles()
    by_id = module_profile_map()

    assert validate_module_profiles() == []
    assert profiles["profile_count"] == 10
    career = by_id["career_ops_only"]
    assert career["hooks_required"] is False
    assert career["docker_required"] is False
    assert "public_exports" in career["excludes"]
    analytics = by_id["analytics_only"]
    assert analytics["hooks_required"] is False
    assert analytics["agents_required"] is False
    assert analytics["workflows_required"] is False
    assert analytics["claude_required"] is False
    assert analytics["codex_required"] is False
    assert analytics["docker_required"] is False
    assert "repo_mutation" in analytics["excludes"]
    assert "ds analytics-ingest" in analytics["exposed_commands"]
    assert analytics["hooks_are_optional_producers"] is True
    token = by_id["token_only"]
    assert token["docker_required"] is False
    assert "fake_cost_estimation" in token["excludes"]
    assert "ds modules" in by_id["core"]["exposed_commands"]


def test_adapter_router_status_exposes_capabilities_without_execution(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_active_surfaces(repo)
    db_path = tmp_path / "router" / "studio.db"
    with _connect(db_path) as conn:
        register_default_adapter_authority_profiles(conn)
        _write_projection_files(repo, conn)
        conn.commit()

        status = adapter_router_status(conn, source_root=repo, dream_studio_home=tmp_path / "home")

    assert status["model_name"] == "dream_studio_installed_adapter_router"
    assert status["execution_authorized"] is False
    assert status["db_write_authorized"] is False
    assert status["adapter_health"]["adapter_count"] == 8
    assert status["adapter_projection_summary"]["config_write_authorized"] is False
    assert set(status["capabilities"]) >= {
        "current_route_state",
        "context_packet_generation",
        "adapter_result_normalization",
        "contract_atlas_queries",
        "module_profile_status",
    }
    assert status["adapter_access_modes"]["unsupported_overclaiming_prevented"] is True


def test_adapter_access_modes_classify_proven_and_unproven_surfaces() -> None:
    summary = adapter_access_mode_summary()
    statuses = {(row["adapter_id"], row["surface"]): row["status"] for row in summary["adapters"]}

    assert statuses[("codex", "Codex CLI")] == "live_consumption_proven"
    assert statuses[("codex", "Codex app configured environment")] == "live_consumption_proven"
    assert statuses[("claude", "Claude Code CLI")] == "live_consumption_proven"
    assert (
        statuses[("claude", "Claude Code app/workspace")]
        == "live_consumption_proven_with_workspace_head_check"
    )
    assert statuses[("codex-cloud", "Codex cloud/GitHub environment")] == (
        "not_proven_in_local_runtime"
    )


def test_rehearsal_install_bootstraps_temp_home_without_live_state(tmp_path: Path) -> None:
    rehearsal_home = tmp_path / "rehearsal-home"

    result = bootstrap_rehearsal_runtime(source_root=REPO_ROOT, dream_studio_home=rehearsal_home)

    assert result["fresh_state_created"] is True
    assert result["sqlite_bootstrap"] is True
    assert result["live_state_mutated"] is False
    assert Path(result["sqlite_path"]).is_file()
    assert Path(result["config_path"]).is_file()
    assert result["context_packet_generated"] == "rehearsal-codex-resume"


def test_ds_commands_run_from_outside_repo_against_rehearsal_home(tmp_path: Path) -> None:
    rehearsal_home = tmp_path / "rehearsal-home"
    outside = tmp_path / "outside"
    outside.mkdir()
    ds = REPO_ROOT / "interfaces" / "cli" / "ds.py"

    bootstrap = subprocess.run(
        [
            sys.executable,
            str(ds),
            "--source-root",
            str(REPO_ROOT),
            "rehearsal-install",
            "--rehearsal-home",
            str(rehearsal_home),
        ],
        cwd=outside,
        capture_output=True,
        text=True,
        check=True,
    )
    status = subprocess.run(
        [
            sys.executable,
            str(ds),
            "--source-root",
            str(REPO_ROOT),
            "--home",
            str(rehearsal_home),
            "router",
        ],
        cwd=outside,
        capture_output=True,
        text=True,
        check=True,
    )
    packet = subprocess.run(
        [
            sys.executable,
            str(ds),
            "--source-root",
            str(REPO_ROOT),
            "--home",
            str(rehearsal_home),
            "context-packet",
            "--adapter",
            "codex",
            "--surface",
            "resume",
        ],
        cwd=outside,
        capture_output=True,
        text=True,
        check=True,
    )

    bootstrap_payload = json.loads(bootstrap.stdout)
    status_payload = json.loads(status.stdout)
    packet_payload = json.loads(packet.stdout)
    assert bootstrap_payload["dream_studio_home"] == str(rehearsal_home.resolve())
    assert status_payload["runtime_model"]["source_build_location"] == str(REPO_ROOT)
    assert status_payload["runtime_model"]["user_local_state_location"] == str(
        rehearsal_home.resolve()
    )
    assert status_payload["execution_authorized"] is False
    assert packet_payload["packet_id"] == "dry-run-codex-resume"


def test_ds_router_refuses_missing_state_without_bootstrap(tmp_path: Path) -> None:
    missing_home = tmp_path / "missing-home"
    outside = tmp_path / "outside"
    outside.mkdir()
    ds = REPO_ROOT / "interfaces" / "cli" / "ds.py"

    result = subprocess.run(
        [
            sys.executable,
            str(ds),
            "--source-root",
            str(REPO_ROOT),
            "--home",
            str(missing_home),
            "router",
        ],
        cwd=outside,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stderr)
    assert result.returncode == 1
    assert "SQLite authority is missing" in payload["error"]
    assert not (missing_home / "state" / "studio.db").exists()


def test_actual_app_exposes_installed_adapter_router(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    db_path = tmp_path / "routes" / "studio.db"
    with _connect(db_path) as conn:
        register_default_adapter_authority_profiles(conn)
        conn.commit()
    DatabaseRuntime.reset_instance()
    monkeypatch.setenv(DB_PATH_ENV, str(db_path))

    response = TestClient(app).get(
        "/api/shared-intelligence/adapter-router",
        params={"project_id": "dream-studio"},
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["model_name"] == "dream_studio_installed_adapter_router"
    assert payload["execution_authorized"] is False
    assert payload["dashboard_consumable"] is True
    assert payload["adapter_access_modes"]["unsupported_overclaiming_prevented"] is True


def _write_active_surfaces(repo: Path) -> None:
    (repo / "AGENTS.md").parent.mkdir(parents=True, exist_ok=True)
    (repo / "AGENTS.md").write_text(
        "Dream Studio SQLite projection adapter-projections/codex/AGENTS.md\n",
        encoding="utf-8",
    )
    (repo / "CLAUDE.md").write_text(
        "Dream Studio SQLite projection adapter-projections/claude/CLAUDE.md\n",
        encoding="utf-8",
    )


def _write_projection_files(repo: Path, conn) -> None:
    from core.shared_intelligence.adapter_config_projection import adapter_config_projection_report

    report = adapter_config_projection_report(conn, project_id="dream-studio")
    for projection in report["projections"]:
        path = repo / projection["projection_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(projection["content"], encoding="utf-8")
