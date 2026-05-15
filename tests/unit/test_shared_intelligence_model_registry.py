from __future__ import annotations

from pathlib import Path

from core.event_store.studio_db import _connect
from core.shared_intelligence.authority import record_model_provider_profile
from core.shared_intelligence.model_registry import (
    model_provider_capability_matrix,
    model_provider_registry_policy,
    model_provider_registry_summary,
)


def _db(tmp_path: Path) -> Path:
    return tmp_path / "model-registry" / "studio.db"


def test_model_provider_registry_summary_uses_recorded_sqlite_facts(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        _seed_profiles(conn)
        summary = model_provider_registry_summary(conn)

    assert summary["model_name"] == "shared_intelligence_model_provider_registry_summary"
    assert summary["derived_view"] is True
    assert summary["primary_authority"] is False
    assert summary["routing_authority"] is False
    assert summary["source_tables"] == ["model_provider_profiles"]
    assert summary["provider_api_calls_performed"] is False
    assert summary["billing_authority"] is False
    assert summary["cost_records_are_estimates"] is False
    assert summary["cost_records_require_source"] is True
    assert summary["model_count"] == 3
    assert summary["provider_counts"] == {
        "anthropic": 1,
        "local": 1,
        "openai": 1,
    }
    assert summary["capability_counts"]["code"] == 3
    assert summary["failure_mode_counts"]["context_overflow"] == 1


def test_model_provider_capability_matrix_matches_constraints_from_recorded_profiles(
    tmp_path: Path,
) -> None:
    with _connect(_db(tmp_path)) as conn:
        _seed_profiles(conn)
        matrix = model_provider_capability_matrix(
            conn,
            required_capabilities=["code"],
            min_context_tokens=100000,
        )
        tool_use = model_provider_capability_matrix(
            conn,
            required_capabilities=["tool_use"],
        )

    assert matrix["match_count"] == 2
    assert matrix["matches_by_provider"] == {
        "anthropic": ["claude-test-reasoning"],
        "openai": ["gpt-test-code"],
    }
    assert "context_limit_too_small" in matrix["rejected"][0]["rejection_reasons"]
    assert tool_use["match_count"] == 1
    assert tool_use["matches"][0]["model_id"] == "gpt-test-code"


def test_model_provider_registry_empty_state_is_non_authoritative(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        summary = model_provider_registry_summary(conn)
        matrix = model_provider_capability_matrix(conn, required_capabilities=["code"])

    assert summary["facts_available"] is False
    assert summary["profiles"] == []
    assert matrix["facts_available"] is False
    assert matrix["matches"] == []
    assert (
        matrix["empty_state"]
        == "No recorded model/provider profile matches the requested capabilities."
    )


def test_model_provider_registry_policy_requires_fresh_verification_for_latest_claims() -> None:
    policy = model_provider_registry_policy()

    assert policy["source_authority"] == "sqlite"
    assert policy["provider_api_calls_default"] is False
    assert policy["billing_authority"] is False
    assert policy["cost_records_are_estimates"] is False
    assert policy["cost_records_require_source"] is True
    assert policy["latest_model_claims_require_fresh_verification"] is True
    assert policy["profile_writes_require_injected_connection"] is True


def test_model_registry_uses_temp_db_not_live_db(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    live_db = Path.home() / ".dream-studio" / "state" / "studio.db"
    with _connect(db_path) as conn:
        _seed_profiles(conn)
        summary = model_provider_registry_summary(conn)

    assert summary["model_count"] == 3
    assert db_path.is_file()
    assert db_path != live_db


def _seed_profiles(conn) -> None:
    record_model_provider_profile(
        conn,
        model_profile_id="openai-gpt-test-code",
        provider="openai",
        model_id="gpt-test-code",
        capability_tags=["code", "tool_use"],
        context_limit_tokens=200000,
        cost_profile={"authority": "recorded_estimate"},
        token_behavior={"streaming": True},
        output_quality={"code": "strong"},
        failure_modes=["context_overflow"],
        best_use_patterns=["bounded repo implementation"],
        source_refs=["sqlite:model_provider_profiles"],
        evidence_refs=["tests/unit/test_shared_intelligence_model_registry.py"],
    )
    record_model_provider_profile(
        conn,
        model_profile_id="anthropic-claude-test-reasoning",
        provider="anthropic",
        model_id="claude-test-reasoning",
        capability_tags=["code", "reasoning"],
        context_limit_tokens=180000,
        cost_profile={"authority": "recorded_estimate"},
        failure_modes=["tool_retry"],
        best_use_patterns=["architecture review"],
    )
    record_model_provider_profile(
        conn,
        model_profile_id="local-small-code",
        provider="local",
        model_id="local-small-code",
        capability_tags=["code", "offline"],
        context_limit_tokens=32000,
        cost_profile={"authority": "local_estimate"},
        failure_modes=["limited_context"],
        best_use_patterns=["offline summarization"],
    )
    conn.commit()
