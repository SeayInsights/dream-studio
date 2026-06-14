"""Integration tests for WO-TOKEN-CAPTURE.

T4-tests: Verifies that TokenConsumptionProjection materializes token.consumed
events from ai_canonical_events into token_usage_records, and that
normalize_stop falls back to the per-session accumulator written by
token_capture.handle_post_tool_use.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_SESSION_ID = "sess-token-test-0001"
_PROJECT_ID = "proj-token-test-000"
_TASK_ID = "task-token-test-0000"
_WO_ID = "wo-token-test-000000"
_NOW = "2026-06-14T12:00:00+00:00"


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def db_path(tmp_path):
    from core.config.sqlite_bootstrap import bootstrap_database

    path = tmp_path / "state" / "studio.db"
    bootstrap_database(path)
    return path


def _seed_token_event(db_path: Path, *, event_id: str | None = None, **payload_overrides) -> str:
    """Insert a token.consumed event into ai_canonical_events. Returns event_id."""
    eid = event_id or str(uuid.uuid4())
    payload = {
        "input_tokens": 100,
        "output_tokens": 50,
        "cache_creation_input_tokens": 10,
        "cache_read_input_tokens": 20,
        "granularity": "tool_invocation",
    }
    payload.update(payload_overrides)
    trace = {
        "project_id": _PROJECT_ID,
        "task_id": _TASK_ID,
        "work_order_id": _WO_ID,
    }
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO ai_canonical_events"
            " (event_id, event_type, event_timestamp, session_id, trace, payload)"
            " VALUES (?, 'token.consumed', ?, ?, ?, ?)",
            (eid, _NOW, _SESSION_ID, json.dumps(trace), json.dumps(payload)),
        )
        conn.commit()
    finally:
        conn.close()
    return eid


# ── T2: TokenConsumptionProjection ────────────────────────────────────────────


class TestTokenConsumptionProjection:
    def test_projection_materializes_event_into_token_usage_records(self, db_path, monkeypatch):
        """A seeded token.consumed event is projected into token_usage_records."""
        monkeypatch.setenv("DS_STUDIO_DB", str(db_path))
        event_id = _seed_token_event(db_path)

        from core.projections.token_projection import TokenConsumptionProjection

        proj = TokenConsumptionProjection()
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            proj.setup_tables(conn)

            # Build a minimal event dict matching the framework's _row_to_event shape.
            event = {
                "event_id": event_id,
                "event_type": "token.consumed",
                "event_timestamp": _NOW,
                "session_id": _SESSION_ID,
                "payload": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_creation_input_tokens": 10,
                    "cache_read_input_tokens": 20,
                    "granularity": "tool_invocation",
                },
                "trace": {
                    "project_id": _PROJECT_ID,
                    "task_id": _TASK_ID,
                    "work_order_id": _WO_ID,
                },
            }
            rows_written = proj.handle(event, conn)
            conn.commit()
        finally:
            conn.close()

        assert rows_written == 1

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM token_usage_records WHERE token_usage_id = ?", (event_id,)
            ).fetchone()
        finally:
            conn.close()

        assert row is not None, "token_usage_records should have a row for the event"
        assert row["input_tokens"] == 100
        assert row["output_tokens"] == 50
        assert row["cached_tokens"] == 10
        assert row["cache_read_tokens"] == 20
        assert row["total_tokens"] == 180  # 100+50+10+20
        assert row["project_id"] == _PROJECT_ID
        assert row["task_id"] == _TASK_ID

    def test_projection_is_idempotent(self, db_path, monkeypatch):
        """Replaying the same event twice produces exactly one row (INSERT OR IGNORE)."""
        monkeypatch.setenv("DS_STUDIO_DB", str(db_path))
        event_id = _seed_token_event(db_path)

        from core.projections.token_projection import TokenConsumptionProjection

        proj = TokenConsumptionProjection()
        event = {
            "event_id": event_id,
            "event_type": "token.consumed",
            "event_timestamp": _NOW,
            "payload": {"input_tokens": 10, "output_tokens": 5},
            "trace": {},
        }
        conn = sqlite3.connect(str(db_path))
        try:
            proj.handle(event, conn)
            proj.handle(event, conn)  # replay
            conn.commit()
            count = conn.execute(
                "SELECT COUNT(*) FROM token_usage_records WHERE token_usage_id = ?", (event_id,)
            ).fetchone()[0]
        finally:
            conn.close()

        assert count == 1, "Duplicate handle() calls must produce exactly one row"

    def test_projection_returns_zero_for_missing_event_id(self, db_path):
        """handle() returns 0 and writes nothing when event_id is absent."""
        from core.projections.token_projection import TokenConsumptionProjection

        proj = TokenConsumptionProjection()
        conn = sqlite3.connect(str(db_path))
        try:
            rows = proj.handle({"event_type": "token.consumed", "payload": {}, "trace": {}}, conn)
        finally:
            conn.close()

        assert rows == 0

    def test_token_usage_records_populated_after_multiple_events(self, db_path, monkeypatch):
        """Multiple seeded events all land in token_usage_records."""
        monkeypatch.setenv("DS_STUDIO_DB", str(db_path))

        from core.projections.token_projection import TokenConsumptionProjection

        proj = TokenConsumptionProjection()
        conn = sqlite3.connect(str(db_path))
        try:
            for i in range(3):
                eid = str(uuid.uuid4())
                proj.handle(
                    {
                        "event_id": eid,
                        "event_type": "token.consumed",
                        "event_timestamp": _NOW,
                        "payload": {"input_tokens": i + 1, "output_tokens": i + 1},
                        "trace": {"project_id": _PROJECT_ID},
                    },
                    conn,
                )
            conn.commit()
            count = conn.execute(
                "SELECT COUNT(*) FROM token_usage_records WHERE project_id = ?", (_PROJECT_ID,)
            ).fetchone()[0]
        finally:
            conn.close()

        assert count == 3


# ── T3: normalize_stop accumulator fallback ───────────────────────────────────


class TestSessionAccumulator:
    def test_update_and_read_accumulator(self, tmp_path, monkeypatch):
        """_update_session_accumulator merges token counts; read returns the total."""
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        session_id = "acc-test-session-001"

        from core.telemetry.token_capture import _update_session_accumulator

        # Two tool calls accumulate.
        _update_session_accumulator(session_id, {"input_tokens": 100, "output_tokens": 50})
        _update_session_accumulator(session_id, {"input_tokens": 200, "output_tokens": 75})

        acc_path = tmp_path / ".dream-studio" / "state" / f"session-tokens-{session_id}.json"
        data = json.loads(acc_path.read_text(encoding="utf-8"))

        assert data["input_tokens"] == 300
        assert data["output_tokens"] == 125

    def test_accumulator_handles_cache_tokens(self, tmp_path, monkeypatch):
        """Cache creation and cache read tokens are accumulated correctly."""
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        session_id = "acc-test-session-002"

        from core.telemetry.token_capture import _update_session_accumulator

        _update_session_accumulator(
            session_id,
            {
                "input_tokens": 10,
                "output_tokens": 5,
                "cache_creation_input_tokens": 20,
                "cache_read_input_tokens": 30,
            },
        )

        acc_path = tmp_path / ".dream-studio" / "state" / f"session-tokens-{session_id}.json"
        data = json.loads(acc_path.read_text(encoding="utf-8"))

        assert data["cache_creation_input_tokens"] == 20
        assert data["cache_read_input_tokens"] == 30

    def test_normalize_stop_reads_accumulator_when_payload_empty(self, tmp_path, monkeypatch):
        """normalize_stop falls back to the session accumulator for token totals."""
        session_id = "stop-test-session-001"
        acc_dir = tmp_path / ".dream-studio" / "state"
        acc_dir.mkdir(parents=True)
        acc_path = acc_dir / f"session-tokens-{session_id}.json"
        acc_path.write_text(
            json.dumps({"input_tokens": 400, "output_tokens": 120}), encoding="utf-8"
        )

        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

        import unittest.mock as mock

        with (
            mock.patch(
                "emitters.claude_code.emitter.get_or_create_session_id", return_value=session_id
            ),
            mock.patch("emitters.claude_code.emitter.get_active_project_id", return_value=None),
            mock.patch("emitters.claude_code.emitter._get_db_path", return_value=None),
        ):
            from emitters.claude_code.emitter import normalize_stop

            # Stop payload with no usage field.
            envelopes = normalize_stop({})

        assert len(envelopes) == 1
        payload = envelopes[0].payload
        assert payload.get("input_tokens") == 400
        assert payload.get("output_tokens") == 120

    def test_normalize_stop_prefers_payload_tokens_over_accumulator(self, tmp_path, monkeypatch):
        """normalize_stop uses Stop payload tokens when present, ignores accumulator."""
        session_id = "stop-test-session-002"
        acc_dir = tmp_path / ".dream-studio" / "state"
        acc_dir.mkdir(parents=True)
        (acc_dir / f"session-tokens-{session_id}.json").write_text(
            json.dumps({"input_tokens": 999, "output_tokens": 999}), encoding="utf-8"
        )

        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

        import unittest.mock as mock

        with (
            mock.patch(
                "emitters.claude_code.emitter.get_or_create_session_id", return_value=session_id
            ),
            mock.patch("emitters.claude_code.emitter.get_active_project_id", return_value=None),
            mock.patch("emitters.claude_code.emitter._get_db_path", return_value=None),
        ):
            from emitters.claude_code.emitter import normalize_stop

            envelopes = normalize_stop({"usage": {"input_tokens": 50, "output_tokens": 30}})

        payload = envelopes[0].payload
        assert payload["input_tokens"] == 50
        assert payload["output_tokens"] == 30


# ── T1: dispatch routing includes core/on-post-tool-use ──────────────────────


def _load_dispatch_hooks():
    """Load .claude/hooks/dispatch/hooks.py by explicit path under a unique name.

    A bare ``import hooks`` resolves to the top-level ``hooks/`` namespace package
    (which has no ``_resolve_handlers``). Once any earlier test in the suite caches
    that module in ``sys.modules``, a later ``import hooks`` returns the cached
    namespace package regardless of ``sys.path`` insertion — so the dispatch module
    is loaded directly from its file path here to avoid the collision. This passed in
    isolation but failed in the full suite (full-ci #359 post-merge).
    """
    import importlib.util  # noqa: PLC0415

    path = REPO_ROOT / ".claude" / "hooks" / "dispatch" / "hooks.py"
    spec = importlib.util.spec_from_file_location("_dispatch_hooks_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestDispatchHookRouting:
    def test_post_tool_use_includes_token_capture_handler(self):
        """_resolve_handlers returns core/on-post-tool-use as first PostToolUse handler."""
        from pathlib import Path as _Path  # noqa: PLC0415

        dispatch_hooks = _load_dispatch_hooks()
        fake_root = _Path("/fake/plugin-root")
        handlers = dispatch_hooks._resolve_handlers("PostToolUse", "Bash", fake_root)
        names = [name for name, _ in handlers]
        assert (
            "on-post-tool-use" in names
        ), f"core/on-post-tool-use missing from PostToolUse handlers; got: {names}"
        assert (
            names[0] == "on-post-tool-use"
        ), f"on-post-tool-use must be first handler; got: {names}"

    def test_post_tool_use_skill_still_gets_skill_handlers(self):
        """Skill tool still gets on-skill-metrics and on-skill-complete in addition to token capture."""
        from pathlib import Path as _Path  # noqa: PLC0415

        dispatch_hooks = _load_dispatch_hooks()
        fake_root = _Path("/fake/plugin-root")
        handlers = dispatch_hooks._resolve_handlers("PostToolUse", "Skill", fake_root)
        names = [name for name, _ in handlers]
        assert "on-post-tool-use" in names
        assert "on-skill-metrics" in names
        assert "on-skill-complete" in names
