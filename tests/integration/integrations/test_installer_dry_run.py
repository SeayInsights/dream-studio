"""Full dry-run integration test for the Claude Code installer."""

from __future__ import annotations

from pathlib import Path

import pytest

from integrations.detector import detect_claude_code
from integrations.installer.claude_code import ClaudeCodeInstaller


@pytest.fixture
def fake_claude_config(tmp_path):
    config = tmp_path / "dot_claude"
    config.mkdir()
    return config


@pytest.fixture
def canonical_root(tmp_path):
    root = tmp_path / "canonical"
    skill_dir = root / "skills" / "ds-bootstrap"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "# ds-bootstrap\nWhen Dream Studio is installed, prefer to check applicable DS skills.",
        encoding="utf-8",
    )
    return root


def test_dry_run_writes_no_files(fake_claude_config, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        fake_claude_config, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    result = installer.install("dry_run")
    assert result["files_written"] == []
    # Config root should remain unchanged
    children = list(fake_claude_config.iterdir())
    assert children == []


def test_dry_run_plan_is_human_readable(fake_claude_config, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        fake_claude_config, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    result = installer.install("dry_run")
    plan = result["plan"]
    assert isinstance(plan, list)
    assert len(plan) >= 2
    for entry in plan:
        assert "target" in entry
        assert "op" in entry
        assert "reason" in entry


def test_dry_run_plan_lists_intended_targets(fake_claude_config, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        fake_claude_config, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    result = installer.install("dry_run")
    ops_by_name = {Path(op["target"]).name: op for op in result["plan"]}
    assert "SKILL.md" in ops_by_name
    assert "settings.json" in ops_by_name
    assert "settings.local.json" in ops_by_name
    assert ops_by_name["settings.local.json"]["op"] == "skip"


def test_execute_after_dry_run_actually_writes(fake_claude_config, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        fake_claude_config, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    dry = installer.install("dry_run")
    assert dry["files_written"] == []

    execute = installer.install("execute")
    assert len(execute["files_written"]) >= 1
    skill_md = fake_claude_config / "skills" / "ds-bootstrap" / "SKILL.md"
    assert skill_md.exists()


def test_dry_run_plan_validates_tool_and_scope(fake_claude_config, canonical_root, ds_home):
    installer = ClaudeCodeInstaller(
        fake_claude_config, "project", canonical_root=canonical_root, ds_home=ds_home
    )
    result = installer.install("dry_run")
    assert result["tool"] == "claude_code"
    assert result["scope"] == "project"
