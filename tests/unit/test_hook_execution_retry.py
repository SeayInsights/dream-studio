"""insert_hook_execution retries a locked database; the refusal printer does not.

The once-per-session refusal printer was inserted between `@_with_retry` and
`insert_hook_execution`, so the decorator moved onto the printer and every hook's
execution record lost its retry: a "database is locked" went straight to the
fallback file.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager


def test_a_locked_database_is_retried_not_sent_to_the_fallback(tmp_path, monkeypatch):
    from core.event_store import connection, event_writer_hooks

    attempts: list[int] = []
    emitted: list[str] = []

    @contextmanager
    def flaky_transaction(db_path=None):
        attempts.append(1)
        if len(attempts) == 1:
            raise sqlite3.OperationalError("database is locked")
        yield None

    monkeypatch.setattr(event_writer_hooks, "_db_transaction", flaky_transaction)
    monkeypatch.setattr(
        event_writer_hooks, "_try_emit_canonical", lambda *a, **k: emitted.append(a[0])
    )
    monkeypatch.setattr(connection.time, "sleep", lambda _s: None)
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(tmp_path / "home"))

    result = event_writer_hooks.insert_hook_execution(
        "on-x", "PostToolUse", {}, "2026-10-16T00:00:00+00:00", session_id="s-1"
    )
    assert len(attempts) == 2, "the locked first attempt was not retried"
    assert emitted, "the execution record was never emitted"
    assert result is None
    assert not (tmp_path / "home" / "state" / "hook_executions_fallback.jsonl").exists()


def test_the_refusal_printer_is_not_wrapped_in_the_database_retry():
    from core.event_store import event_writer_hooks

    assert not hasattr(event_writer_hooks._surface_authority_refusal, "__wrapped__")
    assert hasattr(event_writer_hooks.insert_hook_execution, "__wrapped__")
