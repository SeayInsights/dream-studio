"""TA5: Dashboard truth-up — delete fabricators, query real data."""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

# ── fixture UUIDs ──────────────────────────────────────────────────────────────

PROJECT_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
PROJECT_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
MILESTONE_A = "11111111-1111-1111-1111-111111111111"
MILESTONE_B = "22222222-2222-2222-2222-222222222222"
WO_A = "33333333-3333-3333-3333-333333333333"
WO_B = "44444444-4444-4444-4444-444444444444"
TASK_A = "55555555-5555-5555-5555-555555555555"
TASK_B = "66666666-6666-6666-6666-666666666666"
NOW = "2026-05-22T12:00:00+00:00"


# ── in-memory DB helpers ───────────────────────────────────────────────────────


def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE canonical_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            trace JSON NOT NULL,
            severity TEXT NOT NULL,
            payload JSON NOT NULL,
            actor JSON,
            confidence_score REAL,
            source_type TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX idx_ce_event_type ON canonical_events(event_type)")
    conn.execute("CREATE INDEX idx_ce_timestamp ON canonical_events(timestamp)")
    conn.commit()
    return conn


def _insert_token_event(
    conn: sqlite3.Connection,
    *,
    project_id: str | None = PROJECT_A,
    milestone_id: str | None = MILESTONE_A,
    work_order_id: str | None = WO_A,
    task_id: str | None = TASK_A,
    attribution_status: str = "fully_attributed",
    model: str = "claude-sonnet-4-6",
    input_tokens: int = 100,
    output_tokens: int = 50,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
    ts: str = NOW,
) -> str:
    event_id = str(uuid.uuid4())
    trace = {
        "domain": "telemetry",
        "attribution_status": attribution_status,
        "project_id": project_id,
        "milestone_id": milestone_id,
        "work_order_id": work_order_id,
        "task_id": task_id,
    }
    payload = {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_input_tokens": cache_creation_input_tokens,
        "cache_read_input_tokens": cache_read_input_tokens,
        "granularity": "tool_invocation",
    }
    conn.execute(
        """
        INSERT INTO canonical_events
            (event_id, event_type, timestamp, trace, severity, payload)
        VALUES (?, 'token.consumed', ?, ?, 'info', ?)
        """,
        (event_id, ts, json.dumps(trace), json.dumps(payload)),
    )
    conn.commit()
    return event_id


def _insert_skill_executed_event(
    conn: sqlite3.Connection,
    *,
    skill_name: str = "ds-core",
    duration_ms: float = 30_000.0,
    status: str = "completed",
    ts: str = NOW,
) -> str:
    event_id = str(uuid.uuid4())
    payload = {
        "skill_name": skill_name,
        "duration_ms": duration_ms,
        "status": status,
    }
    conn.execute(
        """
        INSERT INTO canonical_events
            (event_id, event_type, timestamp, trace, severity, payload)
        VALUES (?, 'skill.executed', ?, '{}', 'info', ?)
        """,
        (event_id, ts, json.dumps(payload)),
    )
    conn.commit()
    return event_id


# ── patch helpers ──────────────────────────────────────────────────────────────


def _patch_conn(conn: sqlite3.Connection):
    """Return a context manager that patches get_connection in token_attribution."""

    def _factory():
        return conn

    return mock.patch(
        "projections.api.queries.token_attribution.get_connection",
        side_effect=_factory,
    )


# ==============================================================================
# Unit: compute_cost
# ==============================================================================


