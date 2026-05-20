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
