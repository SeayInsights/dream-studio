from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.event_store.studio_db import _connect
from core.shared_intelligence.adapter_alignment import register_default_adapter_authority_profiles
from core.shared_intelligence.usage_accounting import (
    adapter_usage_accounting_summary,
    record_ai_usage_operational_record,
    register_default_adapter_accounting_profiles,
)


def _db(tmp_path: Path) -> Path:
    return tmp_path / "ai-usage-accounting" / "studio.db"


@pytest.fixture
def analytics_store(tmp_path, monkeypatch):
    """Isolated DuckDB analytics store (WO-DBA-DROP: token_usage_records is a
    view over events_fact now — seed token.consumed events, not the retired
    SQLite table)."""
    from core.analytics import duckdb_store

    db = tmp_path / "aggregate_metrics.db"
    monkeypatch.setattr(duckdb_store, "analytics_db_path", lambda: db)
    return db


def _seed_token_event(
    analytics_db: Path,
    *,
    event_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    adapter_id: str,
    provider: str,
) -> None:
    from core.analytics import duckdb_store

    conn = duckdb_store.connect_analytics(analytics_db, read_only=False)
    try:
        duckdb_store.ensure_analytics_schema(conn)
        conn.execute(
            "INSERT INTO events_fact (event_id, event_type, event_timestamp, model_id,"
            " adapter_id, input_tokens, output_tokens, payload)"
            " VALUES (?, 'token.consumed', '2026-07-03T00:00:00Z', ?, ?, ?, ?, ?)",
            [
                event_id,
                model,
                adapter_id,
                input_tokens,
                output_tokens,
                json.dumps({"model": model, "provider": provider}),
            ],
        )
    finally:
        conn.close()


def test_default_adapter_accounting_profiles_are_honest_about_plan_costs(
    tmp_path: Path,
) -> None:
    with _connect(_db(tmp_path)) as conn:
        register_default_adapter_authority_profiles(conn)
        register_default_adapter_accounting_profiles(conn)
        summary = adapter_usage_accounting_summary(conn)

    profiles = {profile["profile_id"]: profile for profile in summary["profiles"]}
    assert profiles["claude-code-subscription"]["billing_mode"] == "subscription_plan"
    assert profiles["claude-code-subscription"]["cost_visibility"] == "unavailable"
    assert profiles["codex-chatgpt-plan"]["billing_mode"] == "subscription_plan"
    assert profiles["codex-chatgpt-plan"]["cost_visibility"] == "unavailable"
    assert profiles["claude-api-token-metered"]["billing_mode"] == "token_metered"
    assert profiles["claude-api-token-metered"]["cost_visibility"] == "provider_reported"
    assert summary["policy"]["tokens_are_usage_not_cost"] is True
    assert summary["policy"]["provider_billing_credentials_inspected"] is False


def test_unpriced_model_rows_preserve_tokens_without_inventing_cost(
    tmp_path: Path, analytics_store: Path
) -> None:
    """A token.consumed event for a model absent from the pricing table
    (WO-DBA-DROP: DuckDB token_usage_records view LEFT JOINs
    token_model_pricing) reports tokens honestly with no fabricated cost —
    the same governance outcome the retired subscription_plan override used
    to produce."""
    _seed_token_event(
        analytics_store,
        event_id="token-claude-plan",
        model="claude-plan-not-a-real-model",
        input_tokens=1000,
        output_tokens=250,
        adapter_id="claude",
        provider="anthropic",
    )
    with _connect(_db(tmp_path)) as conn:
        register_default_adapter_authority_profiles(conn)
        summary = adapter_usage_accounting_summary(conn)

    claude = summary["by_adapter"]["claude"]
    assert claude["total_tokens"] == 1250
    assert claude["reportable_cost"] is None
    assert claude["cost_display"] == "unknown"
    assert claude["cost_visibility"] == {"unavailable": 1}


def test_priced_model_rows_report_cost_from_duckdb_view(
    tmp_path: Path, analytics_store: Path
) -> None:
    """A token.consumed event for a model IN the pricing table gets a
    computed reportable cost from the DuckDB view — the WO-DBA-DROP
    replacement for the retired externally-injected provider-metadata cost
    path (token.consumed events carry no pre-computed dollar amount)."""
    from core.pricing.claude_models import CLAUDE_MODEL_PRICING, compute_cost

    model = next(iter(CLAUDE_MODEL_PRICING))
    _seed_token_event(
        analytics_store,
        event_id="token-claude-api",
        model=model,
        input_tokens=1000,
        output_tokens=500,
        adapter_id="claude",
        provider="anthropic",
    )
    with _connect(_db(tmp_path)) as conn:
        register_default_adapter_authority_profiles(conn)
        summary = adapter_usage_accounting_summary(conn)

    claude = summary["by_adapter"]["claude"]
    assert claude["total_tokens"] == 1500
    expected_cost = compute_cost(model, 1000, 500)
    assert claude["reportable_cost"] == pytest.approx(expected_cost, rel=1e-6)
    assert claude["cost_visibility"] == {"estimated": 1}


def test_operational_usage_records_track_value_without_cost(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        register_default_adapter_authority_profiles(conn)
        record_ai_usage_operational_record(
            conn,
            usage_record_id="usage-codex-build",
            project_id="dream-studio",
            adapter_id="codex",
            provider="openai",
            model_id="codex-plan",
            billing_mode="subscription_plan",
            token_visibility="partial",
            cost_visibility="unavailable",
            cost_amount=22.0,
            files_touched=["core/shared_intelligence/usage_accounting.py"],
            commands_run=["pytest tests/unit/test_ai_usage_accounting.py"],
            validation_result="passed",
            success=True,
            rework_needed=False,
            duration_ms=1234,
            evidence_refs=["tests/unit/test_ai_usage_accounting.py"],
        )
        row = conn.execute(
            "SELECT cost_amount FROM ai_usage_operational_records WHERE usage_record_id = ?",
            ("usage-codex-build",),
        ).fetchone()
        summary = adapter_usage_accounting_summary(conn, project_id="dream-studio")

    assert row["cost_amount"] is None
    codex = summary["by_adapter"]["codex"]
    assert codex["run_count"] == 1
    assert codex["files_touched_count"] == 1
    assert codex["commands_run_count"] == 1
    assert codex["validation_results"] == {"passed": 1}
    assert codex["successful_runs"] == 1
