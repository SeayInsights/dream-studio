"""Unit tests for on-session-start.py session config writing."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO = Path(__file__).resolve().parents[3]
_SESSION_CONFIG = _REPO / "runtime" / "session_config.py"


def _load_session_config():
    import importlib.util
    spec = importlib.util.spec_from_file_location("session_config", _SESSION_CONFIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def sc():
    return _load_session_config()


def test_session_config_written_on_start(sc, tmp_path):
    """write_session_config creates a temp file with the expected keys."""
    session_id = "test-session-abc"
    data = {
        "session_id": session_id,
        "invocation_flags": ["--dangerously-skip-permissions"],
        "cwd": str(tmp_path),
        "timestamp": 1000,
        "continuation_count": 0,
    }

    # Override tempdir so we can find the file reliably
    with patch("tempfile.gettempdir", return_value=str(tmp_path)):
        sc.write_session_config(session_id, data)
        result = sc.read_session_config(session_id)

    assert result["session_id"] == session_id
    assert "--dangerously-skip-permissions" in result["invocation_flags"]
    assert result["continuation_count"] == 0


def test_read_session_config_returns_empty_when_missing(sc, tmp_path):
    """read_session_config returns empty dict for unknown session_id."""
    with patch("tempfile.gettempdir", return_value=str(tmp_path)):
        result = sc.read_session_config("no-such-session")
    assert result == {}


def test_detect_flags_returns_list(sc):
    """detect_invocation_flags always returns a list (empty is fine in test context)."""
    flags = sc.detect_invocation_flags()
    assert isinstance(flags, list)
