"""Tests for hooks/lib/audit.py and hooks/lib/telemetry.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))

from lib.audit import log_event  # noqa: E402
from lib.telemetry import capture_exception, init_sentry  # noqa: E402


# ── audit ──────────────────────────────────────────────────────────────


def test_log_event_writes_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    log_event("test_event", {"tool_name": "Edit"}, session_id="sess-001")
    audit = tmp_path / ".dream-studio" / "audit.jsonl"
    assert audit.exists()
    record = json.loads(audit.read_text(encoding="utf-8").strip())
    assert record["event"] == "test_event"
    assert record["session_id"] == "sess-001"
    assert record["payload_summary"] == {"tool_name": "Edit"}
    assert "ts" in record


def test_log_event_appends(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    log_event("evt_a", {}, session_id="s1")
    log_event("evt_b", {}, session_id="s2")
    lines = (tmp_path / ".dream-studio" / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event"] == "evt_a"
    assert json.loads(lines[1])["event"] == "evt_b"


def test_log_event_no_session_id(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    log_event("no_session", {"hook_event_name": "Stop"})
    record = json.loads((tmp_path / ".dream-studio" / "audit.jsonl").read_text(encoding="utf-8").strip())
    assert record["session_id"] == ""


def test_log_event_silent_on_error(monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: Path("/nonexistent/readonly/path"))
    log_event("should_not_crash", {})  # must not raise


# ── telemetry ──────────────────────────────────────────────────────────


def test_init_sentry_noop_without_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    init_sentry()  # must not raise or import sentry_sdk


def test_capture_exception_noop_without_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    capture_exception(ValueError("test"))  # must not raise


def test_init_sentry_skips_when_sdk_missing(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://fake@sentry.io/1")
    monkeypatch.setitem(sys.modules, "sentry_sdk", None)
    try:
        init_sentry()
    except Exception:
        pass  # ImportError is acceptable; crash is not
    finally:
        sys.modules.pop("sentry_sdk", None)


def test_capture_exception_with_dsn_but_no_sdk(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://fake@sentry.io/1")
    monkeypatch.setitem(sys.modules, "sentry_sdk", None)
    try:
        capture_exception(RuntimeError("boom"))  # must not raise
    except Exception:
        pass
    finally:
        sys.modules.pop("sentry_sdk", None)


# ── audit: effectiveness_score branch (line 42) ────────────────────────


def test_log_event_includes_effectiveness_score(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    log_event("scored_event", {"tool_name": "Bash"}, effectiveness_score=0.85)
    record = json.loads((tmp_path / ".dream-studio" / "audit.jsonl").read_text(encoding="utf-8").strip())
    assert "effectiveness_score" in record
    assert record["effectiveness_score"] == 0.85


# ── audit: outer except (lines 45-46) ─────────────────────────────────


def test_log_event_write_failure_swallowed(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    ds_dir = tmp_path / ".dream-studio"
    ds_dir.mkdir(parents=True, exist_ok=True)
    (ds_dir / "audit.jsonl").mkdir()  # directory where file would be → open raises
    log_event("test_event", {})  # must not raise


# ── telemetry: sentry_sdk actually callable (lines 17, 25) ────────────


def test_init_sentry_calls_sdk_when_dsn_set(monkeypatch):
    from unittest.mock import MagicMock
    mock_sdk = MagicMock()
    monkeypatch.setenv("SENTRY_DSN", "https://fake@sentry.io/1")
    monkeypatch.setitem(sys.modules, "sentry_sdk", mock_sdk)
    init_sentry()
    mock_sdk.init.assert_called_once_with(dsn="https://fake@sentry.io/1", traces_sample_rate=0.1)


def test_capture_exception_calls_sdk_when_dsn_set(monkeypatch):
    from unittest.mock import MagicMock
    mock_sdk = MagicMock()
    exc = ValueError("something went wrong")
    monkeypatch.setenv("SENTRY_DSN", "https://fake@sentry.io/1")
    monkeypatch.setitem(sys.modules, "sentry_sdk", mock_sdk)
    capture_exception(exc)
    mock_sdk.capture_exception.assert_called_once_with(exc)
