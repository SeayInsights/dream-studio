from __future__ import annotations

from core.work_orders.audit_export import (
    build_audit_export_packet,
    validate_audit_export_packet,
)


def test_audit_export_packet_summarizes_release_without_raw_content() -> None:
    packet = build_audit_export_packet(
        release_id="local-2026-05-13",
        milestones=[{"id": "m1", "status": "complete", "raw_prompt": "private"}],
        validations=[{"id": "v1", "status": "passed"}, {"id": "v2", "status": "failed"}],
        decisions=[{"id": "d1", "decision": "continue"}],
        security_findings=[{"id": "s1", "status": "open", "secret": "private"}],
        evidence_refs=["meta/audit/report.md"],
    )

    assert packet["derived_view"] is True
    assert packet["primary_authority"] is False
    assert packet["raw_content_exported"] is False
    assert packet["executive_summary"]["milestone_count"] == 1
    assert packet["executive_summary"]["failed_validation_count"] == 1
    assert packet["executive_summary"]["open_security_finding_count"] == 1
    assert "raw_prompt" not in packet["sections"]["milestones"][0]
    assert "secret" not in packet["sections"]["security_findings"][0]
    assert validate_audit_export_packet(packet) == []


def test_audit_export_validator_rejects_authority_and_raw_fields() -> None:
    issues = validate_audit_export_packet(
        {
            "release_id": "",
            "primary_authority": True,
            "raw_content_exported": True,
            "sections": {"decisions": [{"id": "d1", "raw_prompt": "private"}]},
        }
    )

    assert "audit_packet_must_not_be_primary_authority" in issues
    assert "raw_content_must_not_be_exported" in issues
    assert "release_id_required" in issues
    assert "decisions_0_contains_forbidden_fields:raw_prompt" in issues
