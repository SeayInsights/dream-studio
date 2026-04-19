"""Tests for hooks.lib.paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from lib import paths


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Redirect HOME/USERPROFILE/Path.home to a tmp dir for every test."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    return tmp_path


def test_user_data_dir_creates_and_returns(isolated_home):
    result = paths.user_data_dir()
    assert result == isolated_home / ".dream-studio"
    assert result.is_dir()


def test_user_data_dir_idempotent(isolated_home):
    first = paths.user_data_dir()
    second = paths.user_data_dir()
    assert first == second


def test_meta_dir_under_user_data(isolated_home):
    result = paths.meta_dir()
    assert result == isolated_home / ".dream-studio" / "meta"
    assert result.is_dir()


def test_state_dir_under_user_data(isolated_home):
    result = paths.state_dir()
    assert result == isolated_home / ".dream-studio" / "state"
    assert result.is_dir()


def test_planning_dir_under_user_data(isolated_home):
    result = paths.planning_dir()
    assert result == isolated_home / ".dream-studio" / "planning"
    assert result.is_dir()


def test_project_root_returns_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert paths.project_root() == tmp_path


def test_plugin_root_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
    assert paths.plugin_root() == tmp_path.resolve()


def test_plugin_root_walks_up_to_manifest(tmp_path, monkeypatch):
    """With no env var set, plugin_root finds the real plugin root by walking up."""
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    root = paths.plugin_root()
    assert (root / ".claude-plugin" / "plugin.json").is_file()


def test_plugin_root_raises_when_no_manifest(tmp_path, monkeypatch):
    """If we relocate lib to a dir with no manifest anywhere upward, error."""
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    fake_lib = tmp_path / "fake_lib"
    fake_lib.mkdir()
    monkeypatch.setattr(paths, "__file__", str(fake_lib / "paths.py"))
    with pytest.raises(RuntimeError, match="Could not locate plugin root"):
        paths.plugin_root()
