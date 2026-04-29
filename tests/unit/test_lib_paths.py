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


# ── check_for_update ──────────────────────────────────────────────────────


def test_check_for_update_unknown_version_returns_early(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(lp, "plugin_version", lambda: "unknown")
    lp.check_for_update()  # must not make any network call or raise


def test_check_for_update_sentinel_skips_request(tmp_path, monkeypatch):
    import datetime
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(lp, "plugin_version", lambda: "1.0.0")
    today = datetime.date.today().isoformat()
    state = tmp_path / ".dream-studio" / "state"
    state.mkdir(parents=True)
    (state / f".update-checked-{today}").write_text("", encoding="utf-8")
    # If this makes a real network call it would fail — sentinel prevents it
    lp.check_for_update()


def test_check_for_update_no_newer_version(tmp_path, monkeypatch):
    from unittest.mock import MagicMock, patch
    import json
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(lp, "plugin_version", lambda: "1.0.0")
    response_data = json.dumps({"tag_name": "v1.0.0"}).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = response_data
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        lp.check_for_update()
    sentinel = tmp_path / ".dream-studio" / "state"
    assert any(f.name.startswith(".update-checked-") for f in sentinel.iterdir())


def test_check_for_update_newer_version_prints_notice(tmp_path, monkeypatch, capsys):
    from unittest.mock import MagicMock, patch
    import json
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(lp, "plugin_version", lambda: "1.0.0")
    response_data = json.dumps({"tag_name": "v1.1.0"}).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = response_data
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        lp.check_for_update()
    captured = capsys.readouterr()
    assert "Update available" in captured.err
    assert "v1.1.0" in captured.err
    assert "git pull" in captured.err


def test_check_for_update_network_failure_swallowed(tmp_path, monkeypatch):
    from unittest.mock import patch
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(lp, "plugin_version", lambda: "1.0.0")
    with patch("urllib.request.urlopen", side_effect=OSError("network unreachable")):
        lp.check_for_update()  # must not raise


def test_check_for_update_empty_tag_returns_early(tmp_path, monkeypatch):
    from unittest.mock import MagicMock, patch
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(lp, "plugin_version", lambda: "1.0.0")
    response_data = json.dumps({"tag_name": ""}).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = response_data
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        lp.check_for_update()  # empty tag_name → early return (line 159)


def test_check_for_update_invalid_version_handles_valueerror(tmp_path, monkeypatch):
    from unittest.mock import MagicMock, patch
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(lp, "plugin_version", lambda: "1.0.0")
    response_data = json.dumps({"tag_name": "v2.x.0"}).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = response_data
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        lp.check_for_update()  # "2.x.0" → ValueError in _ver → (0,) ≤ (1,0,0) → no update


def test_check_for_update_repo_parse_exception_and_root_fallback(tmp_path, monkeypatch, capsys):
    from unittest.mock import MagicMock, patch
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(lp, "plugin_version", lambda: "1.0.0")

    call_count = [0]

    def flaky_plugin_root():
        call_count[0] += 1
        if call_count[0] > 1:
            raise RuntimeError("plugin root not found")
        return tmp_path  # first call: no plugin.json → manifest.read_text raises

    monkeypatch.setattr(lp, "plugin_root", flaky_plugin_root)
    response_data = json.dumps({"tag_name": "v2.0.0"}).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = response_data
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        lp.check_for_update()

    captured = capsys.readouterr()
    assert "Update available" in captured.err      # notice was printed
    assert "your dream-studio directory" in captured.err  # fallback root (lines 172-173)
