from __future__ import annotations

from core.security.privacy_supply_chain import (
    build_security_privacy_supply_chain_review,
    validate_security_privacy_supply_chain_review,
)


def test_security_privacy_review_packet_covers_required_categories_without_secret_extraction() -> (
    None
):
    packet = build_security_privacy_supply_chain_review(
        findings=[
            {
                "id": "finding-1",
                "category": "secret_handling",
                "risk": "high",
                "status": "manual_review_required",
                "secret_value": "do-not-include",
            }
        ],
        evidence_refs=["meta/audit/security.md"],
    )

    assert packet["secret_values_extracted"] is False
    assert packet["external_scan_run"] is False
    assert packet["package_commands_run"] is False
    assert "secret_value" not in packet["findings"][0]
    assert packet["findings"][0]["secret_value_present"] is False
    assert packet["summary"]["high_risk_count"] == 1
    assert validate_security_privacy_supply_chain_review(packet) == []


def test_security_privacy_review_validator_rejects_boundary_violations() -> None:
    issues = validate_security_privacy_supply_chain_review(
        {
            "secret_values_extracted": True,
            "external_scan_run": True,
            "package_commands_run": True,
            "categories": ["secret_handling"],
            "findings": [{"id": "bad", "secret_value": "nope"}],
        }
    )

    assert "secret_values_must_not_be_extracted" in issues
    assert "external_scan_not_allowed_in_packet_builder" in issues
    assert "package_commands_not_allowed_in_packet_builder" in issues
    assert any(issue.startswith("missing_review_categories:") for issue in issues)
    assert "finding_0_contains_secret_value" in issues
