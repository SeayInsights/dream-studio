"""Unit tests for on-stop-handoff hook."""

from __future__ import annotations

import io
import json
import time
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from control.context import handoff as context_handoff  # noqa: E402
from conftest import load_handler  # noqa: E402


def _load_handler():
    return load_handler("on-stop-handoff")


# ── has_session_activity ───────────────────────────────────────────────


def test_has_activity_dirty_tree(tmp_path, monkeypatch):
    # Patch active_files to return dirty files
    monkeypatch.setattr(context_handoff, "active_files", lambda cwd: [("modified", "foo.py")])
    assert context_handoff.has_session_activity(tmp_path) is True


def test_has_activity_recent_commit(tmp_path, monkeypatch):
    monkeypatch.setattr(context_handoff, "active_files", lambda cwd: [])
    # Patch last_commit_age_seconds to return 1 hour ago
    monkeypatch.setattr(context_handoff, "last_commit_age_seconds", lambda cwd: 3600)
    assert context_handoff.has_session_activity(tmp_path) is True


def test_has_activity_clean_old_commit(tmp_path, monkeypatch):
    monkeypatch.setattr(context_handoff, "active_files", lambda cwd: [])
    # 48 hours old — beyond the 24h threshold
    monkeypatch.setattr(context_handoff, "last_commit_age_seconds", lambda cwd: 48 * 3600)
    assert context_handoff.has_session_activity(tmp_path) is False


def test_has_activity_no_git(tmp_path, monkeypatch):
    monkeypatch.setattr(context_handoff, "active_files", lambda cwd: [])
    monkeypatch.setattr(context_handoff, "last_commit_age_seconds", lambda cwd: None)
    assert context_handoff.has_session_activity(tmp_path) is False


# ── last_commit_age_seconds ────────────────────────────────────────────


def test_last_commit_age_returns_float(tmp_path):
    # In a non-git dir, git log returns nothing → None
    result = context_handoff.last_commit_age_seconds(tmp_path)
    assert result is None or isinstance(result, float)


def test_last_commit_age_parses_timestamp(tmp_path, monkeypatch):
    fake_ts = str(int(time.time()) - 7200)  # 2 hours ago
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: mock.Mock(stdout=fake_ts + "\n"),
    )
    age = context_handoff.last_commit_age_seconds(tmp_path)
    assert age is not None
    assert 7100 < age < 7300


# ── main() — skip on no activity ──────────────────────────────────────


def test_main_skips_on_no_activity(tmp_path, monkeypatch):
    mod = _load_handler()
    monkeypatch.setattr(context_handoff, "has_session_activity", lambda cwd: False)
    written = []
    monkeypatch.setattr(
        context_handoff, "write_session_handoff", lambda *a, **kw: written.append("handoff") or None
    )
    monkeypatch.setattr(
        context_handoff, "record_session_to_db", lambda *a, **kw: written.append("record")
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"session_id": "test123"})))

    mod.main()
    assert written == [], "should write nothing when no activity"


def test_main_writes_on_activity(tmp_path, monkeypatch):
    mod = _load_handler()
    monkeypatch.setattr(context_handoff, "has_session_activity", lambda cwd: True)
    monkeypatch.setattr(mod, "has_sentinel", lambda key, **kw: False)
    monkeypatch.setattr(mod, "set_sentinel", lambda key, typ, **kw: True)

    written = []

    def fake_write_session_handoff(cwd, session_id):
        written.append(("handoff", cwd, session_id))
        return tmp_path / "handoff.md"

    def fake_record_session_to_db(cwd, session_id, handoff_path):
        written.append(("record", cwd, session_id))

    monkeypatch.setattr(context_handoff, "write_session_handoff", fake_write_session_handoff)
    monkeypatch.setattr(context_handoff, "record_session_to_db", fake_record_session_to_db)
    monkeypatch.setattr(
        "sys.stdin", io.StringIO(json.dumps({"session_id": "sess-abc", "cwd": str(tmp_path)}))
    )

    mod.main()

    assert any(e[0] == "handoff" for e in written), "handoff should be written"
    assert any(e[0] == "record" for e in written), "record should be written"


def test_main_handles_empty_stdin(tmp_path, monkeypatch):
    """Handler must not crash when stdin is empty."""
    mod = _load_handler()
    monkeypatch.setattr(context_handoff, "has_session_activity", lambda cwd: False)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    mod.main()  # should not raise


def test_main_handles_invalid_json(tmp_path, monkeypatch):
    """Handler must not crash on malformed stdin."""
    mod = _load_handler()
    monkeypatch.setattr(context_handoff, "has_session_activity", lambda cwd: False)
    monkeypatch.setattr("sys.stdin", io.StringIO("{bad json"))
    mod.main()  # should not raise
