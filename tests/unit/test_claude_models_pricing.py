"""WO-COST-MODEL-RATES: the pricing table must carry current model rates.

Reportable / API-equivalent cost was stuck at ~$0.08 because
core/pricing/claude_models.py lacked claude-opus-4-8 — compute_cost logged
'unknown model … -> returning 0.0', so all Opus usage costed $0.

Module-level functions so the work order's bare TEST-CHECK node-ids resolve.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from core.pricing.claude_models import (
    CLAUDE_MODEL_PRICING,
    _normalize_model_id,
    compute_cost,
)

REPO_ROOT = Path(__file__).parents[2]

# Models actually in use / current shipping tier that MUST price (claude-fable-5 is
# intentionally excluded: zero usage and no published rate — not fabricated here).
CURRENT_MODELS = ("claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5")


def test_opus_4_8_has_nonzero_cost():
    """claude-opus-4-8 is priced at the current-Opus tier (input $5 / output $25 per MTok)."""
    assert "claude-opus-4-8" in CLAUDE_MODEL_PRICING, "claude-opus-4-8 missing from pricing table"
    cost = compute_cost("claude-opus-4-8", 1_000_000, 1_000_000)
    assert cost > 0, "opus-4-8 must produce a non-zero cost (was $0 — unknown model)"
    assert cost == 30.0, f"opus-4-8 1M in + 1M out should be $30.00 (5+25), got {cost}"
    # Date-suffixed id normalizes to the same rate.
    assert compute_cost("claude-opus-4-8-20260101", 1_000_000, 0) == 5.0


def test_no_unknown_model_for_current_models(caplog):
    """compute_cost must not log 'unknown model' for any current shipping model."""
    for model in CURRENT_MODELS:
        assert _normalize_model_id(model) in CLAUDE_MODEL_PRICING, f"{model} missing from table"
    with caplog.at_level(logging.WARNING, logger="core.pricing.claude_models"):
        for model in CURRENT_MODELS:
            assert compute_cost(model, 1000, 1000) > 0
    assert (
        "unknown model" not in caplog.text
    ), f"compute_cost logged an unknown-model warning for a current model: {caplog.text!r}"


def test_all_consumers_get_current_rates():
    """Every compute_cost consumer benefits from the shared table — adding opus-4-8
    flows to all of them. Verify the table covers current models and the real
    consumers import the shared pricing (no consumer carries its own rates)."""
    # Shared table covers the current models => every consumer gets the rate.
    for model in CURRENT_MODELS:
        assert compute_cost(model, 1000, 0) > 0, f"{model} unpriced — consumers would see $0"

    consumers = (
        "projections/core/cost_analysis.py",
        "projections/api/queries/token_attribution.py",
        "interfaces/cli/efficiency_analytics.py",
    )
    for rel in consumers:
        src = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert (
            "claude_models" in src or "compute_cost" in src
        ), f"{rel} should source rates from core.pricing.claude_models, not its own table"
        # Regression guard: no consumer may DEFINE its own per-model rate table
        # (a private MODEL_PRICING drifts from canon — caused the opus-4-8 miss).
        # Importing the shared CLAUDE_MODEL_PRICING is fine; defining a bare
        # MODEL_PRICING name (assignment/annotation) is not.
        import re as _re

        assert not _re.search(
            r"(?<!CLAUDE_)\bMODEL_PRICING\s*[:=]", src
        ), f"{rel} must not define a private MODEL_PRICING table"

    # Actually EXERCISE a consumer end-to-end: efficiency_analytics must price an
    # opus-4-8 session through the shared table (was $0 / stale before).
    from interfaces.cli.efficiency_analytics import compute_cost_analysis

    sessions = [
        {
            "session_id": "s-opus-1",
            "primary_model": "claude-opus-4-8",
            "prompt_tokens": 1_000_000,
            "completion_tokens": 1_000_000,
            "date": "2026-06-18",
        }
    ]
    result = compute_cost_analysis(sessions, total_tasks=0)
    assert (
        result["total_cost_usd"] == 30.0
    ), f"efficiency_analytics must price opus-4-8 via the shared table ($30), got {result['total_cost_usd']}"


def test_end_to_end(tmp_path, monkeypatch):
    """End-to-end: a token.consumed event on claude-opus-4-8 yields non-zero
    API-equivalent cost and is counted as priced (no longer 'unknown model').

    WO-DBA-DROP (migration 137): token_usage_records is no longer a SQLite
    table — api_equivalent_cost() reads the DuckDB aggregate_metrics.db view
    (derived from canonical token.consumed events) instead.
    """
    from core.analytics import duckdb_store
    from core.config.sqlite_bootstrap import bootstrap_database
    from projections.core.cost_analysis import api_equivalent_cost

    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)

    analytics_db = tmp_path / "aggregate_metrics.db"
    monkeypatch.setattr(duckdb_store, "analytics_db_path", lambda: analytics_db)
    duck_conn = duckdb_store.connect_analytics(analytics_db, read_only=False)
    try:
        duckdb_store.ensure_analytics_schema(duck_conn)
        duck_conn.execute(
            "INSERT INTO events_fact (event_id, event_type, event_timestamp, model_id,"
            " input_tokens, output_tokens)"
            " VALUES ('t-opus', 'token.consumed', '2026-07-03T00:00:00Z', 'claude-opus-4-8',"
            " 1000000, 1000000)"
        )
    finally:
        duck_conn.close()

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        result = api_equivalent_cost(conn)
    finally:
        conn.close()

    assert result["total_usd"] == 30.0, f"opus-4-8 row should cost $30, got {result['total_usd']}"
    assert result["priced_record_count"] == 1
    assert result["unpriced_record_count"] == 0
