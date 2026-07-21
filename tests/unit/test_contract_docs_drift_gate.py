from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from core.shared_intelligence.contract_registry import (
    change_impact_report,
    contract_registry,
    validate_contract_registry,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_contract_registry_has_required_release_blocking_domains() -> None:
    registry = contract_registry()

    assert validate_contract_registry(registry) == []
    assert registry["derived_view"] is True
    assert registry["primary_authority"] is False
    assert registry["db_write_authorized"] is False
    domain_ids = {domain["domain_id"] for domain in registry["domains"]}
    assert domain_ids >= {
        "contract_atlas",
        "shared_intelligence_adapters",
        "sqlite_schema_authority",
        "dashboard_runtime",
        "workflow_and_hooks",
        "release_publication_gate",
    }
    assert all(domain["release_blocking"] is True for domain in registry["domains"])


def test_contract_docs_drift_blocks_source_change_without_required_docs() -> None:
    report = change_impact_report(["core/shared_intelligence/contract_atlas.py"])

    assert report["status"] == "fail"
    assert report["blocking_domain_count"] == 1
    blocking = report["blocking_domains"][0]
    assert blocking["domain_id"] == "contract_atlas"
    assert "docs/architecture/contract-atlas.md" in blocking["missing_required_doc_refs"]
    # docs/README.md assertion removed (Wave 7): README ungated from contract_atlas (O1 precedent).
    assert blocking["docs_update_required"] is True
    assert blocking["contract_atlas_update_required"] is True


def test_contract_docs_drift_passes_when_required_docs_are_refreshed() -> None:
    report = change_impact_report(
        [
            "core/shared_intelligence/contract_atlas.py",
            "docs/architecture/contract-atlas.md",
            "docs/README.md",
            "docs/operations/lint-format-baseline-policy.md",
        ]
    )

    assert report["status"] == "pass"
    impacted = [domain for domain in report["domains"] if domain["impacted"]]
    assert [domain["domain_id"] for domain in impacted] == ["contract_atlas"]
    assert impacted[0]["freshness_status"] == "fresh"
    assert impacted[0]["docs_update_required"] is False


def test_contract_docs_drift_supports_explicit_reviewed_no_change_decision() -> None:
    report = change_impact_report(
        ["core/config/database.py"],
        reviewed_no_change_domains=["sqlite_schema_authority"],
    )

    assert report["status"] == "pass"
    impacted = [domain for domain in report["domains"] if domain["impacted"]]
    assert impacted[0]["domain_id"] == "sqlite_schema_authority"
    assert impacted[0]["freshness_status"] == "docs_reviewed_no_change_needed"
    assert impacted[0]["docs_reviewed_no_change_needed"] is True


def test_contract_docs_drift_detects_private_artifact_publication_risk() -> None:
    report = change_impact_report([".dream-studio/state/studio.db"])

    assert report["status"] == "fail"
    assert report["publication_risk"]["private_artifact_risk_detected"] is True
    assert (
        "remove_private_artifact_from_repo_change_set"
        in report["publication_risk"]["required_actions"]
    )


def test_contract_docs_drift_cli_uses_explicit_changed_files() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "interfaces/cli/contract_docs_drift_gate.py",
            "--changed-file",
            "interfaces/cli/ci_gate.py",
            "--changed-file",
            "interfaces/cli/contract_docs_drift_gate.py",
            "--changed-file",
            "docs/operations/lint-format-baseline-policy.md",
            "--changed-file",
            "docs/PUBLICATION_BOUNDARY.md",
            "--changed-file",
            "docs/operations/repo-publication-privacy.md",
            "--changed-file",
            "docs/operations/external-project-validation-pipeline.md",
            "--changed-file",
            "docs/operations/docker-module-profiles.md",
            "--changed-file",
            "README.md",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    assert payload["impacted_domain_count"] == 1
    assert any(domain["domain_id"] == "release_publication_gate" for domain in payload["domains"])


def test_contract_docs_drift_cli_fails_on_missing_impacted_docs() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "interfaces/cli/contract_docs_drift_gate.py",
            "--changed-file",
            "core/config/database.py",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "fail"
    assert payload["blocking_domains"][0]["domain_id"] == "sqlite_schema_authority"
    assert "docs/DATABASE.md" in payload["blocking_domains"][0]["missing_required_doc_refs"]


def test_changed_files_covers_full_branch_not_just_last_commit(tmp_path, monkeypatch) -> None:
    """WO-GATE-PARITY regression: the base-ref diff must capture the FULL branch
    change set (merge-base three-dot diff), including a contract-domain file
    changed in an earlier commit than the one being pushed."""
    import argparse

    import interfaces.cli.contract_docs_drift_gate as gate_mod

    repo = tmp_path / "repo"
    repo.mkdir()
    run = dict(cwd=str(repo), capture_output=True, text=True, check=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], **run)
    subprocess.run(["git", "config", "user.email", "t@t"], **run)
    subprocess.run(["git", "config", "user.name", "t"], **run)
    (repo / "base.txt").write_text("base", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], **run)
    subprocess.run(["git", "commit", "-q", "-m", "base"], **run)
    subprocess.run(["git", "checkout", "-q", "-b", "feature"], **run)
    # Commit 1: the contract-domain source change.
    (repo / "sqlite_bootstrap.py").write_text("v1", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], **run)
    subprocess.run(["git", "commit", "-q", "-m", "touch contract domain"], **run)
    # Commit 2 (the one "being pushed"): an unrelated change.
    (repo / "other.txt").write_text("v1", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], **run)
    subprocess.run(["git", "commit", "-q", "-m", "unrelated"], **run)

    monkeypatch.setattr(gate_mod, "REPO_ROOT", repo)
    monkeypatch.delenv("DREAM_STUDIO_CHANGED_FILES", raising=False)
    monkeypatch.delenv("DREAM_STUDIO_BASE_REF", raising=False)
    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
    args = argparse.Namespace(
        changed_file=[], changed_files=None, base_ref="main", docs_reviewed_no_change=[]
    )

    files = gate_mod._changed_files(args)

    assert "sqlite_bootstrap.py" in files, "earlier-commit change missing from change set"
    assert "other.txt" in files


