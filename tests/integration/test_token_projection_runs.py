"""AC-named tests for WO-TOKEN-BACKFILL — token.consumed projection on the live flow.

Acceptance criteria (business_tasks.acceptance_criteria):
  - T2: tests/integration/test_token_projection_runs.py::test_new_token_event_materializes_via_sync
  - T4: tests/integration/test_token_projection_runs.py::test_end_to_end

token_usage_records was empty because TokenConsumptionProjection ran only in the
dormant projection daemon. sync_tick() now registers it alongside the SDLC
projections (core/projections/runner.py), so token.consumed events emitted on the
live flow materialize into token_usage_records — the table the dashboard's
Cost-Over-Time / Model-Distribution surfaces read.
"""

from __future__ import annotations

import json
import sqlite3
import uuid

import pytest

_NOW = "2026-06-15T00:00:00+00:00"


def _reset_db_runtime() -> None:
    from core.config.database import DatabaseRuntime

    DatabaseRuntime.reset_instance()


@pytest.fixture
def live_like_db(tmp_path, monkeypatch):
    """A bootstrapped studio.db wired as the resolved authority for the engine.

    The projection engine resolves its connection via DREAM_STUDIO_DB_PATH +
    the DatabaseRuntime singleton, so both the env var and a singleton reset are
    required for sync_tick() to read/write this temp DB rather than the live one.
    """
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    _reset_db_runtime()

    from core.config.sqlite_bootstrap import bootstrap_database

    bootstrap_database(db)
    yield db
    _reset_db_runtime()


def _seed_token_event(
    db, *, input_tokens, output_tokens, project_id="p-ac", model="claude-opus-4-8"
):
    """Insert a token.consumed event into ai_canonical_events. Returns event_id."""
    eid = str(uuid.uuid4())
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO ai_canonical_events"
            " (event_id, event_type, event_timestamp, session_id, trace, payload)"
            " VALUES (?, 'token.consumed', ?, ?, ?, ?)",
            (
                eid,
                _NOW,
                "sess-ac",
                json.dumps({"project_id": project_id}),
                json.dumps(
                    {"input_tokens": input_tokens, "output_tokens": output_tokens, "model": model}
                ),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return eid


def test_new_token_event_materializes_via_sync(live_like_db):
    """T2: a token.consumed event materializes into token_usage_records via sync_tick().

    Regression guard against the projection running only in the dormant daemon.
    """
    event_id = _seed_token_event(live_like_db, input_tokens=100, output_tokens=50)

    from core.projections.runner import sync_tick

    sync_tick()

    conn = sqlite3.connect(str(live_like_db))
    try:
        row = conn.execute(
            "SELECT input_tokens, output_tokens, total_tokens"
            " FROM token_usage_records WHERE token_usage_id = ?",
            (event_id,),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None, "token.consumed must materialize via the live sync_tick path"
    assert row == (100, 50, 150)


def test_end_to_end(live_like_db):
    """T4: multiple token.consumed events project end-to-end with correct aggregates.

    Exercises the full canonical → projection → read-model path the dashboard
    reads, plus idempotency (a second tick must not duplicate rows).
    """
    _seed_token_event(live_like_db, input_tokens=100, output_tokens=50)
    _seed_token_event(live_like_db, input_tokens=200, output_tokens=75)
    _seed_token_event(live_like_db, input_tokens=10, output_tokens=5)

    from core.projections.runner import sync_tick

    sync_tick()

    conn = sqlite3.connect(str(live_like_db))
    try:
        count = conn.execute("SELECT COUNT(*) FROM token_usage_records").fetchone()[0]
        total = conn.execute(
            "SELECT COALESCE(SUM(total_tokens), 0) FROM token_usage_records"
        ).fetchone()[0]
    finally:
        conn.close()

    assert count == 3
    assert total == 150 + 275 + 15  # 440

    # Idempotent: re-running the tick must not duplicate rows.
    sync_tick()
    conn = sqlite3.connect(str(live_like_db))
    try:
        count_after = conn.execute("SELECT COUNT(*) FROM token_usage_records").fetchone()[0]
    finally:
        conn.close()
    assert count_after == 3, "re-running sync_tick must not duplicate token rows"
