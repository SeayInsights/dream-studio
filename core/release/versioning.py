"""Planning-only release versioning and distribution readiness helpers."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from core.production_readiness import build_secure_production_readiness_gate
from core.security.lifecycle import build_security_lifecycle_gate

SEMVER_RE = re.compile(r"^v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def build_release_readiness_packet(
    *,
    version: str,
    git_head: str,
    branch: str,
    changelog_entries: Sequence[str] = (),
    evidence_refs: Sequence[str] = (),
    known_caveats: Sequence[str] = (),
    rollback_notes: Sequence[str] = (),
    distribution_decision: str = "local_dogfood",
    security_lifecycle_status: Mapping[str, Any] | None = None,
    production_readiness_status: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a release readiness packet without tagging, pushing, or deploying."""

    return {
        "packet_type": "release_versioning_readiness",
        "version": version,
        "version_valid": bool(SEMVER_RE.match(version)),
        "branch": branch,
        "git_head": git_head,
        "derived_view": True,
        "primary_authority": False,
        "tag_created": False,
        "pushed": False,
        "deployed": False,
        "distribution_decision": distribution_decision,
        "decision_options": [
            "local_dogfood",
            "create_local_tag",
            "push_branch",
            "push_branch_and_tag",
            "hold_release",
        ],
        "changelog": [{"entry": str(entry)} for entry in changelog_entries],
        "release_notes": _release_notes(version, changelog_entries, known_caveats, rollback_notes),
        "known_caveats": [str(item) for item in known_caveats],
        "rollback_notes": [str(item) for item in rollback_notes],
        "evidence_refs": [str(ref) for ref in evidence_refs],
        "security_lifecycle_status": (
            dict(security_lifecycle_status)
            if security_lifecycle_status is not None
            else build_security_lifecycle_gate(lifecycle_event="release_merge")
        ),
        "production_readiness_status": (
            dict(production_readiness_status)
            if production_readiness_status is not None
            else build_secure_production_readiness_gate(lifecycle_event="release_merge")
        ),
        "approval_requirements": {
            "tag_requires_operator_approval": True,
            "push_requires_operator_approval": True,
            "deploy_requires_operator_approval": True,
        },
    }


def validate_release_readiness_packet(packet: Mapping[str, Any]) -> list[str]:
    """Return readiness or boundary violations for a release packet."""

    issues: list[str] = []
    if not packet.get("version_valid"):
        issues.append("valid_semver_version_required")
    if not packet.get("git_head"):
        issues.append("git_head_required")
    if not packet.get("branch"):
        issues.append("branch_required")
    if _truthy(packet.get("tag_created")):
        issues.append("tag_creation_not_allowed_in_readiness_packet")
    if _truthy(packet.get("pushed")):
        issues.append("push_not_allowed_in_readiness_packet")
    if _truthy(packet.get("deployed")):
        issues.append("deploy_not_allowed_in_readiness_packet")
    if not packet.get("rollback_notes"):
        issues.append("rollback_notes_required")
    if not packet.get("evidence_refs"):
        issues.append("evidence_refs_required")
    security_lifecycle = packet.get("security_lifecycle_status")
    if not isinstance(security_lifecycle, Mapping):
        issues.append("security_lifecycle_status_required")
    else:
        status = security_lifecycle.get("security_status")
        if status == "blocked_by_open_findings":
            issues.append("security_lifecycle_open_findings_block_release")
        elif status == "unknown_requires_review":
            issues.append("security_lifecycle_unknown_controls_require_review")
        elif status == "needs_manual_review":
            issues.append("security_lifecycle_manual_review_required")
        elif status != "ready":
            issues.append("security_lifecycle_ready_status_required")
    production_readiness = packet.get("production_readiness_status")
    if not isinstance(production_readiness, Mapping):
        issues.append("production_readiness_status_required")
    else:
        release = production_readiness.get("release_readiness")
        readiness_score = production_readiness.get("project_readiness_score")
        if not isinstance(release, Mapping):
            issues.append("production_readiness_release_status_required")
        elif release.get("status") != "ready":
            issues.append("production_readiness_hold_or_block_required")
        if isinstance(readiness_score, Mapping) and readiness_score.get("status") in {
            "partial",
            "unavailable",
        }:
            issues.append("production_readiness_evidence_incomplete")
    return issues


def _release_notes(
    version: str,
    changelog_entries: Sequence[str],
    known_caveats: Sequence[str],
    rollback_notes: Sequence[str],
) -> str:
    lines = [f"# Dream Studio {version}", "", "## Changes"]
    (
        lines.extend(f"- {entry}" for entry in changelog_entries)
        if changelog_entries
        else lines.append("- none recorded")
    )
    lines.extend(["", "## Known Caveats"])
    (
        lines.extend(f"- {item}" for item in known_caveats)
        if known_caveats
        else lines.append("- none recorded")
    )
    lines.extend(["", "## Rollback"])
    (
        lines.extend(f"- {item}" for item in rollback_notes)
        if rollback_notes
        else lines.append("- rollback notes required")
    )
    return "\n".join(lines) + "\n"


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "present"}
    return bool(value)
