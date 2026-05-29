from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from core.event_store.studio_db import _connect
from core.shared_intelligence.adapter_alignment import register_default_adapter_authority_profiles
from core.shared_intelligence.adapter_config_projection import adapter_config_projection_report
from core.shared_intelligence.contract_atlas_lifecycle import (
    FRESHNESS_MANIFEST_FILENAME,
    PRIVATE_INTERNAL_EXPORT_FILENAME,
    PUBLIC_SANITIZED_EXPORT_FILENAME,
    build_contract_atlas_freshness_manifest,
    refresh_contract_atlas_exports,
    validate_contract_atlas_lifecycle_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_contract_atlas_lifecycle_manifest_validates_refresh_docs_and_leakage(
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
        manifest = build_contract_atlas_freshness_manifest(
            conn,
            repo_root=repo_root,
            project_id="dream-studio",
            changed_files=[
                "core/shared_intelligence/contract_atlas.py",
                "docs/architecture/contract-atlas.md",
                "docs/README.md",
                "docs/operations/lint-format-baseline-policy.md",
            ],
        )

    assert validate_contract_atlas_lifecycle_manifest(manifest) == []
    assert manifest["schema"] == "dream_studio.contract_atlas_lifecycle.v1"
    assert manifest["status"] == "pass"
    assert manifest["db_write_authorized"] is False
    assert manifest["private_internal_refresh"]["status"] == "pass"
    assert manifest["public_sanitized_export_refresh"]["status"] == "pass"
    assert manifest["public_private_data_leakage_check"]["status"] == "pass"
    assert manifest["docs_prd_readme_impact"]["impacted_domain_count"] == 1
    assert manifest["docs_prd_readme_impact"]["docs_update_required_domains"] == []
    assert (
        "/api/shared-intelligence/contract-atlas/freshness"
        in manifest["dashboard_api_freshness_status"]["routes"]
    )


def test_contract_atlas_lifecycle_manifest_flags_missing_prd_or_readme_docs(
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
        manifest = build_contract_atlas_freshness_manifest(
            conn,
            repo_root=repo_root,
            project_id="dream-studio",
            changed_files=["interfaces/cli/contract_docs_drift_gate.py"],
        )

    assert manifest["status"] == "fail"
    impact = manifest["docs_prd_readme_impact"]
    assert impact["status"] == "attention_required"
    # README.md was removed from release_publication_gate required_doc_refs (O1 narrowing).
    # Release-gate / CI-pipeline changes no longer trigger README review as a per-PR coupling.
    # README currency is a release-boundary human judgment — see PUBLICATION_BOUNDARY.md.
    assert impact["readme_update_required_domains"] == []
    assert "release_publication_gate" in impact["docs_update_required_domains"]


def test_contract_atlas_export_refresh_is_dry_run_by_default_and_writes_explicitly(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "home"
    repo_root = tmp_path / "repo"
    output_dir = tmp_path / "exports"
    _write_current_hook_surfaces(home)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    with _connect(_db(tmp_path)) as conn:
        register_default_adapter_authority_profiles(conn)
        projection_report = adapter_config_projection_report(conn, project_id="dream-studio")
        _write_projection_files(repo_root, projection_report)
        dry_run = refresh_contract_atlas_exports(
            conn,
            repo_root=repo_root,
            output_dir=output_dir,
            project_id="dream-studio",
            include_private=True,
            execute=False,
        )
        executed = refresh_contract_atlas_exports(
            conn,
            repo_root=repo_root,
            output_dir=output_dir,
            project_id="dream-studio",
            include_private=True,
            execute=True,
        )

    assert dry_run["written_files"] == []
    assert executed["sqlite_mutated"] is False
    assert (output_dir / PUBLIC_SANITIZED_EXPORT_FILENAME).exists()
    assert (output_dir / PRIVATE_INTERNAL_EXPORT_FILENAME).exists()
    assert (output_dir / FRESHNESS_MANIFEST_FILENAME).exists()
    public_payload = (output_dir / PUBLIC_SANITIZED_EXPORT_FILENAME).read_text(encoding="utf-8")
    assert str(tmp_path) not in public_payload
    public = json.loads(public_payload)
    assert public["sanitized_public_export"] is True
    manifest = json.loads((output_dir / FRESHNESS_MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert manifest["public_private_data_leakage_check"]["status"] == "pass"


def test_contract_atlas_lifecycle_gate_runs_without_live_home_or_db() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "interfaces/cli/contract_atlas_lifecycle_gate.py",
            "--changed-file",
            "core/shared_intelligence/contract_atlas.py",
            "--changed-file",
            "core/shared_intelligence/contract_atlas_lifecycle.py",
            "--changed-file",
            "projections/api/routes/shared_intelligence.py",
            "--changed-file",
            "interfaces/cli/ds.py",
            "--changed-file",
            "interfaces/cli/ci_gate.py",
            "--changed-file",
            "interfaces/cli/contract_atlas_lifecycle_gate.py",
            "--changed-file",
            "docs/architecture/contract-atlas.md",
            "--changed-file",
            "docs/architecture/dream-studio-dashboard-projection-mapping.md",
            "--changed-file",
            "docs/README.md",
            "--changed-file",
            "README.md",
            "--changed-file",
            "docs/operations/lint-format-baseline-policy.md",
            "--changed-file",
            "docs/operations/task-attribution-and-outcomes.md",
            "--changed-file",
            "docs/operations/prd-authority-lifecycle.md",
            "--changed-file",
            "docs/DATABASE.md",
            "--changed-file",
            "docs/MIGRATION_AUTHORITY.md",
            "--changed-file",
            "docs/contracts/security-by-default-development-lifecycle-gate.md",
            "--changed-file",
            "docs/contracts/security-review-profile-pack-contract.md",
            "--changed-file",
            "docs/contracts/secure-production-readiness-gate.md",
            "--changed-file",
            "docs/operations/product-readiness.md",
            "--changed-file",
            "docs/operations/expert-workflow-systems.md",
            "--changed-file",
            "docs/operations/career-ops-capability-center.md",
            "--changed-file",
            "docs/operations/github-repo-intake-evaluation.md",
            "--changed-file",
            "docs/PUBLICATION_BOUNDARY.md",
            "--changed-file",
            "docs/operations/repo-publication-privacy.md",
            "--changed-file",
            "docs/operations/installed-adapter-runtime.md",
            "--changed-file",
            "docs/operations/installed-platform-productization.md",
            "--changed-file",
            "docs/operations/platform-hardening-sequence.md",
            "--changed-file",
            "docs/operations/long-run-multisession-operational-validation.md",
            "--changed-file",
            "docs/operations/troubleshooting.md",
            "--changed-file",
            "docs/architecture/shared-authority-and-adapter-projections.md",
            "--changed-file",
            "docs/operations/independent-configuration-model.md",
            "--changed-file",
            "docs/operations/external-project-validation-pipeline.md",
            "--changed-file",
            "docs/operations/docker-module-profiles.md",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    assert payload["public_private_data_leakage_check"]["status"] == "pass"


def _db(tmp_path: Path) -> Path:
    return tmp_path / "contract-atlas-lifecycle" / "studio.db"


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