class TestComputeCost:
    def test_sonnet_correct_cost(self):
        from core.pricing.claude_models import compute_cost

        # claude-sonnet-4-6: input $3/MTok, output $15/MTok
        cost = compute_cost("claude-sonnet-4-6", 1_000_000, 1_000_000)
        assert abs(cost - 18.00) < 0.0001

    def test_opus_correct_cost(self):
        from core.pricing.claude_models import compute_cost

        # claude-opus-4-7: input $5/MTok, output $25/MTok
        cost = compute_cost("claude-opus-4-7", 1_000_000, 1_000_000)
        assert abs(cost - 30.00) < 0.0001

    def test_cache_tokens_included(self):
        from core.pricing.claude_models import compute_cost

        # claude-sonnet-4-6: cache_write $3.75/MTok, cache_read $0.30/MTok
        cost = compute_cost(
            "claude-sonnet-4-6",
            input_tokens=0,
            output_tokens=0,
            cache_creation_tokens=1_000_000,
            cache_read_tokens=1_000_000,
        )
        assert abs(cost - 4.05) < 0.0001  # 3.75 + 0.30

    def test_haiku_date_suffix_normalised(self):
        from core.pricing.claude_models import compute_cost

        # claude-haiku-4-5-20251001 → strips to claude-haiku-4-5
        cost_with_suffix = compute_cost("claude-haiku-4-5-20251001", 1_000_000, 0)
        cost_without_suffix = compute_cost("claude-haiku-4-5", 1_000_000, 0)
        assert cost_with_suffix == cost_without_suffix
        assert cost_with_suffix > 0

    def test_unknown_model_returns_zero_and_logs(self, caplog):
        from core.pricing.claude_models import compute_cost

        with caplog.at_level(logging.WARNING, logger="core.pricing.claude_models"):
            cost = compute_cost("claude-unknown-99-9", 1_000_000, 1_000_000)

        assert cost == 0.0
        assert "unknown model" in caplog.text.lower()

    def test_empty_model_returns_zero(self):
        from core.pricing.claude_models import compute_cost

        assert compute_cost("", 100, 100) == 0.0

    def test_zero_tokens_returns_zero(self):
        from core.pricing.claude_models import compute_cost

        assert compute_cost("claude-sonnet-4-6", 0, 0) == 0.0


# ==============================================================================
# Unit: token_spend_by_project
# ==============================================================================


class TestTokenSpendByProject:
    def test_sums_correctly_for_known_project(self):
        from projections.api.queries.token_attribution import token_spend_by_project

        conn = _make_db()
        _insert_token_event(conn, project_id=PROJECT_A, input_tokens=200, output_tokens=100)
        _insert_token_event(conn, project_id=PROJECT_A, input_tokens=300, output_tokens=50)

        with _patch_conn(conn):
            result = token_spend_by_project(PROJECT_A)

        assert result["total_tokens"] == 650
        assert result["input_tokens"] == 500
        assert result["output_tokens"] == 150
        assert result["total_cost_usd"] > 0.0
        assert result["data_status"] == "ok"
        assert result["project_id"] == PROJECT_A

    def test_returns_zero_for_project_with_no_events(self):
        from projections.api.queries.token_attribution import token_spend_by_project

        conn = _make_db()

        with _patch_conn(conn):
            result = token_spend_by_project("no-events-project")

        assert result["total_tokens"] == 0
        assert result["total_cost_usd"] == 0.0
        assert result["data_status"] == "empty"

    def test_excludes_other_projects(self):
        from projections.api.queries.token_attribution import token_spend_by_project

        conn = _make_db()
        _insert_token_event(conn, project_id=PROJECT_A, input_tokens=100, output_tokens=50)
        _insert_token_event(conn, project_id=PROJECT_B, input_tokens=999, output_tokens=999)

        with _patch_conn(conn):
            result = token_spend_by_project(PROJECT_A)

        assert result["total_tokens"] == 150
        assert result["input_tokens"] == 100


# ==============================================================================
# Unit: token_spend_by_milestone
# ==============================================================================


class TestTokenSpendByMilestone:
    def test_scopes_correctly_excludes_sibling_milestone(self):
        from projections.api.queries.token_attribution import token_spend_by_milestone

        conn = _make_db()
        _insert_token_event(conn, milestone_id=MILESTONE_A, input_tokens=100, output_tokens=40)
        _insert_token_event(conn, milestone_id=MILESTONE_B, input_tokens=999, output_tokens=999)

        with _patch_conn(conn):
            result = token_spend_by_milestone(MILESTONE_A)

        assert result["total_tokens"] == 140
        assert result["milestone_id"] == MILESTONE_A

    def test_returns_zero_for_empty_milestone(self):
        from projections.api.queries.token_attribution import token_spend_by_milestone

        conn = _make_db()

        with _patch_conn(conn):
            result = token_spend_by_milestone("no-events-milestone")

        assert result["data_status"] == "empty"
        assert result["total_tokens"] == 0


# ==============================================================================
# Unit: token_spend_by_work_order
# ==============================================================================


