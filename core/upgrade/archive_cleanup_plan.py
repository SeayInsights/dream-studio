"""Archive-only cleanup planning guards.

This module creates non-executing plans for future archive-only cleanup review.
It does not move, delete, compact, deduplicate, or mutate installed state.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.upgrade.cleanup_manifest import validate_cleanup_manifest


def build_archive_only_cleanup_plan(
    cleanup_manifest: Mapping[str, Any],
    *,
    archive_root: Path,
) -> dict[str, Any]:
    """Build a non-executing archive-only plan from cleanup manifest candidates."""
    errors = validate_cleanup_manifest(cleanup_manifest)
    archive_items = [
        item
        for item in cleanup_manifest.get("items", [])
        if item.get("category") == "archive_candidate"
    ]
    deferred_items = [
        item
        for item in cleanup_manifest.get("items", [])
        if item.get("category") != "archive_candidate"
    ]
    return {
        "artifact_type": "archive_only_cleanup_plan",
        "planning_only": True,
        "archive_execution_allowed": False,
        "delete_execution_allowed": False,
        "deduplication_execution_allowed": False,
        "compaction_execution_allowed": False,
        "db_cleanup_allowed": False,
        "requires_future_operator_approval": True,
        "archive_root": str(archive_root),
        "validation_errors": errors,
        "archive_candidates": [_archive_candidate(item, archive_root) for item in archive_items],
        "deferred_candidates": [
            {
                "path_or_category": item.get("path_or_category"),
                "category": item.get("category"),
                "reason": "not eligible for archive-only planning without a later narrower review",
                "human_review_required": True,
            }
            for item in deferred_items
        ],
        "restore_rehearsal": {
            "required_before_archive_execution": True,
            "required_steps": [
                "copy archive candidate to rehearsal archive root",
                "verify source hash and archive hash",
                "restore candidate from rehearsal archive",
                "verify restored hash matches source hash",
                "record rollback instructions",
            ],
        },
    }


def validate_archive_only_cleanup_plan(plan: Mapping[str, Any]) -> list[str]:
    """Validate that an archive cleanup plan cannot execute cleanup."""
    errors: list[str] = []
    if plan.get("planning_only") is not True:
        errors.append("archive cleanup plan must be planning-only")
    for key in (
        "archive_execution_allowed",
        "delete_execution_allowed",
        "deduplication_execution_allowed",
        "compaction_execution_allowed",
        "db_cleanup_allowed",
    ):
        if plan.get(key) is not False:
            errors.append(f"{key} must be false")
    if plan.get("requires_future_operator_approval") is not True:
        errors.append("future operator approval is required")
    for candidate in plan.get("archive_candidates", []):
        if candidate.get("hash_evidence_required") is not True:
            errors.append("archive candidate must require hash evidence")
        if candidate.get("restore_rehearsal_required") is not True:
            errors.append("archive candidate must require restore rehearsal")
        if candidate.get("delete_after_archive_allowed") is not False:
            errors.append("archive candidate must not allow deletion after archive")
    return errors


def _archive_candidate(item: Mapping[str, Any], archive_root: Path) -> dict[str, Any]:
    source = str(item.get("path_or_category", "unknown"))
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", source).strip("-").lower() or "archive-candidate"
    return {
        "source_path_or_category": source,
        "proposed_archive_path": str(archive_root / "candidates" / slug),
        "reason": item.get("reason"),
        "confidence": item.get("confidence"),
        "risk_level": item.get("risk_level"),
        "source_evidence": list(item.get("source_evidence", [])),
        "backup_dependency": True,
        "hash_evidence_required": True,
        "restore_rehearsal_required": True,
        "human_review_required": True,
        "archive_execution_allowed": False,
        "delete_after_archive_allowed": False,
    }