def test_pre_push_manifest_docs_drift_is_blocking() -> None:
    """WO-GATE-PARITY: CI runs the docs-drift script as a blocking step, so the
    local pre-push tier must be blocking too — an advisory tier let PR #263
    push green and then fail all three matrix platforms on the same drift."""
    import yaml

    manifest = yaml.safe_load(
        (REPO_ROOT / "canonical" / "workflows" / "pre-push.yaml").read_text(encoding="utf-8")
    )
    docs_drift = next(g for g in manifest["gates"] if g["id"] == "docs-drift")
    assert docs_drift["tier"] == "blocking"


def test_engine_skill_coupling_domains_exist() -> None:
    """WO-SKILL-COUPLING: the three new deterministic engine→skill coupling domains
    must be registered and release-blocking."""
    registry = contract_registry()
    domain_ids = {domain["domain_id"] for domain in registry["domains"]}
    assert "work_orders_engine_skill_surface" in domain_ids
    assert "projects_engine_skill_surface" in domain_ids
    assert "milestones_engine_skill_surface" in domain_ids
    for domain in registry["domains"]:
        if domain["domain_id"] in (
            "work_orders_engine_skill_surface",
            "projects_engine_skill_surface",
            "milestones_engine_skill_surface",
        ):
            assert (
                domain["release_blocking"] is True
            ), f"{domain['domain_id']} must be release_blocking"


def test_work_orders_engine_change_triggers_skill_surface_domain() -> None:
    """Changing a work_orders engine file must require canonical/skills/ds-workorder/SKILL.md."""
    report = change_impact_report(["core/work_orders/verify.py"])

    wo_domain = next(
        (d for d in report["domains"] if d["domain_id"] == "work_orders_engine_skill_surface"),
        None,
    )
    assert wo_domain is not None
    assert wo_domain["impacted"] is True
    assert "canonical/skills/ds-workorder/SKILL.md" in wo_domain["missing_required_doc_refs"]
    assert wo_domain["release_blocking"] is True


def test_work_orders_engine_change_passes_when_skill_doc_included() -> None:
    """Including canonical/skills/ds-workorder/SKILL.md in the changeset satisfies the coupling."""
    report = change_impact_report(
        ["core/work_orders/verify.py", "canonical/skills/ds-workorder/SKILL.md"]
    )

    wo_domain = next(
        d for d in report["domains"] if d["domain_id"] == "work_orders_engine_skill_surface"
    )
    assert wo_domain["freshness_status"] == "fresh"
    assert wo_domain["missing_required_doc_refs"] == []


def test_contract_docs_drift_cli_accepts_reviewed_no_change() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "interfaces/cli/contract_docs_drift_gate.py",
            "--changed-file",
            "core/config/database.py",
            "--docs-reviewed-no-change",
            "sqlite_schema_authority",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    sqlite_domain = next(
        domain for domain in payload["domains"] if domain["domain_id"] == "sqlite_schema_authority"
    )
    assert sqlite_domain["freshness_status"] == "docs_reviewed_no_change_needed"