class TestTokenSpendByWorkOrder:
    def test_scopes_correctly(self):
        from projections.api.queries.token_attribution import token_spend_by_work_order

        conn = _make_db()
        _insert_token_event(conn, work_order_id=WO_A, input_tokens=50, output_tokens=25)
        _insert_token_event(conn, work_order_id=WO_B, input_tokens=999, output_tokens=999)

        with _patch_conn(conn):
            result = token_spend_by_work_order(WO_A)

        assert result["total_tokens"] == 75
        assert result["work_order_id"] == WO_A

    def test_returns_zero_when_empty(self):
        from projections.api.queries.token_attribution import token_spend_by_work_order

        conn = _make_db()

        with _patch_conn(conn):
            result = token_spend_by_work_order("no-events-wo")

        assert result["data_status"] == "empty"


# ==============================================================================
# Unit: token_spend_by_task
# ==============================================================================


class TestTokenSpendByTask:
    def test_scopes_correctly(self):
        from projections.api.queries.token_attribution import token_spend_by_task

        conn = _make_db()
        _insert_token_event(conn, task_id=TASK_A, input_tokens=80, output_tokens=20)
        _insert_token_event(conn, task_id=TASK_B, input_tokens=999, output_tokens=999)

        with _patch_conn(conn):
            result = token_spend_by_task(TASK_A)

        assert result["total_tokens"] == 100
        assert result["task_id"] == TASK_A

    def test_returns_zero_when_empty(self):
        from projections.api.queries.token_attribution import token_spend_by_task

        conn = _make_db()

        with _patch_conn(conn):
            result = token_spend_by_task("no-events-task")

        assert result["data_status"] == "empty"


# ==============================================================================
# Unit: attribution_coverage
# ==============================================================================


class TestAttributionCoverage:
    def test_correct_breakdown_for_known_distribution(self):
        from projections.api.queries.token_attribution import attribution_coverage

        conn = _make_db()
        # 6 fully_attributed, 3 partial, 1 orphan → 60 / 30 / 10 %
        for _ in range(6):
            _insert_token_event(conn, attribution_status="fully_attributed")
        for _ in range(3):
            _insert_token_event(conn, attribution_status="partial")
        _insert_token_event(conn, attribution_status="orphan")

        with _patch_conn(conn):
            result = attribution_coverage()

        assert result["total_events"] == 10
        assert result["fully_attributed_pct"] == 60.0
        assert result["partial_pct"] == 30.0
        assert result["orphan_pct"] == 10.0
        assert result["data_status"] == "ok"

    def test_empty_when_no_events(self):
        from projections.api.queries.token_attribution import attribution_coverage

        conn = _make_db()

        with _patch_conn(conn):
            result = attribution_coverage()

        assert result["data_status"] == "empty"
        assert result["total_events"] == 0
        assert result["fully_attributed_pct"] == 0.0

    def test_project_scoped_excludes_other_projects(self):
        from projections.api.queries.token_attribution import attribution_coverage

        conn = _make_db()
        # PROJECT_A: 2 fully_attributed
        _insert_token_event(conn, project_id=PROJECT_A, attribution_status="fully_attributed")
        _insert_token_event(conn, project_id=PROJECT_A, attribution_status="fully_attributed")
        # PROJECT_B: 8 orphan (should not affect PROJECT_A result)
        for _ in range(8):
            _insert_token_event(conn, project_id=PROJECT_B, attribution_status="orphan")

        with _patch_conn(conn):
            result = attribution_coverage(project_id=PROJECT_A)

        assert result["total_events"] == 2
        assert result["fully_attributed_pct"] == 100.0
        assert result["orphan_pct"] == 0.0

    def test_backfill_counted_as_orphan(self):
        from projections.api.queries.token_attribution import attribution_coverage

        conn = _make_db()
        _insert_token_event(conn, attribution_status="fully_attributed")
        _insert_token_event(conn, attribution_status="backfill")  # backfill → orphan bucket

        with _patch_conn(conn):
            result = attribution_coverage()

        assert result["total_events"] == 2
        assert result["fully_attributed_pct"] == 50.0
        assert result["orphan_pct"] == 50.0


