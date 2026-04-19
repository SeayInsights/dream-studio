"""Unit tests for hooks/handlers/on-stop-handoff.py."""

from __future__ import annotations

import io
import json
import time
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))

# Import the handler module via conftest helper (or direct import here)
import importlib.util

_HANDLER_PATH = Path(__file__).resolve().parents[2] / "hooks" / "handlers" / "on-stop-handoff.py"


def _load_handler():
    spec = importlib.util.spec_from_file_location("on_stop_handoff", _HANDLER_PATH)
    assert spec is not None, f"Could not load spec from {_HANDLER_PATH}"
    assert spec.loader is not None, "Spec has no loader"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ── _has_activity ──────────────────────────────────────────────────────


def test_has_activity_dirty_tree(tmp_path, monkeypatch):
    mod = _load_handler()
    # Patch active_files to return dirty files, and skip git-log check
    monkeypatch.setattr(mod, "active_files", lambda cwd: [("modified", "foo.py")])
    assert mod._has_activity(tmp_path) is True


def test_has_activity_recent_commit(tmp_path, monkeypatch):
    mod = _load_handler()
    monkeypatch.setattr(mod, "active_files", lambda cwd: [])
    # Patch _last_commit_age_seconds to return 1 hour ago
    monkeypatch.setattr(mod, "_last_commit_age_seconds", lambda cwd: 3600)
    assert mod._has_activity(tmp_path) is True


def test_has_activity_clean_old_commit(tmp_path, monkeypatch):
    mod = _load_handler()
    monkeypatch.setattr(mod, "active_files", lambda cwd: [])
    # 48 hours old — beyond the 24h threshold
    monkeypatch.setattr(mod, "_last_commit_age_seconds", lambda cwd: 48 * 3600)
    assert mod._has_activity(tmp_path) is False


def test_has_activity_no_git(tmp_path, monkeypatch):
    mod = _load_handler()
    monkeypatch.setattr(mod, "active_files", lambda cwd: [])
    monkeypatch.setattr(mod, "_last_commit_age_seconds", lambda cwd: None)
    assert mod._has_activity(tmp_path) is False


# ── _last_commit_age_seconds ───────────────────────────────────────────


def test_last_commit_age_returns_float(tmp_path):
    mod = _load_handler()
    # In a non-git dir, git log returns nothing → None
    result = mod._last_commit_age_seconds(tmp_path)
    assert result is None or isinstance(result, float)


def test_last_commit_age_parses_timestamp(tmp_path, monkeypatch):
    mod = _load_handler()
    fake_ts = str(int(time.time()) - 7200)  # 2 hours ago
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: mock.Mock(stdout=fake_ts + "\n"),
    )
    age = mod._last_commit_age_seconds(tmp_path)
    assert age is not None
    assert 7100 < age < 7300


# ── main() — skip on no activity ──────────────────────────────────────


def test_main_skips_on_no_activity(tmp_path, monkeypatch):
    mod = _load_handler()
    monkeypatch.setattr(mod, "_has_activity", lambda cwd: False)
    written = []
    monkeypatch.setattr(mod, "write_handoff", lambda *a, **kw: written.append("handoff") or None)
    monkeypatch.setattr(mod, "write_recap", lambda *a, **kw: written.append("recap"))
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "test123"})))

    mod.main()
    assert written == [], "should write nothing when no activity"


def test_main_writes_on_activity(tmp_path, monkeypatch):
    mod = _load_handler()
    monkeypatch.setattr(mod, "_has_activity", lambda cwd: True)
    monkeypatch.setattr(mod, "paths", mock.Mock(project_root=lambda: tmp_path))

    written = []

    def fake_write_handoff(cwd, kb, session_id, is_pct):
        written.append(("handoff", kb, is_pct))
        return tmp_path / "handoff.md"

    def fake_write_recap(cwd, kb, session_id, handoff_path):
        written.append(("recap", kb))

    monkeypatch.setattr(mod, "write_handoff", fake_write_handoff)
    monkeypatch.setattr(mod, "write_recap", fake_write_recap)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "sess-abc", "cwd": str(tmp_path)})))

    mod.main()

    assert any(e[0] == "handoff" for e in written), "handoff should be written"
    assert any(e[0] == "recap" for e in written), "recap should be written"

    # Confirm kb=0 sentinel and is_pct=False
    handoff_entry = next(e for e in written if e[0] == "handoff")
    assert handoff_entry[1] == 0.0, "kb must be 0.0 sentinel for Stop hook"
    assert handoff_entry[2] is False, "is_pct must be False for Stop hook"


def test_main_handles_empty_stdin(tmp_path, monkeypatch):
    """Handler must not crash when stdin is empty."""
    mod = _load_handler()
    monkeypatch.setattr(mod, "_has_activity", lambda cwd: False)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    mod.main()  # should not raise


def test_main_handles_invalid_json(tmp_path, monkeypatch):
    """Handler must not crash on malformed stdin."""
    mod = _load_handler()
    monkeypatch.setattr(mod, "_has_activity", lambda cwd: False)
    monkeypatch.setattr("sys.stdin", io.StringIO("{bad json"))
    mod.main()  # should not raise
