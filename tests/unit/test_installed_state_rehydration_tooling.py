from __future__ import annotations

from pathlib import Path

import pytest

import core.upgrade
from core.upgrade.cleanup_manifest import draft_cleanup_manifest, validate_cleanup_manifest
from core.upgrade.evidence_reconciliation import (
    INSTALLED_STATE_PATH,
    reconcile_existing_evidence,
    validate_evidence_reconciliation,
)
from core.upgrade.installed_state_rehydration import (
    LiveStateWriteError,
    assert_rehearsal_write_target,
    build_rehydration_gap_plan,
    build_validation_summary,
    plan_from_existing_evidence,
)


def test_reconciliation_uses_existing_evidence_without_broad_inventory() -> None:
    reconciliation = reconcile_existing_evidence()

    assert reconciliation["broad_inventory_repeated"] is False
    assert reconciliation["live_state_mutation_allowed"] is False
    assert reconciliation["live_db_mutation_allowed"] is False
    assert validate_evidence_reconciliation(reconciliation) == []
    categories = {source["category"] for source in reconciliation["evidence_sources"]}
    assert "database_authority" in categories
    assert "dashboard_read_models" in categories
    assert "integration_matrix" in categories
    assert reconciliation["remaining_gaps"]


def test_rehydration_mapping_covers_required_domains() -> None:
    plan = build_rehydration_gap_plan(reconcile_existing_evidence())
    domains = {item["source_domain"] for item in plan["mapping_domains"]}

    assert plan["live_mutation_allowed"] is False
    assert plan["rehearsal_required_before_cutover"] is True
    assert {
        "projects",
        "milestones",
        "work_orders",
        "approvals",
        "decisions",
        "research",
        "security_findings",
        "validations_evals",
        "token_usage",
        "skills",
        "workflows",
        "hooks_tools",
        "reports_prompts",
        "dashboard_projection_data",
        "backups_archives_caches_logs",
    } <= domains


def test_cleanup_manifest_is_non_executable_and_review_gated() -> None:
    manifest = draft_cleanup_manifest(reconcile_existing_evidence())

    assert manifest["cleanup_execution_allowed"] is False
    assert manifest["executable"] is False
    assert validate_cleanup_manifest(manifest) == []
    categories = {item["category"] for item in manifest["items"]}
    assert "keep" in categories
    assert "rehydrate" in categories
    assert "archive_candidate" in categories
    assert "deduplicate_candidate" in categories
    assert "manual_review_required" in categories
    assert "unknown_defer" in categories
    assert "delete_candidate" in manifest["categories"]
    assert all(item["human_review_required"] for item in manifest["items"])


def test_no_live_mutation_guard_rejects_live_installed_state() -> None:
    with pytest.raises(LiveStateWriteError):
        assert_rehearsal_write_target(INSTALLED_STATE_PATH)
    with pytest.raises(LiveStateWriteError):
        assert_rehearsal_write_target(INSTALLED_STATE_PATH / "state" / "rehearsal")


def test_rehearsal_target_allows_temp_paths(tmp_path: Path) -> None:
    target = tmp_path / "rehearsal-output"

    assert assert_rehearsal_write_target(target) == target.resolve()


def test_plan_from_existing_evidence_is_dry_run_and_valid(tmp_path: Path) -> None:
    plan = plan_from_existing_evidence(rehearsal_output_path=tmp_path / "rehearsal")

    assert plan["dry_run"] is True
    assert plan["validation"]["valid"] is True
    assert plan["validation"]["dry_run_supported"] is True
    assert plan["validation"]["rehearsal_mode_supported"] is True
    assert plan["validation"]["live_write_guard_supported"] is True
    assert plan["reconciliation"]["broad_inventory_repeated"] is False


def test_validation_summary_fails_if_live_mutation_is_enabled() -> None:
    reconciliation = reconcile_existing_evidence()
    rehydration_plan = build_rehydration_gap_plan(reconciliation)
    cleanup = draft_cleanup_manifest(reconciliation)
    bad_plan = {**rehydration_plan, "live_mutation_allowed": True}

    summary = build_validation_summary(
        reconciliation=reconciliation,
        rehydration_plan=bad_plan,
        cleanup_manifest=cleanup,
    )

    assert summary["valid"] is False
    assert "rehydration plan must forbid live mutation" in summary["errors"]


def test_upgrade_tooling_source_does_not_hardcode_operator_home_path() -> None:
    upgrade_root = Path(core.upgrade.__file__).parent
    hardcoded_operator_home = "C:\\Users\\Example User"

    source_text = "\n".join(path.read_text(encoding="utf-8") for path in upgrade_root.glob("*.py"))

    assert hardcoded_operator_home not in source_text
