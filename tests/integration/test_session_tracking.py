"""Integration tests for T007-T009: real-time session tracking hooks."""

from __future__ import annotations

import io
import json


# ── T007: on-session-start ─────────────────────────────────────────────────


def test_session_start_inserts_session(isolated_home, monkeypatch, handler):
    """main() calls insert_session with the session_id from the payload."""
    mod = handler("on-session-start")
    calls: list[tuple] = []
    monkeypatch.setattr(mod, "insert_session", lambda *a, **kw: calls.append((a, kw)) or True)
    monkeypatch.setattr(mod, "has_sentinel", lambda k: False)
    monkeypatch.setattr(mod, "set_sentinel", lambda k, c: None)
    monkeypatch.setattr(mod, "upsert_project", lambda *a, **kw: True)

    payload = {"session_id": "test-session-abc"}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    mod.main()

    assert len(calls) == 1
    args, _kwargs = calls[0]
    assert args[0] == "test-session-abc"


def test_session_start_generates_uuid_when_no_session_id(isolated_home, monkeypatch, handler):
    """When no session_id is in payload or env, a UUID is generated and passed."""
    mod = handler("on-session-start")
    calls: list[tuple] = []
    monkeypatch.setattr(mod, "insert_session", lambda *a, **kw: calls.append((a, kw)) or True)
    monkeypatch.setattr(mod, "has_sentinel", lambda k: False)
    monkeypatch.setattr(mod, "set_sentinel", lambda k, c: None)
    monkeypatch.setattr(mod, "upsert_project", lambda *a, **kw: True)
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({})))
    mod.main()

    assert len(calls) == 1
    args, _kwargs = calls[0]
    generated_id = args[0]
    # Must be a non-empty string that looks like a UUID (8-4-4-4-12)
    import re
    assert re.match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        generated_id,
    ), f"Expected UUID, got: {generated_id!r}"


def test_session_start_sentinel_prevents_double_fire(isolated_home, monkeypatch, handler):
    """Calling main() twice fires insert_session only once (sentinel blocks second call)."""
    mod = handler("on-session-start")
    calls: list[tuple] = []
    sentinel_store: set[str] = set()

    def _has(k: str) -> bool:
        return k in sentinel_store

    def _set(k: str, c: str) -> None:
        sentinel_store.add(k)

    monkeypatch.setattr(mod, "insert_session", lambda *a, **kw: calls.append((a, kw)) or True)
    monkeypatch.setattr(mod, "has_sentinel", _has)
    monkeypatch.setattr(mod, "set_sentinel", _set)
    monkeypatch.setattr(mod, "upsert_project", lambda *a, **kw: True)

    payload = {"session_id": "dup-session"}

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    mod.main()

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    mod.main()

    assert len(calls) == 1


# ── T007: on-session-end ──────────────────────────────────────────────────


def test_session_end_calls_end_session(isolated_home, monkeypatch, handler):
    """main() calls end_session with the session_id from the Stop payload."""
    mod = handler("on-session-end")
    calls: list[tuple] = []
    monkeypatch.setattr(mod, "end_session", lambda *a, **kw: calls.append((a, kw)) or True)
    monkeypatch.setattr(mod, "has_sentinel", lambda k: False)
    monkeypatch.setattr(mod, "set_sentinel", lambda k, c: None)

    payload = {"session_id": "stop-session-xyz"}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    mod.main()

    assert len(calls) == 1
    args, _kwargs = calls[0]
    assert args[0] == "stop-session-xyz"


def test_session_end_sentinel_prevents_double_fire(isolated_home, monkeypatch, handler):
    """Calling main() twice fires end_session only once."""
    mod = handler("on-session-end")
    calls: list[tuple] = []
    sentinel_store: set[str] = set()

    def _has(k: str) -> bool:
        return k in sentinel_store

    def _set(k: str, c: str) -> None:
        sentinel_store.add(k)

    monkeypatch.setattr(mod, "end_session", lambda *a, **kw: calls.append((a, kw)) or True)
    monkeypatch.setattr(mod, "has_sentinel", _has)
    monkeypatch.setattr(mod, "set_sentinel", _set)

    payload = {"session_id": "dup-end-session"}

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    mod.main()

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    mod.main()

    assert len(calls) == 1


def test_session_end_graceful_without_session_id(isolated_home, monkeypatch, handler):
    """Empty payload (no session_id) does not crash and skips end_session."""
    mod = handler("on-session-end")
    calls: list[tuple] = []
    monkeypatch.setattr(mod, "end_session", lambda *a, **kw: calls.append((a, kw)) or True)
    monkeypatch.setattr(mod, "has_sentinel", lambda k: False)
    monkeypatch.setattr(mod, "set_sentinel", lambda k, c: None)

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({})))
    mod.main()  # must not raise

    assert calls == []


# ── T008: on-skill-metrics token usage ───────────────────────────────────


def test_skill_metrics_inserts_token_usage(isolated_home, monkeypatch, handler):
    """on-skill-metrics calls insert_token_usage with the granular display name.

    The display name strips the 'dream-studio:' prefix and appends the mode,
    so 'dream-studio:core' with args='think' becomes 'core:think'.
    """
    mod = handler("on-skill-metrics")
    tu_calls: list[dict] = []
    monkeypatch.setattr(
        mod,
        "insert_token_usage",
        lambda **kw: tu_calls.append(kw) or True,
    )

    payload = {
        "session_id": "metrics-session",
        "tool_input": {"skill": "dream-studio:core", "args": "think"},
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    mod.main()

    assert len(tu_calls) == 1
    call = tu_calls[0]
    assert call["session_id"] == "metrics-session"
    assert call["skill_name"] == "core:think"
    assert call["input_tokens"] == 0
    assert call["output_tokens"] == 0
