from __future__ import annotations

from core.telemetry.model_providers import (
    infer_provider_from_model,
    normalize_model_usage_metadata,
    provider_contract_map,
    validate_model_provider_contracts,
)


def test_model_provider_contracts_are_metadata_only() -> None:
    assert validate_model_provider_contracts() == []

    for contract in provider_contract_map().values():
        assert contract["api_call_default"] is False
        assert contract["billing_authority"] is False
        assert contract["cost_records_are_estimates"] is False
        assert contract["cost_records_require_source"] is True


def test_infer_provider_from_model_ids_without_provider_calls() -> None:
    assert infer_provider_from_model("gpt-5") == "openai"
    assert infer_provider_from_model("claude-sonnet-4.5") == "anthropic"
    assert infer_provider_from_model("local-llama") == "local"
    assert infer_provider_from_model(None) == "unknown"
    assert infer_provider_from_model("not-in-catalog") == "unknown"


def test_normalized_model_usage_never_claims_billing_authority() -> None:
    metadata = normalize_model_usage_metadata(model_id="gpt-5", fallback_reason="none")

    assert metadata["model_id"] == "gpt-5"
    assert metadata["provider"] == "openai"
    assert metadata["inferred_provider"] == "openai"
    assert metadata["provider_metadata_authority"] is False
    assert metadata["billing_authority"] is False
    assert metadata["cost_records_are_estimates"] is False
    assert metadata["cost_records_require_source"] is True
    assert metadata["api_call_default"] is False
    assert "code" in metadata["capabilities"]


def test_unknown_provider_is_conservative_fallback() -> None:
    metadata = normalize_model_usage_metadata(
        model_id="mystery-model",
        provider="unsupported-provider",
        fallback_reason="unsupported provider supplied",
    )

    assert metadata["provider"] == "unknown"
    assert metadata["inferred_provider"] == "unknown"
    assert metadata["capabilities"] == []
    assert metadata["billing_authority"] is False


def test_validation_rejects_provider_billing_authority() -> None:
    bad = [
        {
            "provider": "unsafe",
            "model_prefixes": ["unsafe"],
            "capabilities": ["chat"],
            "api_call_default": False,
            "billing_authority": True,
            "cost_records_are_estimates": False,
            "cost_records_require_source": True,
            "fallback_provider": "unknown",
        },
        {
            "provider": "unknown",
            "model_prefixes": [],
            "capabilities": [],
            "api_call_default": False,
            "billing_authority": False,
            "cost_records_are_estimates": False,
            "cost_records_require_source": True,
            "fallback_provider": None,
        },
    ]

    errors = validate_model_provider_contracts(bad)

    assert "billing_authority must be false for provider unsafe" in errors
