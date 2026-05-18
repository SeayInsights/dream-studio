"""Unit tests for on-context-threshold.py continuation spawner."""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_REPO = Path(__file__).resolve().parents[3]
_HANDLER = _REPO / "runtime" / "hooks" / "meta" / "on-context-threshold.py"


def _load_handler():
    """Load on-context-threshold as a module without executing module-level code."""
    spec = importlib.util.spec_from_file_location("on_context_threshold", _HANDLER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def handler():
    return _load_handler()


# ── threshold tests ───────────────────────────────────────────────────────────


def test_no_spawn_below_threshold(handler, tmp_path, monkeypatch):
    """Below 75% normalized usage, _spawn_continuation must not be called."""
    spawn_calls = []
    monkeypatch.setattr(handler, "_spawn_continuation", lambda cfg: spawn_calls.append(cfg))
    monkeypatch.setattr(handler, "_already_spawned", lambda sid: False)
    monkeypatch.setattr(handler, "_emit_harvest", lambda *a: None)
    monkeypatch.setattr(handler, "_write_spawn_lock", lambda sid: None)
    monkeypatch.setattr(handler, "read_session_config", lambda sid: {})

    # 60% normalized = raw 60 * 83 / 100 = 49.8 raw
    payload = json.dumps({"session_id": "s1", "context_window": {"used_percentage": 49.8}})
    with patch("sys.stdin") as mock_stdin, pytest.raises(SystemExit) as exc:
        mock_stdin.read.return_value = payload
        handler.main()
    assert exc.value.code == 0
    assert len(spawn_calls) == 0


def test_spawn_at_threshold(handler, monkeypatch):
    """At exactly 75% normalized, _spawn_continuation must be called once."""
    spawn_calls = []
    monkeypatch.setattr(handler, "_spawn_continuation", lambda cfg: spawn_calls.append(cfg))
    monkeypatch.setattr(handler, "_already_spawned", lambda sid: False)
    monkeypatch.setattr(handler, "_emit_harvest", lambda *a: None)
    monkeypatch.setattr(handler, "_write_spawn_lock", lambda sid: None)
    monkeypatch.setattr(handler, "read_session_config", lambda sid: {"invocation_flags": []})

    # 75% normalized = raw 75 * 83 / 100 = 62.25 raw
    raw_pct = 75.0 * handler.COMPACT_THRESHOLD / 100.0
    payload = json.dumps({"session_id": "s1", "context_window": {"used_percentage": raw_pct}})
    with patch("sys.stdin") as mock_stdin, pytest.raises(SystemExit) as exc:
        mock_stdin.read.return_value = payload
        handler.main()
    assert exc.value.code == 0
    assert len(spawn_calls) == 1


def test_spawn_lock_prevents_double_spawn(handler, monkeypatch):
    """When _already_spawned returns True, spawn must not be called again."""
    spawn_calls = []
    monkeypatch.setattr(handler, "_spawn_continuation", lambda cfg: spawn_calls.append(cfg))
    monkeypatch.setattr(handler, "_already_spawned", lambda sid: True)
    monkeypatch.setattr(handler, "_emit_harvest", lambda *a: None)
    monkeypatch.setattr(handler, "_write_spawn_lock", lambda sid: None)
    monkeypatch.setattr(handler, "read_session_config", lambda sid: {})

    raw_pct = 80.0 * handler.COMPACT_THRESHOLD / 100.0
    payload = json.dumps({"session_id": "s1", "context_window": {"used_percentage": raw_pct}})
    with patch("sys.stdin") as mock_stdin, pytest.raises(SystemExit) as exc:
        mock_stdin.read.return_value = payload
        handler.main()
    assert exc.value.code == 0
    assert len(spawn_calls) == 0


def test_session_config_flags_carried_over(handler, monkeypatch):
    """--dangerously-skip-permissions in session config appears in spawn command."""
    built_commands = []

    def fake_spawn(session_config):
        flags = session_config.get("invocation_flags", [])
        safe_prompt = handler._build_continuation_prompt(session_config).replace('"', '\\"')
        flags_str = " ".join(flags)
        cmd = f'claude {flags_str} "{safe_prompt}"'.strip()
        built_commands.append(cmd)

    monkeypatch.setattr(handler, "_spawn_continuation", fake_spawn)
    monkeypatch.setattr(handler, "_already_spawned", lambda sid: False)
    monkeypatch.setattr(handler, "_emit_harvest", lambda *a: None)
    monkeypatch.setattr(handler, "_write_spawn_lock", lambda sid: None)
    monkeypatch.setattr(
        handler, "read_session_config",
        lambda sid: {"invocation_flags": ["--dangerously-skip-permissions"], "cwd": "/tmp"}
    )

    raw_pct = 80.0 * handler.COMPACT_THRESHOLD / 100.0
    payload = json.dumps({"session_id": "s1", "context_window": {"used_percentage": raw_pct}})
    with patch("sys.stdin") as mock_stdin, pytest.raises(SystemExit):
        mock_stdin.read.return_value = payload
        handler.main()

    assert len(built_commands) == 1
    assert "--dangerously-skip-permissions" in built_commands[0]


def test_session_config_model_flag(handler, monkeypatch):
    """--model flag and value in session config appear in spawn command."""
    built_commands = []

    def fake_spawn(session_config):
        flags = session_config.get("invocation_flags", [])
        flags_str = " ".join(flags)
        built_commands.append(f"claude {flags_str}")

    monkeypatch.setattr(handler, "_spawn_continuation", fake_spawn)
    monkeypatch.setattr(handler, "_already_spawned", lambda sid: False)
    monkeypatch.setattr(handler, "_emit_harvest", lambda *a: None)
    monkeypatch.setattr(handler, "_write_spawn_lock", lambda sid: None)
    monkeypatch.setattr(
        handler, "read_session_config",
        lambda sid: {"invocation_flags": ["--model", "claude-sonnet-4-6"], "cwd": "/tmp"}
    )

    raw_pct = 80.0 * handler.COMPACT_THRESHOLD / 100.0
    payload = json.dumps({"session_id": "s1", "context_window": {"used_percentage": raw_pct}})
    with patch("sys.stdin") as mock_stdin, pytest.raises(SystemExit):
        mock_stdin.read.return_value = payload
        handler.main()

    assert len(built_commands) == 1
    assert "--model" in built_commands[0]
    assert "claude-sonnet-4-6" in built_commands[0]


def test_continuation_prompt_includes_project(handler, monkeypatch):
    """_build_continuation_prompt includes active project name when found in SQLite."""
    import sqlite3

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE ds_projects (name TEXT, id TEXT, status TEXT)")
    db.execute("INSERT INTO ds_projects VALUES ('MyProject', 'proj-123', 'active')")
    db.execute(
        "CREATE TABLE ds_workflow_runs "
        "(workflow_id TEXT, current_node TEXT, status TEXT, updated_at TEXT)"
    )
    db.commit()

    # Patch sqlite3.connect inside the handler module so the in-memory db is used
    monkeypatch.setattr(
        "sqlite3.connect",
        lambda path, **kw: db if "studio.db" in str(path) else sqlite3.connect(path, **kw),
    )
    # Patch Path.exists so the db_path.exists() check passes
    monkeypatch.setattr(Path, "exists", lambda self: True)

    prompt = handler._build_continuation_prompt({"cwd": "/tmp"})
    assert "MyProject" in prompt


def test_spawn_never_blocks(handler, monkeypatch):
    """Even if _spawn_continuation raises, main must exit 0."""
    def raise_on_spawn(cfg):
        raise RuntimeError("Terminal not found")

    monkeypatch.setattr(handler, "_spawn_continuation", raise_on_spawn)
    monkeypatch.setattr(handler, "_already_spawned", lambda sid: False)
    monkeypatch.setattr(handler, "_emit_harvest", lambda *a: None)
    monkeypatch.setattr(handler, "_write_spawn_lock", lambda sid: None)
    monkeypatch.setattr(handler, "read_session_config", lambda sid: {})

    raw_pct = 80.0 * handler.COMPACT_THRESHOLD / 100.0
    payload = json.dumps({"session_id": "s1", "context_window": {"used_percentage": raw_pct}})
    with patch("sys.stdin") as mock_stdin, pytest.raises(SystemExit) as exc:
        mock_stdin.read.return_value = payload
        handler.main()
    assert exc.value.code == 0
