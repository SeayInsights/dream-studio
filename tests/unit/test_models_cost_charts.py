"""Tests for WO-DASH-ATTRIBUTION-SURFACES T3: cost-by-model populates with non-zero values for known models."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _make_bare_conn() -> sqlite3.Connection:
    """Return a bare in-memory SQLite connection (no token_usage_records table).

    WO-DBA-DROP (migration 137): token_usage_records is retired from SQLite —
    api_equivalent_cost() falls through to the DuckDB aggregate_metrics.db
    view; seed it via _seed_duckdb_tokens() before calling this.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _seed_duckdb_tokens(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Seed two token.consumed events each for claude-opus-4-8 and
    claude-sonnet-4-6 (5000/2000/0/0, matching the retired SQLite fixture)
    into an isolated DuckDB analytics store's events_fact."""
    from core.analytics import duckdb_store

    analytics_db = tmp_path / "aggregate_metrics.db"
    monkeypatch.setattr(duckdb_store, "analytics_db_path", lambda: analytics_db)
    conn = duckdb_store.connect_analytics(analytics_db, read_only=False)
    try:
        duckdb_store.ensure_analytics_schema(conn)
        for i, model in enumerate(
            ["claude-opus-4-8", "claude-opus-4-8", "claude-sonnet-4-6", "claude-sonnet-4-6"]
        ):
            conn.execute(
                "INSERT INTO events_fact (event_id, event_type, event_timestamp, model_id,"
                " input_tokens, output_tokens, payload)"
                " VALUES (?, 'token.consumed', '2026-07-03T00:00:00Z', ?, 5000, 2000, '{}')",
                [f"tok-{i}", model],
            )
    finally:
        conn.close()


def test_cost_by_model_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify api_equivalent_cost returns non-zero costs for known models with seeded token data."""
    from projections.core.cost_analysis import api_equivalent_cost

    _seed_duckdb_tokens(monkeypatch, tmp_path)
    conn = _make_bare_conn()
    result = api_equivalent_cost(conn)
    conn.close()

    assert (
        result["total_usd"] > 0.0
    ), f"total_usd should be > 0 for known models with token data, got {result['total_usd']!r}"
    assert (
        result["priced_record_count"] == 4
    ), f"Expected 4 priced records, got {result['priced_record_count']!r}"
    assert (
        result["unpriced_record_count"] == 0
    ), f"Expected 0 unpriced records, got {result['unpriced_record_count']!r}"

    model_ids = {entry["model_id"] for entry in result["by_model"]}
    assert (
        "claude-opus-4-8" in model_ids
    ), f"claude-opus-4-8 not found in by_model. Got: {model_ids!r}"
    assert (
        "claude-sonnet-4-6" in model_ids
    ), f"claude-sonnet-4-6 not found in by_model. Got: {model_ids!r}"

    for entry in result["by_model"]:
        assert (
            entry["usd"] > 0.0
        ), f"Expected usd > 0 for model {entry['model_id']!r}, got {entry['usd']!r}"
