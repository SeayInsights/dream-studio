"""Tests for hooks/lib/paths.py — plugin_root, plugin_version, writability, version mismatch."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))

import lib.paths as lp  # noqa: E402
from lib.paths import user_data_dir_writable, warn_version_mismatch  # noqa: E402


# ── plugin_root: RuntimeError when no markers found (line 39) ─────────────


def test_plugin_root_raises_when_no_markers(monkeypatch):
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    orig_is_file = Path.is_file
    orig_is_dir = Path.is_dir

    def no_plugin_json(self):
        if ".claude-plugin" in str(self) and self.name == "plugin.json":
            return False
        return orig_is_file(self)

    def no_skills_or_rules(self):
        if self.name in ("skills", "rules"):
            return False
        return orig_is_dir(self)

    monkeypatch.setattr(Path, "is_file", no_plugin_json)
    monkeypatch.setattr(Path, "is_dir", no_skills_or_rules)
    with pytest.raises(RuntimeError, match="Could not locate plugin root"):
        lp.plugin_root()


# ── plugin_version: exception returns "unknown" (lines 54-56) ─────────────


def test_plugin_version_returns_unknown_on_exception(monkeypatch):
    def fail_root():
        raise RuntimeError("no root")
    monkeypatch.setattr(lp, "plugin_root", fail_root)
    assert lp.plugin_version() == "unknown"


# ── user_data_dir_writable (lines 112-120) ────────────────────────────────


def test_user_data_dir_writable_returns_true(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert user_data_dir_writable() is True


def test_user_data_dir_writable_returns_false_on_oserror(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    from unittest.mock import patch
    with patch.object(Path, "mkdir", side_effect=OSError("permission denied")):
        assert user_data_dir_writable() is False


# ── warn_version_mismatch: early returns (lines 134, 137) ─────────────────


def test_warn_unknown_version_returns_early(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(lp, "plugin_version", lambda: "unknown")
    warn_version_mismatch()  # should return at line 134


def test_warn_sentinel_exists_returns_early(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(lp, "plugin_version", lambda: "1.0.0")
    state = tmp_path / ".dream-studio" / "state"
    state.mkdir(parents=True)
    (state / ".version-warned-1.0.0").write_text("", encoding="utf-8")
    warn_version_mismatch()  # should return at line 137


# ── warn_version_mismatch: cache comparison loop (lines 141-158) ──────────


def test_warn_version_mismatch_detects_cache_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(lp, "plugin_version", lambda: "1.0.0")
    plugin_dir = (
        tmp_path / ".claude" / "plugins" / "cache"
        / "dream-studio" / "dream-studio" / "0.9.0"
    )
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps({"version": "0.9.0"}), encoding="utf-8"
    )
    warn_version_mismatch()
    sentinel = tmp_path / ".dream-studio" / "state" / ".version-warned-1.0.0"
    assert sentinel.exists()


def test_warn_version_mismatch_inner_exception_swallowed(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(lp, "plugin_version", lambda: "1.0.0")
    bad_dir = (
        tmp_path / ".claude" / "plugins" / "cache"
        / "dream-studio" / "bad" / "x"
    )
    bad_dir.mkdir(parents=True)
    (bad_dir / "plugin.json").write_text("INVALID JSON", encoding="utf-8")
    warn_version_mismatch()  # inner except must swallow the JSON parse error


def test_warn_version_mismatch_outer_exception_swallowed(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(lp, "plugin_version", lambda: "1.0.0")
    def fail_state():
        raise RuntimeError("state dir unavailable")
    monkeypatch.setattr(lp, "state_dir", fail_state)
    warn_version_mismatch()  # outer except must swallow the RuntimeError
