from __future__ import annotations

from pathlib import Path

import pytest

from integrations.installer.base import RefusalError
from integrations.installer.claude_code import ClaudeCodeInstaller


@pytest.fixture
def canonical_root(tmp_path):
    root = tmp_path / "canonical"
    skill_dir = root / "skills" / "ds-bootstrap"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# ds-bootstrap advisory skill.", encoding="utf-8")
    return root


@pytest.fixture
def config_root(tmp_path):
    cr = tmp_path / "claude_config"
    cr.mkdir()
    return cr


def test_plan_includes_skill_md_create(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    plan = installer.plan()
    ops = {op.target.name: op for op in plan.ops}
    assert "SKILL.md" in ops
    assert ops["SKILL.md"].op == "create"


def test_plan_includes_settings_json_merge(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    plan = installer.plan()
    ops = {op.target.name: op for op in plan.ops}
    assert "settings.json" in ops
    assert ops["settings.json"].op == "merge_json"


def test_plan_always_skips_settings_local_json(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    plan = installer.plan()
    ops = {op.target.name: op for op in plan.ops}
    assert "settings.local.json" in ops
    assert ops["settings.local.json"].op == "skip"
    assert "private/local" in ops["settings.local.json"].reason


def test_settings_local_json_never_written_even_in_execute(config_root, canonical_root, ds_home):
    (config_root / "settings.local.json").write_text('{"private": true}', encoding="utf-8")
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    result = installer.install("execute")
    written = [r["path"] for r in result["files_written"]]
    assert not any("settings.local.json" in p for p in written)


def test_install_refusal_on_bad_mode(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    with pytest.raises(RefusalError):
        installer.install("approve")


def test_dry_run_writes_nothing(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    result = installer.install("dry_run")
    assert result["mode"] == "dry_run"
    assert result["files_written"] == []
    skill_target = config_root / "skills" / "ds-bootstrap" / "SKILL.md"
    assert not skill_target.exists()


def test_execute_writes_skill_md(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    result = installer.install("execute")
    assert result["mode"] == "execute"
    skill_md = config_root / "skills" / "ds-bootstrap" / "SKILL.md"
    assert skill_md.exists()
    assert "ds-bootstrap" in skill_md.read_text(encoding="utf-8")


def test_execute_writes_settings_json(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    settings = config_root / "settings.json"
    assert settings.exists()


def test_execute_preserves_existing_settings_keys(config_root, canonical_root, ds_home):
    import json

    (config_root / "settings.json").write_text('{"theme": "dark", "hooks": {}}', encoding="utf-8")
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    settings = json.loads((config_root / "settings.json").read_text(encoding="utf-8"))
    assert settings.get("theme") == "dark"


def test_execute_writes_manifest(config_root, canonical_root, ds_home):
    from integrations.manifest import read_manifest, MANIFEST_SCHEMA_VERSION

    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    manifest = read_manifest("claude_code", ds_home)
    assert manifest is not None
    assert manifest["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert manifest["tool"] == "claude_code"


def test_execute_creates_backup_for_existing_settings(config_root, canonical_root, ds_home):
    (config_root / "settings.json").write_text('{"existing": true}', encoding="utf-8")
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    backup_dir = ds_home / "backups" / "claude_code"
    backups = list(backup_dir.rglob("settings.json*.bak")) if backup_dir.exists() else []
    assert len(backups) >= 1


def _seed_prior_manifest_with_orphan(config_root, ds_home, orphan_path):
    """Record `orphan_path` as if a prior install wrote it, then create it on disk.

    Mirrors an operator who installed before a mode moved to a different pack: the
    manifest remembers the file, and the file is still physically present.
    """
    from integrations.manifest import build_manifest, compute_hash, write_manifest

    orphan_path.parent.mkdir(parents=True, exist_ok=True)
    orphan_path.write_text("STALE PRE-MOVE CONTENT", encoding="utf-8")
    manifest = build_manifest(
        tool="claude_code",
        scope="user",
        ds_version="0.0.0-test",
        files=[
            {
                "path": str(orphan_path),
                "operation": "create",
                "content_hash": compute_hash("STALE PRE-MOVE CONTENT"),
                "backup_path": None,
            },
            {
                "path": str(config_root / "skills" / "ds-bootstrap" / "SKILL.md"),
                "operation": "create",
                "content_hash": compute_hash("# ds-bootstrap advisory skill."),
                "backup_path": None,
            },
        ],
    )
    write_manifest("claude_code", manifest, ds_home)


def test_plan_prunes_orphaned_skill_file_no_longer_in_canonical(
    config_root, canonical_root, ds_home
):
    orphan = config_root / "skills" / "ds-quality" / "modes" / "database" / "SKILL.md"
    _seed_prior_manifest_with_orphan(config_root, ds_home, orphan)
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    plan = installer.plan()
    delete_targets = {str(op.target) for op in plan.ops if op.op == "delete"}
    assert str(orphan) in delete_targets


def test_plan_does_not_prune_a_skill_file_canonical_still_produces(
    config_root, canonical_root, ds_home
):
    orphan = config_root / "skills" / "ds-quality" / "modes" / "database" / "SKILL.md"
    _seed_prior_manifest_with_orphan(config_root, ds_home, orphan)
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    plan = installer.plan()
    delete_targets = {str(op.target) for op in plan.ops if op.op == "delete"}
    bootstrap_skill_md = config_root / "skills" / "ds-bootstrap" / "SKILL.md"
    assert str(bootstrap_skill_md) not in delete_targets


def test_execute_removes_orphaned_skill_file_and_backs_it_up(config_root, canonical_root, ds_home):
    orphan = config_root / "skills" / "ds-quality" / "modes" / "database" / "SKILL.md"
    _seed_prior_manifest_with_orphan(config_root, ds_home, orphan)
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    result = installer.install("execute")
    assert not orphan.exists()
    assert result["skills"]["files_removed"] == 1
    backup_dir = ds_home / "backups" / "claude_code"
    backups = list(backup_dir.rglob("SKILL.md*.bak")) if backup_dir.exists() else []
    assert any(b.read_text(encoding="utf-8") == "STALE PRE-MOVE CONTENT" for b in backups)


def test_execute_prunes_now_empty_orphan_directories(config_root, canonical_root, ds_home):
    orphan = config_root / "skills" / "ds-quality" / "modes" / "database" / "SKILL.md"
    _seed_prior_manifest_with_orphan(config_root, ds_home, orphan)
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    assert not orphan.parent.exists()
    assert not (config_root / "skills" / "ds-quality").exists()
    assert (config_root / "skills").exists()


def test_execute_manifest_no_longer_lists_removed_orphan(config_root, canonical_root, ds_home):
    from integrations.manifest import read_manifest

    orphan = config_root / "skills" / "ds-quality" / "modes" / "database" / "SKILL.md"
    _seed_prior_manifest_with_orphan(config_root, ds_home, orphan)
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    manifest = read_manifest("claude_code", ds_home)
    paths = {entry["path"] for entry in manifest["files"]}
    assert str(orphan) not in paths


# --------------------------------------------------------------------------
# A project's own round-table seat, via git_repo_root
# --------------------------------------------------------------------------

_PROJECT_LANE_YAML = """
mode: add
lanes:
  - id: a-project-specific-lane
    seat: PCI Scope
    question: >
      Does this change touch anything in the cardholder data environment?
    signature: >
      A file under payments/ or checkout/ changed with no PCI reviewer sign-off noted
      in the PR body.
    precedent: >
      Filed after an internal audit found three merged PRs touching payment capture
      with no compliance review recorded anywhere.
    measurement: >
      No automatable predicate exists for "touches CDE" without a maintained
      file-ownership map, so this is judgment rather than a detector.
    model: sonnet
    judgment: true
    why: >
      No maintained CDE file-ownership map exists yet to turn this into a detector.
"""


@pytest.fixture
def project_with_marker(tmp_path):
    root = tmp_path / "a-project"
    root.mkdir()
    (root / ".ds-review-lanes.yml").write_text(_PROJECT_LANE_YAML, encoding="utf-8")
    return root


def test_plan_includes_a_project_seat_when_git_repo_root_has_a_marker(
    config_root, canonical_root, ds_home, project_with_marker
):
    installer = ClaudeCodeInstaller(
        config_root,
        "user",
        canonical_root=canonical_root,
        ds_home=ds_home,
        git_repo_root=project_with_marker,
    )
    plan = installer.plan()
    ops = {op.target.name: op for op in plan.ops}
    assert "review-pci-scope.md" in ops
    assert ops["review-pci-scope.md"].op == "create"
    assert ops["review-pci-scope.md"].target == config_root / "agents" / "review-pci-scope.md"


def test_plan_has_no_project_seat_without_git_repo_root(config_root, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    plan = installer.plan()
    ops = {op.target.name: op for op in plan.ops}
    assert "review-pci-scope.md" not in ops


def test_plan_has_no_project_seat_when_git_repo_root_has_no_marker(
    config_root, canonical_root, ds_home, tmp_path
):
    bare_root = tmp_path / "no-marker-here"
    bare_root.mkdir()
    installer = ClaudeCodeInstaller(
        config_root,
        "user",
        canonical_root=canonical_root,
        ds_home=ds_home,
        git_repo_root=bare_root,
    )
    plan = installer.plan()
    ops = {op.target.name: op for op in plan.ops}
    assert "review-pci-scope.md" not in ops


def test_execute_writes_the_project_seat_into_the_agents_dir(
    config_root, canonical_root, ds_home, project_with_marker
):
    installer = ClaudeCodeInstaller(
        config_root,
        "user",
        canonical_root=canonical_root,
        ds_home=ds_home,
        git_repo_root=project_with_marker,
    )
    installer.install("execute")
    written = config_root / "agents" / "review-pci-scope.md"
    assert written.is_file()
    assert "name: review-pci-scope" in written.read_text(encoding="utf-8")
