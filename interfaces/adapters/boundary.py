"""Provider-neutral adapter boundary declarations.

Adapters normalize or describe external tool/agent surfaces. They do not own
canonical state, execute providers by default, or write Dream Studio authority.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

ADAPTER_BOUNDARIES: tuple[dict[str, Any], ...] = (
    {
        "adapter_id": "claude",
        "provider_family": "anthropic",
        "surface": "agent_output_normalization",
        "owns_canonical_state": False,
        "writes_authority_db": False,
        "external_execution_default": False,
        "network_access_default": False,
        "diagnostic_metadata_only": True,
    },
    {
        "adapter_id": "codex",
        "provider_family": "openai",
        "surface": "agent_output_normalization",
        "owns_canonical_state": False,
        "writes_authority_db": False,
        "external_execution_default": False,
        "network_access_default": False,
        "diagnostic_metadata_only": True,
    },
    {
        "adapter_id": "cursor",
        "provider_family": "editor_agent",
        "surface": "agent_output_normalization",
        "owns_canonical_state": False,
        "writes_authority_db": False,
        "external_execution_default": False,
        "network_access_default": False,
        "diagnostic_metadata_only": True,
    },
    {
        "adapter_id": "copilot",
        "provider_family": "editor_agent",
        "surface": "agent_output_normalization",
        "owns_canonical_state": False,
        "writes_authority_db": False,
        "external_execution_default": False,
        "network_access_default": False,
        "diagnostic_metadata_only": True,
    },
    {
        "adapter_id": "mcp",
        "provider_family": "tool_protocol",
        "surface": "tool_invocation_metadata",
        "owns_canonical_state": False,
        "writes_authority_db": False,
        "external_execution_default": False,
        "network_access_default": False,
        "diagnostic_metadata_only": True,
    },
    {
        "adapter_id": "shell",
        "provider_family": "local_tool",
        "surface": "tool_invocation_metadata",
        "owns_canonical_state": False,
        "writes_authority_db": False,
        "external_execution_default": False,
        "network_access_default": False,
        "diagnostic_metadata_only": True,
    },
    {
        "adapter_id": "github",
        "provider_family": "source_control",
        "surface": "explicit_operator_tool",
        "owns_canonical_state": False,
        "writes_authority_db": False,
        "external_execution_default": False,
        "network_access_default": False,
        "diagnostic_metadata_only": True,
    },
    {
        "adapter_id": "default",
        "provider_family": "unknown",
        "surface": "fallback_normalization",
        "owns_canonical_state": False,
        "writes_authority_db": False,
        "external_execution_default": False,
        "network_access_default": False,
        "diagnostic_metadata_only": True,
    },
)


def adapter_boundary_map() -> dict[str, dict[str, Any]]:
    return {item["adapter_id"]: dict(item) for item in ADAPTER_BOUNDARIES}


def validate_adapter_boundaries(
    boundaries: Iterable[Mapping[str, Any]] = ADAPTER_BOUNDARIES,
) -> list[str]:
    """Validate that adapter declarations remain non-authoritative."""
    errors: list[str] = []
    seen: set[str] = set()
    for boundary in boundaries:
        adapter_id = str(boundary.get("adapter_id", ""))
        if not adapter_id:
            errors.append("adapter_id is required")
        if adapter_id in seen:
            errors.append(f"duplicate adapter boundary: {adapter_id}")
        seen.add(adapter_id)
        for key in (
            "owns_canonical_state",
            "writes_authority_db",
            "external_execution_default",
            "network_access_default",
        ):
            if boundary.get(key) is not False:
                errors.append(f"{key} must be false for adapter {adapter_id}")
        if boundary.get("diagnostic_metadata_only") is not True:
            errors.append(f"adapter {adapter_id} must be diagnostic metadata only")
        if not boundary.get("surface"):
            errors.append(f"adapter {adapter_id} must declare a surface")
    return errors
