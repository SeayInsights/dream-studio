"""Tests for WO-HS: handoff-spawner de-silencing and ds doctor check."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helper: load on-stop-dispatch without going through package machinery
# ---------------------------------------------------------------------------


def _load_dispatcher():
    spec = importlib.util.spec_from_file_location(
        "on_stop_dispatch_hs",
        Path(__file__).parent.parent.parent / "runtime" / "hooks" / "meta" / "on-stop-dispatch.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# _dispatch_handoff_continuation: import-failure path must emit visible warning
# ---------------------------------------------------------------------------


def test_spawn_none_emits_warning(tmp_path):
    """When _spawn_new_session is None (import failed), a visible warning must appear on stderr."""
    mod = _load_dispatcher()
    orig = mod._spawn_new_session
    mod._spawn_new_session = None

    captured = io.StringIO()
    old_err = sys.stderr
    sys.stderr = captured
    try:
        mod._dispatch_handoff_continuation()
    finally:
        sys.stderr = old_err
        mod._spawn_new_session = orig

    output = captured.getvalue()
    assert "[DS handoff-spawner]" in output, f"Expected warning tag, got: {output!r}"
    assert (
        "session_config" in output.lower() or "import" in output.lower()
    ), f"Expected import-failure context in warning: {output!r}"


def test_spawn_none_does_not_raise(tmp_path):
    """When _spawn_new_session is None, _dispatch_handoff_continuation must not raise."""
    mod = _load_dispatcher()
    orig = mod._spawn_new_session
    mod._spawn_new_session = None
    old_err = sys.stderr
    sys.stderr = io.StringIO()
    try:
        mod._dispatch_handoff_continuation()  # must not raise
    finally:
        sys.stderr = old_err
        mod._spawn_new_session = orig


# ---------------------------------------------------------------------------
# _dispatch_handoff_continuation: spawn-failure path must emit visible warning
# ---------------------------------------------------------------------------


def test_spawn_exception_emits_warning(tmp_path):
    """When _spawn_new_session raises, a visible warning must appear on stderr."""
    mod = _load_dispatcher()
    orig_state = mod.STATE_DIR
    mod.STATE_DIR = tmp_path

    # Write a fresh pending-handoff.json with the fields _dispatch_handoff_continuation checks.
    handoff = {
        "triggered_at": time.time(),
        "handoff_id": "test-handoff-spawn-failure",
        "cwd": str(tmp_path),
    }
    (tmp_path / "pending-handoff.json").write_text(json.dumps(handoff), encoding="utf-8")

    def _broken_spawn(cmd, cwd):
        raise RuntimeError("simulated spawn failure")

    orig_spawn = mod._spawn_new_session
    mod._spawn_new_session = _broken_spawn

    captured = io.StringIO()
    old_err = sys.stderr
    sys.stderr = captured
    try:
        mod._dispatch_handoff_continuation()
    finally:
        sys.stderr = old_err
        mod._spawn_new_session = orig_spawn
        mod.STATE_DIR = orig_state

    output = captured.getvalue()
    assert "[DS handoff-spawner]" in output, f"Expected warning tag, got: {output!r}"
    assert (
        "spawn failed" in output.lower() or "simulated" in output.lower()
    ), f"Expected failure context in warning: {output!r}"


def test_spawn_exception_does_not_raise(tmp_path):
    """When _spawn_new_session raises, _dispatch_handoff_continuation must not propagate."""
    mod = _load_dispatcher()
    orig_state = mod.STATE_DIR
    mod.STATE_DIR = tmp_path

    handoff = {"written_at": time.time(), "content": "Test"}
    (tmp_path / "handoff-latest.json").write_text(json.dumps(handoff), encoding="utf-8")

    def _broken_spawn(cmd, cwd):
        raise RuntimeError("simulated spawn failure")

    orig_spawn = mod._spawn_new_session
    mod._spawn_new_session = _broken_spawn
    old_err = sys.stderr
    sys.stderr = io.StringIO()
    try:
        mod._dispatch_handoff_continuation()  # must not raise
    finally:
        sys.stderr = old_err
        mod._spawn_new_session = orig_spawn
        mod.STATE_DIR = orig_state


# ---------------------------------------------------------------------------
# _dispatch_handoff_continuation: stale/missing handoff — no warning, no crash
# ---------------------------------------------------------------------------


def test_no_handoff_file_is_silent(tmp_path):
    """When handoff-latest.json does not exist, no warning is emitted (normal case)."""
    mod = _load_dispatcher()
    orig_state = mod.STATE_DIR
    mod.STATE_DIR = tmp_path
    mock_spawn = MagicMock()
    orig_spawn = mod._spawn_new_session
    mod._spawn_new_session = mock_spawn

    captured = io.StringIO()
    old_err = sys.stderr
    sys.stderr = captured
    try:
        mod._dispatch_handoff_continuation()
    finally:
        sys.stderr = old_err
        mod._spawn_new_session = orig_spawn
        mod.STATE_DIR = orig_state

    mock_spawn.assert_not_called()
    assert captured.getvalue() == "", f"Expected silence, got: {captured.getvalue()!r}"


def test_stale_handoff_is_silent(tmp_path):
    """Handoffs older than 120 s are discarded silently."""
    mod = _load_dispatcher()
    orig_state = mod.STATE_DIR
    mod.STATE_DIR = tmp_path

    handoff = {"written_at": time.time() - 200, "content": "old content"}
    (tmp_path / "handoff-latest.json").write_text(json.dumps(handoff), encoding="utf-8")

    mock_spawn = MagicMock()
    orig_spawn = mod._spawn_new_session
    mod._spawn_new_session = mock_spawn

    captured = io.StringIO()
    old_err = sys.stderr
    sys.stderr = captured
    try:
        mod._dispatch_handoff_continuation()
    finally:
        sys.stderr = old_err
        mod._spawn_new_session = orig_spawn
        mod.STATE_DIR = orig_state

    mock_spawn.assert_not_called()
    assert captured.getvalue() == "", f"Expected silence, got: {captured.getvalue()!r}"


# ---------------------------------------------------------------------------
# _check_handoff_spawner: ds doctor check
# ---------------------------------------------------------------------------


def test_check_handoff_spawner_pass():
    """_check_handoff_spawner returns pass when session_config.py is present and importable."""
    from core.health.doctor import _check_handoff_spawner

    source_root = Path(__file__).parent.parent.parent
    result = _check_handoff_spawner(source_root)
    assert result["status"] == "pass", f"Expected pass, got: {result}"
    assert result["spawn_importable"] is True


def test_check_handoff_spawner_fail_missing(tmp_path):
    """_check_handoff_spawner returns fail when session_config.py does not exist."""
    from core.health.doctor import _check_handoff_spawner

    result = _check_handoff_spawner(tmp_path)
    assert result["status"] == "fail"
    assert result["spawn_importable"] is False


def test_check_handoff_spawner_fail_missing_function(tmp_path):
    """_check_handoff_spawner returns fail when spawn_new_session is absent from the module."""
    from core.health.doctor import _check_handoff_spawner

    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "session_config.py").write_text(
        "# no spawn_new_session here\n", encoding="utf-8"
    )

    result = _check_handoff_spawner(tmp_path)
    assert result["status"] == "fail"
    assert result["spawn_importable"] is False


def test_doctor_checks_includes_handoff_spawner():
    """run_doctor_checks output must include handoff_spawner under checks."""
    from core.health.doctor import run_doctor_checks

    source_root = Path(__file__).parent.parent.parent
    result = run_doctor_checks(source_root=source_root)
    assert (
        "handoff_spawner" in result["checks"]
    ), f"handoff_spawner missing from doctor checks: {list(result['checks'].keys())}"
    assert result["checks"]["handoff_spawner"]["spawn_importable"] is True
