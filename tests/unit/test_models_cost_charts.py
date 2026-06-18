"""Tests for WO-DASH-ATTRIBUTION-SURFACES T3: cost-by-model populates with non-zero values for known models."""

from __future__ import annotations
import sqlite3


def _make_seeded_conn() -> sqlite3.Connection:
    """Return an in-memory SQLite connection with token_usage_records seeded for two models."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE token_usage_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cached_tokens INTEGER,
            cache_read_tokens INTEGER,
            total_tokens INTEGER,
            skill_id TEXT,
            estimated_cost REAL,
            cost_visibility TEXT,
            created_at TEXT
        )
        """)
    # Two rows for claude-opus-4-8
    conn.execute(
        "INSERT INTO token_usage_records "
        "(model_id, input_tokens, output_tokens, cached_tokens, cache_read_tokens) "
        "VALUES (?, 5000, 2000, 0, 0)",
        ("claude-opus-4-8",),
    )
    conn.execute(
        "INSERT INTO token_usage_records "
        "(model_id, input_tokens, output_tokens, cached_tokens, cache_read_tokens) "
        "VALUES (?, 5000, 2000, 0, 0)",
        ("claude-opus-4-8",),
    )
    # Two rows for claude-sonnet-4-6
    conn.execute(
        "INSERT INTO token_usage_records "
        "(model_id, input_tokens, output_tokens, cached_tokens, cache_read_tokens) "
        "VALUES (?, 5000, 2000, 0, 0)",
        ("claude-sonnet-4-6",),
    )
    conn.execute(
        "INSERT INTO token_usage_records "
        "(model_id, input_tokens, output_tokens, cached_tokens, cache_read_tokens) "
        "VALUES (?, 5000, 2000, 0, 0)",
        ("claude-sonnet-4-6",),
    )
    conn.commit()
    return conn


def test_cost_by_model_nonzero():
    """Verify api_equivalent_cost returns non-zero costs for known models with seeded token data."""
    from projections.core.cost_analysis import api_equivalent_cost

    conn = _make_seeded_conn()
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
