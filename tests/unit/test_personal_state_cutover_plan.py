from __future__ import annotations

from pathlib import Path

import pytest

import core.upgrade
from core.upgrade.cutover_plan import (
    PLAN_DOCUMENT_NAMES,
    build_personal_state_cutover_rehearsal_plan,
    validate_cutover_rehearsal_plan,
)
from core.upgrade.evidence_reconciliation import INSTALLED_STATE_PATH
from core.upgrade.installed_state_rehydration import LiveStateWriteError


def test_cutover_plan_generates_required_documents(tmp_path: Path) -> None:
    plan = build_personal_state_cutover_rehearsal_plan(
        repo_path=tmp_path / "repo",
        installed_state_path=tmp_path / "installed-state",
        live_db_path=tmp_path / "installed-state" / "state" / "studio.db",
        rehearsal_state_path=tmp_path / "rehearsal",
    )

    assert plan["planning_only"] is True
    assert plan["executes_cutover"] is False
    assert plan["executes_cleanup"] is False
    assert plan["live_mutation_allowed"] is False
    assert set(PLAN_DOCUMENT_NAMES) <= set(plan["documents"])
    assert validate_cutover_rehearsal_plan(plan) == []


def test_cutover_plan_refuses_live_state_as_rehearsal_target() -> None:
    with pytest.raises(LiveStateWriteError):
        build_personal_state_cutover_rehearsal_plan(
            repo_path=Path("repo"),
            rehearsal_state_path=INSTALLED_STATE_PATH,
        )


def test_cutover_plan_keeps_cleanup_as_separate_approval_boundary(tmp_path: Path) -> None:
    plan = build_personal_state_cutover_rehearsal_plan(
        repo_path=tmp_path / "repo",
        installed_state_path=tmp_path / "installed-state",
        live_db_path=tmp_path / "installed-state" / "state" / "studio.db",
        rehearsal_state_path=tmp_path / "rehearsal",
    )
    cleanup_strategy = plan["documents"]["cutover_plan"]["cleanup_approval_strategy"]
    gate_names = {gate["gate"] for gate in plan["documents"]["approval_gates"]["gates"]}

    assert cleanup_strategy["cleanup_execution_allowed_now"] is False
    assert "cleanup_manifest" in gate_names
    assert "deletion_archive_compaction" in gate_names
    assert all(
        gate["operator_approval_required"] for gate in plan["documents"]["approval_gates"]["gates"]
    )


def test_cutover_plan_contains_required_validation_gates(tmp_path: Path) -> None:
    plan = build_personal_state_cutover_rehearsal_plan(
        repo_path=tmp_path / "repo",
        installed_state_path=tmp_path / "installed-state",
        live_db_path=tmp_path / "installed-state" / "state" / "studio.db",
        rehearsal_state_path=tmp_path / "rehearsal",
    )
    gates = set(plan["documents"]["validation_checklist"]["gates"])

    assert "repo_status_clean" in gates
    assert "backup_restore_rehearsal_passed" in gates
    assert "rehearsal_rehydration_passed" in gates
    assert "no_duplicate_authority_db_created" in gates
    assert "rollback_instructions_verified" in gates


def test_cutover_plan_source_does_not_hardcode_operator_home_path() -> None:
    upgrade_root = Path(core.upgrade.__file__).parent
    hardcoded_operator_home = "C:\\Users\\Example User"

    source_text = "\n".join(path.read_text(encoding="utf-8") for path in upgrade_root.glob("*.py"))

    assert hardcoded_operator_home not in source_text
