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

    payload = {"session_id": "dup-session"}

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    mod.main()

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    mod.main()

    assert len(calls) == 1


# ── T007: on-session-end ──────────────────────────────────────────────────


def test_session_end_calls_end_session(isolated_home, monkeypatch, handler):
    """main() calls end_session with session_id and outcome from the Stop payload."""
    mod = handler("on-session-end")
    calls: list[tuple] = []
    monkeypatch.setattr(mod, "end_session", lambda *a, **kw: calls.append((a, kw)) or True)
    monkeypatch.setattr(mod, "has_sentinel", lambda k: False)
    monkeypatch.setattr(mod, "set_sentinel", lambda k, c: None)

    payload = {"session_id": "stop-session-xyz", "stop_reason": "end_turn"}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    mod.main()

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == "stop-session-xyz"
    assert kwargs.get("outcome") == "end_turn"


def test_session_end_default_outcome_when_no_stop_reason(isolated_home, monkeypatch, handler):
    """outcome defaults to 'end_turn' when stop_reason absent from payload."""
    mod = handler("on-session-end")
    calls: list[tuple] = []
    monkeypatch.setattr(mod, "end_session", lambda *a, **kw: calls.append((a, kw)) or True)
    monkeypatch.setattr(mod, "has_sentinel", lambda k: False)
    monkeypatch.setattr(mod, "set_sentinel", lambda k, c: None)

    payload = {"session_id": "stop-session-no-reason"}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    mod.main()

    assert len(calls) == 1
    _, kwargs = calls[0]
    assert kwargs.get("outcome") == "end_turn"


def test_session_end_output_tokens_reads_completion_tokens(isolated_home, monkeypatch, handler):
    """output_tokens reads completion_tokens field, not prompt_tokens (copy-paste regression)."""
    mod = handler("on-session-end")
    calls: list[tuple] = []
    monkeypatch.setattr(mod, "end_session", lambda *a, **kw: calls.append((a, kw)) or True)
    monkeypatch.setattr(mod, "has_sentinel", lambda k: False)
    monkeypatch.setattr(mod, "set_sentinel", lambda k, c: None)

    payload = {
        "session_id": "stop-session-tokens",
        "prompt_tokens": 100,
        "completion_tokens": 42,
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    mod.main()

    assert len(calls) == 1
    _, kwargs = calls[0]
    assert kwargs.get("input_tokens") == 100
    assert kwargs.get("output_tokens") == 42


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


# ── T008: on-skill-metrics skill usage ───────────────────────────────────


def test_skill_metrics_writes_skill_usage(isolated_home, monkeypatch, handler):
    """on-skill-metrics calls write_skill_usage with the granular display name.

    The display name strips the 'ds:' prefix and appends the mode,
    so 'ds-core' with args='think' becomes 'core:think'.

    Bug2 regression: insert_token_usage must NOT be called — raw_token_usage
    writes are retired (path b). Token data goes via v2 token_usage_records.
    """
    mod = handler("on-skill-metrics")
    wu_calls: list[tuple] = []
    monkeypatch.setattr(
        mod,
        "write_skill_usage",
        lambda *a: wu_calls.append(a),
    )

    payload = {
        "session_id": "metrics-session",
        "tool_input": {"skill": "ds-core", "args": "think"},
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    mod.main()

    assert len(wu_calls) == 1
    _state_dir, display_name, mode, session_id, _model = wu_calls[0]
    assert display_name == "core:think"
    assert mode == "think"
    assert session_id == "metrics-session"
    assert not hasattr(mod, "insert_token_usage"), "insert_token_usage must not be imported"
