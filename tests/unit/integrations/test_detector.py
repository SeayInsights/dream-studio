from __future__ import annotations

from pathlib import Path

import pytest

from integrations.detector import (
    CLAUDE_CODE_TOOL_ID,
    detect_all,
    detect_claude_code,
)


@pytest.fixture(autouse=True)
def fixture_home(tmp_path, monkeypatch) -> Path:
    """A home of this test's own, and no ambient Claude Code identity.

    User scope resolves to ``CLAUDE_CONFIG_DIR`` when it is set, else ``<home>/.claude``.
    The tests below used to compare against the machine's real ``~/.claude`` and inherited
    whatever ``CLAUDE_CONFIG_DIR`` the shell held, so an operator running a second Claude
    Code identity (the case that variable exists for) failed them. The home is a directory
    apart from ``tmp_path`` itself so a project-scope ``.claude`` made under ``tmp_path``
    can never be mistaken for the user-scope one.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    return home


def test_detect_claude_code_user_scope_default(tmp_path, monkeypatch, fixture_home):
    monkeypatch.chdir(tmp_path)
    result = detect_claude_code()
    assert result.tool_id == CLAUDE_CODE_TOOL_ID
    assert result.scope == "user"
    assert result.config_root == fixture_home / ".claude"


def test_detect_claude_code_user_scope_honors_claude_config_dir(tmp_path, monkeypatch):
    """A second Claude Code identity (e.g. a Fulcrum-specific CLAUDE_CONFIG_DIR) must be
    the config root detection reports for user scope -- not the default ~/.claude."""
    other_home = tmp_path / "claude-fulcrum"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(other_home))
    monkeypatch.chdir(tmp_path)
    result = detect_claude_code()
    assert result.scope == "user"
    assert result.config_root == other_home


def test_detect_claude_code_project_scope_when_dot_claude_present(tmp_path, monkeypatch):
    (tmp_path / ".claude").mkdir()
    monkeypatch.chdir(tmp_path)
    result = detect_claude_code(working_dir=tmp_path)
    assert result.scope == "project"
    assert result.config_root == tmp_path / ".claude"


def test_detect_claude_code_scope_override_user(tmp_path, monkeypatch, fixture_home):
    (tmp_path / ".claude").mkdir()
    result = detect_claude_code(working_dir=tmp_path, scope_override="user")
    assert result.scope == "user"
    assert result.config_root == fixture_home / ".claude"
    assert result.config_root != tmp_path / ".claude"


def test_detect_claude_code_scope_override_project(tmp_path, monkeypatch):
    result = detect_claude_code(working_dir=tmp_path, scope_override="project")
    assert result.scope == "project"
    assert result.config_root == tmp_path / ".claude"


def test_detect_all_returns_claude_code(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tools = detect_all()
    assert len(tools) >= 1
    tool_ids = [t.tool_id for t in tools]
    assert CLAUDE_CODE_TOOL_ID in tool_ids


def test_detect_all_project_scope(tmp_path, monkeypatch):
    (tmp_path / ".claude").mkdir()
    tools = detect_all(working_dir=tmp_path)
    cc = next(t for t in tools if t.tool_id == CLAUDE_CODE_TOOL_ID)
    assert cc.scope == "project"
    assert cc.config_root == tmp_path / ".claude"
