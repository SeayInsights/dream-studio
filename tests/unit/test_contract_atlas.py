from __future__ import annotations

import json
from pathlib import Path

from core.event_store.studio_db import _connect
from core.shared_intelligence.adapter_alignment import register_default_adapter_authority_profiles
from core.shared_intelligence.adapter_config_projection import adapter_config_projection_report
from core.shared_intelligence.contract_atlas import (
    build_contract_atlas,
    validate_contract_atlas,
)


def test_contract_atlas_explains_layers_modules_interfaces_and_boundaries(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "home"
    repo_root = tmp_path / "repo"
    _write_current_hook_surfaces(home)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    with _connect(_db(tmp_path)) as conn:
        register_default_adapter_authority_profiles(conn)
        projection_report = adapter_config_projection_report(conn, project_id="dream-studio")
        _write_projection_files(repo_root, projection_report)

        atlas = build_contract_atlas(
            conn,
            repo_root=repo_root,
            project_id="dream-studio",
        )

    assert validate_contract_atlas(atlas) == []
    assert atlas["schema"] == "dream_studio.contract_atlas.v1"
    assert atlas["private_by_default"] is True
    assert atlas["derived_view"] is True
    assert atlas["primary_authority"] is False
    assert atlas["execution_authorized"] is False
    assert atlas["whole_system_contract"]["contract_id"] == "dream-studio-system"
    assert atlas["contract_registry"]["domain_count"] >= 6
    assert atlas["docs_freshness_tracking"]["rewrite_every_doc_required"] is False
    assert atlas["current_maturity_ledger"]["area_count"] >= 20
    assert atlas["current_maturity_ledger"]["status_counts"]["runtime_validated"] >= 8
    assert {layer["layer_id"] for layer in atlas["layer_contracts"]} >= {
        "repo_source",
        "sqlite_authority",
        "dashboard_api",
        "adapter_projection",
        "runtime_profiles",
    }
    assert {module["module_id"] for module in atlas["module_contracts"]} >= {
        "security_analytics",
        "token_analytics",
        "route_milestone_analytics",
    }
    assert {contract["interface_id"] for contract in atlas["interface_contracts"]} >= {
        "telemetry_api",
        "shared_intelligence_api",
        "hook_launcher",
    }
    assert atlas["analytics_only_profile"]["writes_authorized"] is False
    assert atlas["security_lifecycle_gate"]["source_framework"]["source_control_count"] == 47
    assert atlas["security_lifecycle_gate"]["full_review_required"] is True
    assert atlas["production_readiness_control_catalog"]["control_count"] > 47
    assert atlas["secure_production_readiness_gate"]["workflow_id"] == (
        "production_readiness_workflow"
    )
    assert atlas["installed_runtime_model"]["source_state_separation"] is True
    assert atlas["installed_module_profiles"]["profile_count"] == 8
    assert atlas["boundary_violation_report"]["status"] == "pass"
    assert any(
        item["area"] == "current_maturity_ledger" and item["status"] == "validated"
        for item in atlas["maturity_scorecard"]
    )
    assert any(
        item["area"] == "security_lifecycle_gate"
        and item["canonical_framework"] == "47_enterprise_security_controls"
        for item in atlas["maturity_scorecard"]
    )
    assert any(
        item["area"] == "secure_production_readiness_gate"
        and item["workflow_id"] == "production_readiness_workflow"
        for item in atlas["maturity_scorecard"]
    )
    assert atlas["active_adapter_execution_validation"]["live_claude_execution_proven"] is False
    assert atlas["active_adapter_execution_validation"]["live_codex_execution_proven"] is False
    assert (
        atlas["active_adapter_execution_validation"]["staleness_status"]["repair_candidate_count"]
        == 0
    )


def test_contract_atlas_dependency_graph_uses_confirmed_edges_only(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "home"
    repo_root = tmp_path / "repo"
    _write_current_hook_surfaces(home)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    with _connect(_db(tmp_path)) as conn:
        register_default_adapter_authority_profiles(conn)
        projection_report = adapter_config_projection_report(conn, project_id="dream-studio")
        _write_projection_files(repo_root, projection_report)

        atlas = build_contract_atlas(conn, repo_root=repo_root, project_id="dream-studio")

    graph = atlas["confirmed_dependency_graph"]
    assert graph["inferred_edges_included"] is False
    assert graph["unverified_edges_included"] is False
    assert graph["nodes"]
    assert graph["edges"]
    assert all(edge["edge_status"] == "confirmed" for edge in graph["edges"])
    assert any(
        edge["source"] == "module:security_analytics"
        and edge["relation"] == "reads_source_table"
        and edge["target"] == "table:security_findings"
        for edge in graph["edges"]
    )
    assert any(
        edge["source"] == "adapter:codex"
        and edge["target"] == "projection:adapter-projections/codex/AGENTS.md"
        for edge in graph["edges"]
    )
    assert any(
        edge["source"] == "module:security_lifecycle_gate"
        and edge["target"] == "contract:47_enterprise_security_controls"
        for edge in graph["edges"]
    )
    assert any(
        edge["source"] == "module:production_readiness_workflow"
        and edge["target"] == "contract:secure_production_readiness_gate"
        for edge in graph["edges"]
    )


def test_contract_atlas_defaults_to_dream_studio_scope(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    repo_root = tmp_path / "repo"
    _write_current_hook_surfaces(home)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    with _connect(_db(tmp_path)) as conn:
        register_default_adapter_authority_profiles(conn)
        projection_report = adapter_config_projection_report(conn, project_id="dream-studio")
        _write_projection_files(repo_root, projection_report)

        atlas = build_contract_atlas(conn, repo_root=repo_root)

    assert atlas["project_id"] == "dream-studio"
    assert atlas["boundary_violation_report"]["status"] == "pass"
    assert (
        atlas["active_adapter_execution_validation"]["staleness_status"]["repair_candidate_count"]
        == 0
    )


def test_contract_atlas_public_export_is_sanitized(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    repo_root = tmp_path / "repo"
    _write_current_hook_surfaces(home)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    with _connect(_db(tmp_path)) as conn:
        register_default_adapter_authority_profiles(conn)
        projection_report = adapter_config_projection_report(conn, project_id="dream-studio")
        _write_projection_files(repo_root, projection_report)

        atlas = build_contract_atlas(
            conn,
            repo_root=repo_root,
            project_id="dream-studio",
            export_scope="public",
        )

    payload = json.dumps(atlas, sort_keys=True)
    assert validate_contract_atlas(atlas) == []
    assert atlas["export_scope"] == "public"
    assert atlas["sanitized_public_export"] is True
    assert str(tmp_path) not in payload
    assert all(
        "local_user_surface" not in contract for contract in atlas["adapter_projection_contracts"]
    )
    hook_surfaces = [
        contract.get("local_hook_surface")
        for contract in atlas["adapter_projection_contracts"]
        if contract.get("local_hook_surface") is not None
    ]
    assert hook_surfaces
    assert all(surface.get("secret_contents_read") is False for surface in hook_surfaces)


def _db(tmp_path: Path) -> Path:
    return tmp_path / "contract-atlas" / "studio.db"


def _write_projection_files(repo_root: Path, projection_report: dict) -> None:
    for projection in projection_report["projections"]:
        _write(repo_root / projection["projection_path"], projection["content"])
    _write(
        repo_root / "AGENTS.md",
        "Dream Studio SQLite authority projection for Codex.\n"
        "adapter-projections/codex/AGENTS.md\n",
    )
    _write(
        repo_root / "CLAUDE.md",
        "Dream Studio SQLite authority projection for Claude.\n"
        "adapter-projections/claude/CLAUDE.md\n",
    )


def _write_current_hook_surfaces(home: Path) -> None:
    _write(
        home / ".claude" / "settings.json",
        """
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \\"C:/Users/Example/builds/dream-studio/hooks/run.py\\" on-prompt-dispatch"
          }
        ]
      }
    ]
  }
}
""".lstrip(),
    )
    _write(
        home / ".codex" / "hooks.json",
        """
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\\"C:/Users/Example/builds/dream-studio/hooks/run.cmd\\" on-prompt-dispatch"
          }
        ]
      }
    ]
  }
}
""".lstrip(),
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
