from __future__ import annotations

from pathlib import Path

from core.event_store.studio_db import _connect
from core.shared_intelligence.adapter_alignment import register_default_adapter_authority_profiles
from core.shared_intelligence.usage_accounting import (
    adapter_usage_accounting_summary,
    register_default_adapter_accounting_profiles,
)
from core.telemetry.execution_spine import record_token_usage


def _db(tmp_path: Path) -> Path:
    return tmp_path / "ai-usage-accounting" / "studio.db"


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


def test_plan_token_rows_preserve_tokens_without_inventing_cost(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        register_default_adapter_authority_profiles(conn)
        record_token_usage(
            conn,
            token_usage_id="token-claude-plan",
            adapter_id="claude",
            provider="anthropic",
            model_id="claude-sonnet",
            billing_mode="subscription_plan",
            token_visibility="partial",
            input_tokens=1000,
            output_tokens=250,
            estimated_cost=99.0,
            purpose="plan telemetry",
        )
        summary = adapter_usage_accounting_summary(conn)

    claude = summary["by_adapter"]["claude"]
    assert claude["total_tokens"] == 1250
    assert claude["reportable_cost"] is None
    assert claude["cost_display"] == "unknown"
    assert claude["cost_visibility"] == {"unavailable": 1}


def test_token_metered_rows_report_cost_only_when_metadata_marks_it(
    tmp_path: Path,
) -> None:
    with _connect(_db(tmp_path)) as conn:
        register_default_adapter_authority_profiles(conn)
        record_token_usage(
            conn,
            token_usage_id="token-codex-api",
            adapter_id="codex",
            provider="openai",
            model_id="gpt-5",
            billing_mode="token_metered",
            token_visibility="exact",
            cost_visibility="provider_reported",
            usage_source="provider_metadata",
            cost_source="provider_metadata",
            input_tokens=100,
            output_tokens=50,
            estimated_cost=0.123456,
            purpose="api usage",
        )
        summary = adapter_usage_accounting_summary(conn)

    codex = summary["by_adapter"]["codex"]
    assert codex["total_tokens"] == 150
    assert codex["reportable_cost"] == 0.123456
    assert codex["cost_visibility"] == {"provider_reported": 1}


# test_operational_usage_records_track_value_without_cost removed —
# record_ai_usage_operational_record deleted; ai_usage_operational_records dropped migration 131.