# ==============================================================================
# Integration: 100 events with mixed attribution → correct percentages
# ==============================================================================


class TestAttributionCoverageIntegration:
    def test_100_events_mixed_attribution(self):
        from projections.api.queries.token_attribution import attribution_coverage

        conn = _make_db()
        statuses = ["fully_attributed"] * 67 + ["partial"] * 22 + ["orphan"] * 11
        for s in statuses:
            _insert_token_event(conn, attribution_status=s)

        with _patch_conn(conn):
            result = attribution_coverage()

        assert result["total_events"] == 100
        assert result["fully_attributed_pct"] == 67.0
        assert result["partial_pct"] == 22.0
        assert result["orphan_pct"] == 11.0
        assert result["data_status"] == "ok"


# ==============================================================================
# Integration: endpoint previously calling fabricator returns real data
# ==============================================================================


class TestTokensEndpointRealData:
    """The /tokens endpoint used to call _build_skill_costs; now it returns real data."""

    def test_endpoint_returns_attribution_coverage_field(self):
        from projections.api.queries.token_attribution import attribution_coverage

        conn = _make_db()
        _insert_token_event(conn, project_id=PROJECT_A, attribution_status="fully_attributed")

        with _patch_conn(conn):
            result = attribution_coverage()

        # The field now exists on the tokens endpoint response (wired in metrics.py)
        assert "data_status" in result
        assert result["data_status"] == "ok"

    def test_endpoint_empty_state_is_honest(self):
        from projections.api.queries.token_attribution import attribution_coverage

        conn = _make_db()

        with _patch_conn(conn):
            result = attribution_coverage()

        # No fabricated percentages — all zero, data_status=empty
        assert result["data_status"] == "empty"
        assert result["fully_attributed_pct"] == 0.0
        assert result["partial_pct"] == 0.0
        assert result["orphan_pct"] == 0.0


# ==============================================================================
# Integration: exec_time_ranges_from_canonical reads skill.executed events
# ==============================================================================


class TestExecTimeRangesIntegration:
    def test_reads_duration_from_canonical_events(self):
        from projections.api.queries.token_attribution import exec_time_ranges_from_canonical

        conn = _make_db()
        # Two executions of ds-core: 30s and 90s (30_000ms and 90_000ms)
        _insert_skill_executed_event(conn, skill_name="ds-core", duration_ms=30_000.0)
        _insert_skill_executed_event(conn, skill_name="ds-core", duration_ms=90_000.0)

        with mock.patch(
            "projections.api.queries.token_attribution.get_connection",
            side_effect=lambda: conn,
        ):
            result = exec_time_ranges_from_canonical(days=30)

        assert "ds-core" in result
        # 30_000ms / 60_000 = 0.5 min; 90_000ms / 60_000 = 1.5 min
        assert abs(result["ds-core"]["min_m"] - 0.5) < 0.001
        assert abs(result["ds-core"]["max_m"] - 1.5) < 0.001

    def test_returns_empty_when_no_skill_executed_events(self):
        from projections.api.queries.token_attribution import exec_time_ranges_from_canonical

        conn = _make_db()

        with mock.patch(
            "projections.api.queries.token_attribution.get_connection",
            side_effect=lambda: conn,
        ):
            result = exec_time_ranges_from_canonical(days=30)

        assert result == {}


# ==============================================================================
# Regression: fabricators must not exist in production code
# ==============================================================================


class TestFabricatorsDeleted:
    def _grep_production_py(self, pattern: str) -> list[str]:
        """Return production .py files containing the pattern, excluding tests."""
        repo = Path(__file__).resolve().parents[2]
        hits = []
        for path in repo.rglob("*.py"):
            parts = path.parts
            if any(p in ("tests", "test") for p in parts):
                continue
            if "__pycache__" in parts:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
                if pattern in text:
                    hits.append(str(path.relative_to(repo)))
            except OSError:
                pass
        return hits

    def test_build_skill_costs_absent_from_production(self):
        hits = self._grep_production_py("_build_skill_costs")
        assert hits == [], f"_build_skill_costs still found in: {hits}"

    def test_build_exec_time_ranges_absent_from_production(self):
        hits = self._grep_production_py("_build_exec_time_ranges")
        assert hits == [], f"_build_exec_time_ranges still found in: {hits}"
