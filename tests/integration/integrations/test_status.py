"""Integration test for multi-tool status reporting."""

from __future__ import annotations

from pathlib import Path

import pytest

from integrations.detector import detect_all
from integrations.health import IntegrationState, doctor
from integrations.installer.claude_code import ClaudeCodeInstaller


@pytest.fixture
def canonical_root(tmp_path):
    root = tmp_path / "canonical"
    skill_dir = root / "skills" / "ds-bootstrap"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# ds-bootstrap", encoding="utf-8")
    return root


def test_status_returns_claude_code(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tools = detect_all()
    assert any(t.tool_id == "claude_code" for t in tools)


def test_status_reflects_install_state(tmp_path, canonical_root, ds_home):
    config_root = tmp_path / ".claude"
    config_root.mkdir()

    result_before = doctor(
        "claude_code", config_root, ds_home=ds_home, canonical_root=canonical_root
    )
    assert result_before["state"] == IntegrationState.PLAN_AVAILABLE.value

    installer = ClaudeCodeInstaller(
        config_root, "user", canonical_root=canonical_root, ds_home=ds_home
    )
    installer.install("execute")

    result_after = doctor(
        "claude_code", config_root, ds_home=ds_home, canonical_root=canonical_root
    )
    assert result_after["state"] == IntegrationState.INSTALLED_VERIFIED.value


def test_status_shows_correct_health_for_not_detected(tmp_path, ds_home):
    config_root = tmp_path / "missing_claude"
    result = doctor("claude_code", config_root, ds_home=ds_home)
    assert result["state"] == IntegrationState.NOT_DETECTED.value
