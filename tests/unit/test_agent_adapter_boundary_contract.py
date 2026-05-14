from __future__ import annotations

from interfaces.adapters.boundary import (
    ADAPTER_BOUNDARIES,
    adapter_boundary_map,
    validate_adapter_boundaries,
)


def test_adapter_boundaries_are_provider_neutral_and_non_authoritative() -> None:
    assert validate_adapter_boundaries() == []

    for boundary in ADAPTER_BOUNDARIES:
        assert boundary["owns_canonical_state"] is False
        assert boundary["writes_authority_db"] is False
        assert boundary["external_execution_default"] is False
        assert boundary["network_access_default"] is False
        assert boundary["diagnostic_metadata_only"] is True


def test_expected_agent_and_tool_adapter_families_are_declared() -> None:
    boundaries = adapter_boundary_map()

    assert "claude" in boundaries
    assert "codex" in boundaries
    assert "cursor" in boundaries
    assert "copilot" in boundaries
    assert "mcp" in boundaries
    assert "shell" in boundaries
    assert "github" in boundaries
    assert "default" in boundaries
    assert boundaries["codex"]["provider_family"] == "openai"
    assert boundaries["claude"]["provider_family"] == "anthropic"


def test_validation_rejects_authoritative_adapter_boundary() -> None:
    bad = [
        {
            "adapter_id": "unsafe",
            "provider_family": "example",
            "surface": "agent_output_normalization",
            "owns_canonical_state": True,
            "writes_authority_db": False,
            "external_execution_default": False,
            "network_access_default": False,
            "diagnostic_metadata_only": True,
        }
    ]

    errors = validate_adapter_boundaries(bad)

    assert "owns_canonical_state must be false for adapter unsafe" in errors


def test_validation_rejects_default_external_execution() -> None:
    bad = [
        {
            "adapter_id": "unsafe",
            "provider_family": "example",
            "surface": "agent_output_normalization",
            "owns_canonical_state": False,
            "writes_authority_db": False,
            "external_execution_default": True,
            "network_access_default": False,
            "diagnostic_metadata_only": True,
        }
    ]

    errors = validate_adapter_boundaries(bad)

    assert "external_execution_default must be false for adapter unsafe" in errors
