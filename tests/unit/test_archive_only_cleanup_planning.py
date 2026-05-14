from __future__ import annotations

from pathlib import Path

from core.upgrade.archive_cleanup_plan import (
    build_archive_only_cleanup_plan,
    validate_archive_only_cleanup_plan,
)
from core.upgrade.cleanup_manifest import draft_cleanup_manifest
from core.upgrade.evidence_reconciliation import reconcile_existing_evidence


def test_archive_only_plan_is_non_executing_and_approval_gated(tmp_path: Path) -> None:
    manifest = draft_cleanup_manifest(reconcile_existing_evidence())

    plan = build_archive_only_cleanup_plan(
        manifest,
        archive_root=tmp_path / "archive-rehearsal",
    )

    assert validate_archive_only_cleanup_plan(plan) == []
    assert plan["planning_only"] is True
    assert plan["archive_execution_allowed"] is False
    assert plan["delete_execution_allowed"] is False
    assert plan["deduplication_execution_allowed"] is False
    assert plan["compaction_execution_allowed"] is False
    assert plan["db_cleanup_allowed"] is False
    assert plan["requires_future_operator_approval"] is True


def test_archive_candidates_require_hash_and_restore_rehearsal(tmp_path: Path) -> None:
    manifest = draft_cleanup_manifest(reconcile_existing_evidence())

    plan = build_archive_only_cleanup_plan(
        manifest,
        archive_root=tmp_path / "archive-rehearsal",
    )

    assert plan["archive_candidates"]
    for candidate in plan["archive_candidates"]:
        assert candidate["backup_dependency"] is True
        assert candidate["hash_evidence_required"] is True
        assert candidate["restore_rehearsal_required"] is True
        assert candidate["human_review_required"] is True
        assert candidate["archive_execution_allowed"] is False
        assert candidate["delete_after_archive_allowed"] is False


def test_non_archive_cleanup_categories_are_deferred(tmp_path: Path) -> None:
    manifest = draft_cleanup_manifest(reconcile_existing_evidence())

    plan = build_archive_only_cleanup_plan(
        manifest,
        archive_root=tmp_path / "archive-rehearsal",
    )

    deferred_categories = {item["category"] for item in plan["deferred_candidates"]}
    assert "keep" in deferred_categories
    assert "rehydrate" in deferred_categories
    assert "manual_review_required" in deferred_categories
    assert "unknown_defer" in deferred_categories
    assert all(item["human_review_required"] for item in plan["deferred_candidates"])


def test_archive_only_plan_does_not_create_archive_paths(tmp_path: Path) -> None:
    archive_root = tmp_path / "archive-rehearsal"
    manifest = draft_cleanup_manifest(reconcile_existing_evidence())

    plan = build_archive_only_cleanup_plan(manifest, archive_root=archive_root)

    assert plan["archive_root"] == str(archive_root)
    assert not archive_root.exists()
