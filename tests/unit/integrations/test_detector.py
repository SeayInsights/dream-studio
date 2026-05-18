from __future__ import annotations

from pathlib import Path

import pytest

from integrations.detector import (
    CLAUDE_CODE_TOOL_ID,
    detect_all,
    detect_claude_code,
)


def test_detect_claude_code_user_scope_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = detect_claude_code()
    assert result.tool_id == CLAUDE_CODE_TOOL_ID
    assert result.scope == "user"
    assert result.config_root == Path.home() / ".claude"


def test_detect_claude_code_project_scope_when_dot_claude_present(tmp_path, monkeypatch):
    (tmp_path / ".claude").mkdir()
    monkeypatch.chdir(tmp_path)
    result = detect_claude_code(working_dir=tmp_path)
    assert result.scope == "project"
    assert result.config_root == tmp_path / ".claude"


def test_detect_claude_code_scope_override_user(tmp_path, monkeypatch):
    (tmp_path / ".claude").mkdir()
    result = detect_claude_code(working_dir=tmp_path, scope_override="user")
    assert result.scope == "user"
    assert result.config_root == Path.home() / ".claude"


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
