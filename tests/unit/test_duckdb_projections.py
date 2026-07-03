"""Tests for DuckDB execution event projection (WO-TS3 task 7)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

from core.analytics.duckdb_store import connect_analytics, ensure_analytics_schema  # noqa: E402
from core.projections.duckdb_projections import dispatch_to_duckdb  # noqa: E402


def _db(tmp_path: Path):
    db = tmp_path / "agg.db"
    conn = connect_analytics(db, read_only=False)
    ensure_analytics_schema(conn)
    return conn


def _evt(event_type, **kwargs):
    base = {
        "event_id": "evt-001",
        "event_type": event_type,
        "event_timestamp": "2026-01-01T00:00:00",
        "trace": {},
        "payload": {},
    }
    base.update(kwargs)
    return base


class TestExecutionEventProjection:
    def test_execution_started_inserted(self, tmp_path):
        conn = _db(tmp_path)
        dispatch_to_duckdb(
            _evt(
                "execution.started",
                event_id="exec-1",
                session_id="sess-1",
                trace={"project_id": "proj-1", "skill_id": "sk-1"},
                payload={"event_name": "skill_invoke"},
            ),
            conn,
        )
        row = conn.execute(
            "SELECT event_type, event_name, project_id, skill_id, outcome_status"
            " FROM duckdb_execution_events WHERE event_id='exec-1'"
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "execution.started"
        assert row[1] == "skill_invoke"
        assert row[2] == "proj-1"
        assert row[3] == "sk-1"
        assert row[4] is None

    def test_execution_completed_captures_outcome(self, tmp_path):
        conn = _db(tmp_path)
        dispatch_to_duckdb(
            _evt(
                "execution.completed",
                event_id="exec-2",
                trace={"project_id": "proj-2", "tool_id": "tool-x"},
                payload={"event_name": "tool_use", "outcome_status": "success"},
            ),
            conn,
        )
        row = conn.execute(
            "SELECT outcome_status, tool_id FROM duckdb_execution_events WHERE event_id='exec-2'"
        ).fetchone()
        conn.close()
        assert row[0] == "success"
        assert row[1] == "tool-x"

    def test_execution_failed_creates_row(self, tmp_path):
        conn = _db(tmp_path)
        dispatch_to_duckdb(
            _evt(
                "execution.failed",
                event_id="exec-3",
                trace={"workflow_id": "wf-1"},
                payload={"event_name": "workflow_run", "outcome_status": "error"},
            ),
            conn,
        )
        row = conn.execute(
            "SELECT event_type, outcome_status FROM duckdb_execution_events WHERE event_id='exec-3'"
        ).fetchone()
        conn.close()
        assert row[0] == "execution.failed"
        assert row[1] == "error"

    def test_dispatch_routes_execution_event(self, tmp_path):
        conn = _db(tmp_path)
        result = dispatch_to_duckdb(
            _evt("execution.started", event_id="exec-4", payload={"event_name": "hook_run"}),
            conn,
        )
        conn.close()
        assert result == 1

    def test_non_execution_event_not_routed(self, tmp_path):
        conn = _db(tmp_path)
        result = dispatch_to_duckdb(
            _evt("tool.execution.completed", event_id="exec-5"),
            conn,
        )
        conn.close()
        assert result == 0

    def test_unknown_event_type_silent(self, tmp_path):
        conn = _db(tmp_path)
        result = dispatch_to_duckdb(_evt("unknown.x"), conn)
        conn.close()
        assert result == 0


class TestTokenViewWiden:
    """WO-TOKEN-VIEW-WIDEN: token_usage_records derives model/cache/cost from
    the ai-canonical token.consumed payload keys instead of hardcoded NULLs."""

    def _seed_token_event(self, conn, event_id, payload, model_id=None):
        import json

        conn.execute(
            "INSERT INTO events_fact (event_id, event_type, event_timestamp,"
            " input_tokens, output_tokens, model_id, payload)"
            " VALUES (?, 'token.consumed', '2026-07-01T00:00:00', ?, ?, ?, ?)",
            [
                event_id,
                payload.get("input_tokens"),
                payload.get("output_tokens"),
                model_id,
                json.dumps(payload),
            ],
        )

    def test_model_and_cache_extracted_from_payload(self, tmp_path):
        conn = _db(tmp_path)
        self._seed_token_event(
            conn,
            "tok-1",
            {
                "input_tokens": 100,
                "output_tokens": 200,
                "model": "claude-opus-4-8",
                "cache_creation_input_tokens": 1000,
                "cache_read_input_tokens": 50000,
            },
        )
        row = conn.execute(
            "SELECT model_id, cached_tokens, cache_read_tokens, estimated_cost"
            " FROM token_usage_records WHERE token_usage_id = 'tok-1'"
        ).fetchone()
        conn.close()
        assert row[0] == "claude-opus-4-8"
        assert row[1] == 1000
        assert row[2] == 50000
        # Same arithmetic as core.pricing.claude_models.compute_cost
        from core.pricing.claude_models import compute_cost

        assert row[3] == pytest.approx(compute_cost("claude-opus-4-8", 100, 200, 1000, 50000))

    def test_dated_model_suffix_normalized_for_pricing(self, tmp_path):
        conn = _db(tmp_path)
        self._seed_token_event(
            conn,
            "tok-2",
            {"input_tokens": 10, "output_tokens": 10, "model": "claude-haiku-4-5-20251001"},
        )
        row = conn.execute(
            "SELECT model_id, estimated_cost FROM token_usage_records"
            " WHERE token_usage_id = 'tok-2'"
        ).fetchone()
        conn.close()
        assert row[0] == "claude-haiku-4-5-20251001"  # raw id preserved
        from core.pricing.claude_models import compute_cost

        assert row[1] == pytest.approx(compute_cost("claude-haiku-4-5-20251001", 10, 10))

    def test_model_less_event_stays_null_cost(self, tmp_path):
        conn = _db(tmp_path)
        self._seed_token_event(conn, "tok-3", {"input_tokens": 5, "output_tokens": 5})
        row = conn.execute(
            "SELECT model_id, cached_tokens, estimated_cost FROM token_usage_records"
            " WHERE token_usage_id = 'tok-3'"
        ).fetchone()
        conn.close()
        assert row[0] is None
        assert row[1] is None
        assert row[2] is None  # unknown model: cost unknown, never fabricated

    def test_fact_column_model_id_wins_over_payload(self, tmp_path):
        conn = _db(tmp_path)
        self._seed_token_event(
            conn,
            "tok-4",
            {"input_tokens": 1, "output_tokens": 1, "model": "claude-opus-4-8"},
            model_id="claude-sonnet-4-6",
        )
        row = conn.execute(
            "SELECT model_id FROM token_usage_records WHERE token_usage_id = 'tok-4'"
        ).fetchone()
        conn.close()
        assert row[0] == "claude-sonnet-4-6"

    def test_pricing_table_refreshes_on_schema_ensure(self, tmp_path):
        from core.pricing.claude_models import CLAUDE_MODEL_PRICING

        conn = _db(tmp_path)
        n = conn.execute("SELECT COUNT(*) FROM token_model_pricing").fetchone()[0]
        assert n == len(CLAUDE_MODEL_PRICING)
        # idempotent re-ensure
        ensure_analytics_schema(conn)
        n2 = conn.execute("SELECT COUNT(*) FROM token_model_pricing").fetchone()[0]
        conn.close()
        assert n2 == n