def test_reviewed_no_change_env_var_reaches_blocking_lane() -> None:
    """WO-DOCS-DRIFT-REVIEWED-ESCAPE: the blocking lane invokes the gate with no
    flag, so DREAM_STUDIO_DOCS_REVIEWED_NO_CHANGE must be honored for an
    impacted domain (local-convenience signal)."""
    env = dict(os.environ)
    env["DREAM_STUDIO_DOCS_REVIEWED_NO_CHANGE"] = "sqlite_schema_authority"
    result = subprocess.run(
        [
            sys.executable,
            "interfaces/cli/contract_docs_drift_gate.py",
            "--changed-file",
            "core/config/database.py",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    assert "sqlite_schema_authority" in payload["reviewed_no_change_domains"]
    sqlite_domain = next(
        d for d in payload["domains"] if d["domain_id"] == "sqlite_schema_authority"
    )
    assert sqlite_domain["freshness_status"] == "docs_reviewed_no_change_needed"


def _init_repo_with_trailer(tmp_path: Path, trailer_domain: str) -> Path:
    """Build a tmp repo: main baseline + a feature commit touching a real
    contract-domain source file, carrying a Docs-Reviewed-No-Change trailer."""
    repo = tmp_path / "repo"
    (repo / "core" / "config").mkdir(parents=True)
    run = dict(cwd=str(repo), capture_output=True, text=True, check=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], **run)
    subprocess.run(["git", "config", "user.email", "t@t"], **run)
    subprocess.run(["git", "config", "user.name", "t"], **run)
    (repo / "base.txt").write_text("base", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], **run)
    subprocess.run(["git", "commit", "-q", "-m", "base"], **run)
    subprocess.run(["git", "checkout", "-q", "-b", "feature"], **run)
    # A real sqlite_schema_authority source pattern so the domain is impacted.
    (repo / "core" / "config" / "database.py").write_text("v1", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], **run)
    subprocess.run(
        [
            "git",
            "commit",
            "-q",
            "-m",
            f"refactor: no behavior change\n\nDocs-Reviewed-No-Change: {trailer_domain}\n",
        ],
        **run,
    )
    return repo


def test_commit_trailer_reviewed_no_change_reaches_blocking_lane(tmp_path, monkeypatch) -> None:
    """WO-DOCS-DRIFT-REVIEWED-ESCAPE: a `Docs-Reviewed-No-Change: <domain>` commit
    trailer in the diff range must satisfy that impacted domain — this is the
    signal that travels identically through push and CI (both flag-less)."""
    import argparse

    import interfaces.cli.contract_docs_drift_gate as gate_mod

    repo = _init_repo_with_trailer(tmp_path, "sqlite_schema_authority")
    monkeypatch.setattr(gate_mod, "REPO_ROOT", repo)
    monkeypatch.delenv("DREAM_STUDIO_CHANGED_FILES", raising=False)
    monkeypatch.delenv("DREAM_STUDIO_BASE_REF", raising=False)
    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
    monkeypatch.delenv("DREAM_STUDIO_DOCS_REVIEWED_NO_CHANGE", raising=False)
    args = argparse.Namespace(
        changed_file=[], changed_files=None, base_ref="main", docs_reviewed_no_change=[]
    )

    reviewed = gate_mod._reviewed_no_change_domains(args)
    assert "sqlite_schema_authority" in reviewed

    report = change_impact_report(
        gate_mod._changed_files(args), reviewed_no_change_domains=reviewed
    )
    assert report["status"] == "pass"
    sqlite_domain = next(
        d for d in report["domains"] if d["domain_id"] == "sqlite_schema_authority"
    )
    assert sqlite_domain["impacted"] is True
    assert sqlite_domain["freshness_status"] == "docs_reviewed_no_change_needed"


def test_trailer_for_other_domain_does_not_false_pass_impacted_domain(
    tmp_path, monkeypatch
) -> None:
    """A trailer naming a different (or unknown) domain must NOT rescue the
    actually-impacted-but-undeclared domain — the escape is per-domain, not a
    blanket skip."""
    import argparse

    import interfaces.cli.contract_docs_drift_gate as gate_mod

    repo = _init_repo_with_trailer(tmp_path, "some_unrelated_domain")
    monkeypatch.setattr(gate_mod, "REPO_ROOT", repo)
    monkeypatch.delenv("DREAM_STUDIO_CHANGED_FILES", raising=False)
    monkeypatch.delenv("DREAM_STUDIO_BASE_REF", raising=False)
    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
    monkeypatch.delenv("DREAM_STUDIO_DOCS_REVIEWED_NO_CHANGE", raising=False)
    args = argparse.Namespace(
        changed_file=[], changed_files=None, base_ref="main", docs_reviewed_no_change=[]
    )

    reviewed = gate_mod._reviewed_no_change_domains(args)
    assert reviewed == ["some_unrelated_domain"]

    report = change_impact_report(
        gate_mod._changed_files(args), reviewed_no_change_domains=reviewed
    )
    assert report["status"] == "fail"
    assert report["blocking_domains"][0]["domain_id"] == "sqlite_schema_authority"
