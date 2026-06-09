from __future__ import annotations

from pathlib import Path

from core.event_store.studio_db import _connect
from core.shared_intelligence.authority import record_learning_event
from core.shared_intelligence.hardening_loop import (
    create_hardening_candidate_from_learning_event,
    record_hardening_validation,
)
from core.shared_intelligence.skill_versioning import (
    skill_version_evaluation_report,
    validate_skill_version_evaluation_report,
)


def _db(tmp_path: Path) -> Path:
    return tmp_path / "skill-versioning" / "studio.db"


def test_validated_skill_candidate_is_ready_for_operator_review(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        _seed_learning_event(
            conn,
            learning_event_id="learn-skill-gap",
            component_type="skill",
            component_id="ds-core",
            severity="medium",
        )
        create_hardening_candidate_from_learning_event(
            conn,
            candidate_id="candidate-ds-core-v2",
            learning_event_id="learn-skill-gap",
            hardening_type="skill_instruction_update",
            current_version="route-first-v1",
            proposed_version="route-first-v2",
            validation_plan=["run route-first regression tests"],
            rollback_plan="Restore route-first-v1 instructions.",
        )
        record_hardening_validation(
            conn,
            candidate_id="candidate-ds-core-v2",
            status="validated",
            validation_refs=["pytest://test_route_first_regression"],
            evidence_refs=["evidence://skill-versioning"],
            validation_summary="Focused skill regression tests passed.",
        )
        report = skill_version_evaluation_report(
            conn, component_type="skill", component_id="ds-core"
        )

    assert validate_skill_version_evaluation_report(report) == []
    assert report["candidate_count"] == 1
    assert report["evaluation_status_counts"]["promotion_ready"] == 1
    evaluation = report["evaluations"][0]
    assert evaluation["candidate_id"] == "candidate-ds-core-v2"
    assert evaluation["evaluation_status"] == "promotion_ready"
    assert evaluation["current_version"] == "route-first-v1"
    assert evaluation["proposed_version"] == "route-first-v2"
    assert evaluation["rollback_plan_present"] is True
    assert evaluation["validation_refs"] == ["pytest://test_route_first_regression"]
    assert evaluation["requires_operator_approval"] is True
    assert evaluation["promotion_execution_authorized"] is False


def test_candidate_without_validation_stays_advisory_not_ready(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        _seed_learning_event(
            conn,
            learning_event_id="learn-workflow-gap",
            component_type="workflow",
            component_id="release-gate",
            severity="low",
        )
        create_hardening_candidate_from_learning_event(
            conn,
            candidate_id="candidate-release-gate-v2",
            learning_event_id="learn-workflow-gap",
            hardening_type="workflow_evaluation_update",
            current_version="release-gate-v1",
            proposed_version="release-gate-v2",
            validation_plan=["run CI release gate tests"],
            rollback_plan="Restore release-gate-v1.",
        )
        report = skill_version_evaluation_report(conn, component_type="workflow")

    evaluation = report["evaluations"][0]
    assert evaluation["evaluation_status"] == "needs_validation"
    assert evaluation["requires_future_work_order"] is True
    assert evaluation["promotion_execution_authorized"] is False


def test_candidate_without_rollback_plan_cannot_be_promoted(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        _seed_learning_event(
            conn,
            learning_event_id="learn-hook-gap",
            component_type="hook",
            component_id="UserPromptSubmit",
            severity="high",
        )
        create_hardening_candidate_from_learning_event(
            conn,
            candidate_id="candidate-hook-v2",
            learning_event_id="learn-hook-gap",
            hardening_type="hook_failure_handling_update",
            current_version="prompt-hook-v1",
            proposed_version="prompt-hook-v2",
            validation_plan=["run hook dispatcher tests"],
            rollback_plan="",
        )
        record_hardening_validation(
            conn,
            candidate_id="candidate-hook-v2",
            status="validated",
            validation_refs=["pytest://test_hook_dispatcher"],
        )
        report = skill_version_evaluation_report(conn, component_type="hook")

    evaluation = report["evaluations"][0]
    assert evaluation["evaluation_status"] == "needs_rollback_plan"
    assert evaluation["risk_level"] == "high"
    assert evaluation["requires_operator_approval"] is True
    assert evaluation["promotion_execution_authorized"] is False


def test_report_empty_state_and_temp_db_boundary(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    live_db = Path.home() / ".dream-studio" / "state" / "studio.db"
    with _connect(db_path) as conn:
        report = skill_version_evaluation_report(conn)

    assert validate_skill_version_evaluation_report(report) == []
    assert report["candidate_count"] == 0
    assert report["promotion_execution_authorized"] is False
    assert report["empty_state"] == (
        "No skill, workflow, or hook hardening candidates are ready for version evaluation."
    )
    assert db_path.is_file()
    assert db_path != live_db


def test_report_validator_rejects_execution_authorization(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        report = skill_version_evaluation_report(conn)

    report["promotion_execution_authorized"] = True

    assert validate_skill_version_evaluation_report(report) == [
        "promotion_execution_authorized must be false"
    ]


def _seed_learning_event(
    conn,
    *,
    learning_event_id: str,
    component_type: str,
    component_id: str,
    severity: str,
) -> None:
    record_learning_event(
        conn,
        learning_event_id=learning_event_id,
        project_id="dream-studio",
        milestone_id="skill_versioning_and_evaluation_maturation",
        task_id="wo-skill-versioning-evaluation",
        process_run_id="process-skill-versioning-test",
        component_type=component_type,
        component_id=component_id,
        event_class="skill_gap" if component_type == "skill" else "workflow_gap",
        severity=severity,
        summary=f"{component_id} needs versioned hardening.",
        recurrence_key=f"{component_type}:{component_id}:versioning",
        promotion_status="candidate",
        source_refs=["sqlite:learning_event_records"],
        evidence_refs=["tests/unit/test_shared_intelligence_skill_versioning.py"],
    )
    conn.commit()
