"""Provider-neutral model metadata contracts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

MODEL_PROVIDER_CONTRACTS: tuple[dict[str, Any], ...] = (
    {
        "provider": "openai",
        "model_prefixes": ["gpt", "o"],
        "capabilities": ["chat", "code", "tool_use"],
        "api_call_default": False,
        "billing_authority": False,
        "cost_records_are_estimates": False,
        "cost_records_require_source": True,
        "fallback_provider": "unknown",
    },
    {
        "provider": "anthropic",
        "model_prefixes": ["claude"],
        "capabilities": ["chat", "code", "tool_use"],
        "api_call_default": False,
        "billing_authority": False,
        "cost_records_are_estimates": False,
        "cost_records_require_source": True,
        "fallback_provider": "unknown",
    },
    {
        "provider": "local",
        "model_prefixes": ["local", "llama", "mistral"],
        "capabilities": ["chat", "code"],
        "api_call_default": False,
        "billing_authority": False,
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
)


def provider_contract_map() -> dict[str, dict[str, Any]]:
    return {contract["provider"]: dict(contract) for contract in MODEL_PROVIDER_CONTRACTS}


def infer_provider_from_model(model_id: str | None) -> str:
    """Infer provider from model metadata without calling provider APIs."""
    if not model_id:
        return "unknown"
    lower = model_id.lower()
    for contract in MODEL_PROVIDER_CONTRACTS:
        provider = contract["provider"]
        if provider == "unknown":
            continue
        for prefix in contract["model_prefixes"]:
            if lower.startswith(prefix) or (len(prefix) > 2 and prefix in lower):
                return provider
    return "unknown"


def normalize_model_usage_metadata(
    *,
    model_id: str | None,
    provider: str | None = None,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    """Normalize token/model metadata for telemetry without provider authority."""
    inferred = infer_provider_from_model(model_id)
    resolved_provider = provider or inferred
    contracts = provider_contract_map()
    if resolved_provider not in contracts:
        resolved_provider = "unknown"
    contract = contracts[resolved_provider]
    return {
        "model_id": model_id or "unknown",
        "provider": resolved_provider,
        "inferred_provider": inferred,
        "provider_metadata_authority": False,
        "billing_authority": False,
        "cost_records_are_estimates": contract["cost_records_are_estimates"],
        "cost_records_require_source": contract["cost_records_require_source"],
        "api_call_default": False,
        "capabilities": list(contract["capabilities"]),
        "fallback_reason": fallback_reason,
    }


def validate_model_provider_contracts(
    contracts: Iterable[Mapping[str, Any]] = MODEL_PROVIDER_CONTRACTS,
) -> list[str]:
    """Validate provider contracts stay metadata-only and non-authoritative."""
    errors: list[str] = []
    providers: set[str] = set()
    for contract in contracts:
        provider = str(contract.get("provider", ""))
        if not provider:
            errors.append("provider is required")
        if provider in providers:
            errors.append(f"duplicate provider: {provider}")
        providers.add(provider)
        if contract.get("api_call_default") is not False:
            errors.append(f"api_call_default must be false for provider {provider}")
        if contract.get("billing_authority") is not False:
            errors.append(f"billing_authority must be false for provider {provider}")
        if contract.get("cost_records_require_source") is not True:
            errors.append(f"cost records must require source evidence for provider {provider}")
    if "unknown" not in providers:
        errors.append("unknown provider fallback is required")
    return errors
