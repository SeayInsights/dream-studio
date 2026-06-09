"""Integration test for the doctor health state machine."""

from __future__ import annotations

from pathlib import Path

import pytest

from integrations.health import IntegrationState, doctor
from integrations.installer.claude_code import ClaudeCodeInstaller


@pytest.fixture
def canonical_root(tmp_path):
    root = tmp_path / "canonical"
    skill_dir = root / "skills" / "ds-bootstrap"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# ds-bootstrap", encoding="utf-8")
    return root


def test_not_detected_state(tmp_path, ds_home):
    config_root = tmp_path / "nonexistent_claude"
    result = doctor("claude_code", config_root, ds_home=ds_home)
    assert result["state"] == IntegrationState.NOT_DETECTED.value


def test_plan_available_state(tmp_path, canonical_root, ds_home):
    config_root = tmp_path / ".claude"
    config_root.mkdir()
    result = doctor("claude_code", config_root, ds_home=ds_home, canonical_root=canonical_root)
    assert result["state"] == IntegrationState.PLAN_AVAILABLE.value


def test_installed_verified_after_execute(tmp_path, canonical_root, ds_home):
    config_root = tmp_path / ".claude"
    config_root.mkdir()
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")
    result = doctor(
        "claude_code",
        config_root,
        ds_home=ds_home,
        canonical_root=canonical_root,
        spool_root=tmp_path / "empty_spool",
    )
    assert result["state"] == IntegrationState.INSTALLED_VERIFIED.value


def test_installed_drifted_after_file_mutation(tmp_path, canonical_root, ds_home):
    config_root = tmp_path / ".claude"
    config_root.mkdir()
    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")

    skill_md = config_root / "skills" / "ds-bootstrap" / "SKILL.md"
    skill_md.write_text("# mutated content", encoding="utf-8")

    result = doctor("claude_code", config_root, ds_home=ds_home)
    assert result["state"] == IntegrationState.INSTALLED_DRIFTED.value
    assert result["drift"]


def test_doctor_returns_config_root_in_result(tmp_path, ds_home):
    config_root = tmp_path / ".claude"
    config_root.mkdir()
    result = doctor("claude_code", config_root, ds_home=ds_home)
    assert str(config_root) in result["config_root"]
