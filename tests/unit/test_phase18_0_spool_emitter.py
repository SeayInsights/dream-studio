"""Tests for spool/emitter.py (Phase 18.0, C1)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_emit_returns_true_on_success(spool_root):
    """emit() returns True when the spool write succeeds."""
    from spool.emitter import emit

    result = emit("test.event", {"key": "value"})
    assert result is True


def test_emit_writes_valid_envelope(spool_root):
    """emit() writes a file to the spool with correct event_type and payload."""
    from spool.emitter import emit

    result = emit("ds_session_harvest", {"session_id": "abc123", "pct": 75.0})
    assert result is True

    # Find the written spool file
    pending_files = list(spool_root.glob("**/*.json"))
    assert len(pending_files) == 1

    envelope = json.loads(pending_files[0].read_text(encoding="utf-8"))
    assert envelope["event_type"] == "ds_session_harvest"
    assert envelope["payload"]["session_id"] == "abc123"
    assert envelope["payload"]["pct"] == 75.0
    assert "event_id" in envelope
    assert "timestamp" in envelope
    assert envelope["schema_version"] == 1


def test_emit_returns_false_on_write_failure(spool_root):
    """emit() returns False (does not raise) when spool write fails."""
    from spool.emitter import emit

    with patch("spool.emitter.write_envelopes", side_effect=OSError("disk full")):
        result = emit("test.event", {"key": "value"})

    assert result is False


def test_emit_never_raises(spool_root):
    """emit() must never propagate any exception to the caller."""
    from spool.emitter import emit

    with patch("spool.emitter.write_envelopes", side_effect=RuntimeError("unexpected")):
        # Should not raise — hooks must be non-blocking
        result = emit("test.event", {})

    assert result is False


def test_emit_accepts_session_id(spool_root):
    """emit() passes session_id through to the envelope."""
    from spool.emitter import emit

    result = emit("test.event", {"x": 1}, session_id="sess-42")
    assert result is True

    pending_files = list(spool_root.glob("**/*.json"))
    envelope = json.loads(pending_files[0].read_text(encoding="utf-8"))
    assert envelope["session_id"] == "sess-42"


def test_context_threshold_hook_imports_without_error():
    """on-context-threshold.py must be importable without ImportError."""
    import importlib.util
    import sys

    hook_path = (
        Path(__file__).resolve().parents[2]
        / "runtime"
        / "hooks"
        / "meta"
        / "on-context-threshold.py"
    )
    assert hook_path.is_file(), f"Hook not found at {hook_path}"
    module_name = "on_context_threshold_test_import"
    spec = importlib.util.spec_from_file_location(module_name, hook_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Must not raise ImportError
    spec.loader.exec_module(module)
    assert hasattr(module, "main")
    assert hasattr(module, "_emit_harvest")
