from __future__ import annotations

from core.release.versioning import (
    build_release_readiness_packet,
    validate_release_readiness_packet,
)


def test_release_readiness_packet_supports_local_dogfood_without_push_or_tag() -> None:
    packet = build_release_readiness_packet(
        version="v0.1.0",
        branch="integration/example",
        git_head="abc123",
        changelog_entries=["Telemetry dashboard wired"],
        evidence_refs=["meta/audit/release.md"],
        known_caveats=["Browser automation deferred"],
        rollback_notes=["Reset to previous local backup"],
        security_lifecycle_status={"security_status": "ready"},
        production_readiness_status={
            "release_readiness": {"status": "ready"},
            "project_readiness_score": {"status": "scored"},
        },
    )

    assert packet["version_valid"] is True
    assert packet["tag_created"] is False
    assert packet["pushed"] is False
    assert packet["deployed"] is False
    assert packet["distribution_decision"] == "local_dogfood"
    assert "Telemetry dashboard wired" in packet["release_notes"]
    assert packet["security_lifecycle_status"]["security_status"] == "ready"
    assert validate_release_readiness_packet(packet) == []


def test_default_release_packet_holds_for_manual_security_lifecycle_review() -> None:
    packet = build_release_readiness_packet(
        version="v0.1.0",
        branch="integration/example",
        git_head="abc123",
        changelog_entries=["Telemetry dashboard wired"],
        evidence_refs=["meta/audit/release.md"],
        rollback_notes=["Reset to previous local backup"],
    )

    assert packet["security_lifecycle_status"]["full_review_required"] is True
    assert "security_lifecycle_manual_review_required" in validate_release_readiness_packet(packet)
    assert "production_readiness_hold_or_block_required" in validate_release_readiness_packet(
        packet
    )
    assert "production_readiness_evidence_incomplete" in validate_release_readiness_packet(packet)


def test_release_packet_validator_blocks_execution_flags_and_missing_evidence() -> None:
    issues = validate_release_readiness_packet(
        {
            "version": "release",
            "version_valid": False,
            "branch": "",
            "git_head": "",
            "tag_created": True,
            "pushed": True,
            "deployed": True,
            "rollback_notes": [],
            "evidence_refs": [],
        }
    )

    assert "valid_semver_version_required" in issues
    assert "git_head_required" in issues
    assert "branch_required" in issues
    assert "tag_creation_not_allowed_in_readiness_packet" in issues
    assert "push_not_allowed_in_readiness_packet" in issues
    assert "deploy_not_allowed_in_readiness_packet" in issues
    assert "rollback_notes_required" in issues
    assert "evidence_refs_required" in issues
    assert "security_lifecycle_status_required" in issues
    assert "production_readiness_status_required" in issues
