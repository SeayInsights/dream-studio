from __future__ import annotations

from pathlib import Path

import pytest

from core.event_store.studio_db import _connect
from core.shared_intelligence.authority import record_learning_event
from core.shared_intelligence.hardening_loop import (
    create_hardening_candidate_from_learning_event,
    hardening_candidate_lifecycle,
    record_hardening_validation,
    validate_hardening_loop_report,
)


def _db(tmp_path: Path) -> Path:
    return tmp_path / "hardening-loop" / "studio.db"


def test_learning_event_creates_non_executing_hardening_candidate(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        _seed_recurring_gap(conn)
        report = create_hardening_candidate_from_learning_event(
            conn,
            candidate_id="hardening-candidate-ds-core",
            learning_event_id="learn-gap-2",
            hardening_type="skill_instruction_update",
            proposed_version="route-first-no-prompt-chain",
            current_version="route-first",
            validation_plan=["run route-first regression tests"],
            rollback_plan="Restore route-first skill instructions.",
        )
        conn.commit()
        event_status = conn.execute(
            "SELECT promotion_status FROM learning_event_records WHERE learning_event_id = ?",
            ("learn-gap-2",),
        ).fetchone()["promotion_status"]

    assert validate_hardening_loop_report(report) == []
    assert report["candidate"]["candidate_id"] == "hardening-candidate-ds-core"
    assert report["candidate"]["status"] == "candidate"
    assert report["candidate"]["current_version"] == "route-first"
    assert report["candidate"]["proposed_version"] == "route-first-no-prompt-chain"
    assert report["candidate"]["recurrence_check"]["recurrence_key"] == "prompt-chain"
    assert report["recurrence_event_count"] == 2
    assert report["recurrence_detected"] is True
    assert report["execution_authorized"] is False
    assert event_status == "candidate"


def test_hardening_validation_updates_candidate_without_promoting_execution(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        _seed_recurring_gap(conn)
        create_hardening_candidate_from_learning_event(
            conn,
            candidate_id="hardening-candidate-ds-core",
            learning_event_id="learn-gap-2",
            hardening_type="skill_instruction_update",
            proposed_version="route-first-no-prompt-chain",
            validation_plan=["run route-first regression tests"],
            rollback_plan="Restore route-first skill instructions.",
        )
        report = record_hardening_validation(
            conn,
            candidate_id="hardening-candidate-ds-core",
            status="validated",
            validation_refs=["pytest://test_shared_intelligence_hardening_loop"],
            evidence_refs=["evidence://hardening-loop"],
            validation_summary="Focused recurrence validation passed.",
        )

    assert validate_hardening_loop_report(report) == []
    assert report["candidate"]["status"] == "validated"
    assert report["candidate"]["recurrence_check"]["validation_refs"] == [
        "pytest://test_shared_intelligence_hardening_loop"
    ]
    assert report["candidate"]["recurrence_check"]["execution_authorized"] is False
    assert report["requires_future_work_order"] is False
    assert "evidence://hardening-loop" in report["candidate"]["evidence_refs"]


def test_hardening_candidate_lifecycle_refuses_unknown_or_unattributed_events(
    tmp_path: Path,
) -> None:
    with _connect(_db(tmp_path)) as conn:
        _seed_recurring_gap(conn)
        record_learning_event(
            conn,
            learning_event_id="learn-unattributed",
            project_id="dream-studio",
            event_class="skill_gap",
            severity="medium",
            summary="Missing component identity should block hardening candidate creation.",
            promotion_status="observed",
        )
        with pytest.raises(ValueError, match="unknown learning_event_id"):
            create_hardening_candidate_from_learning_event(
                conn,
                candidate_id="missing",
                learning_event_id="missing",
                hardening_type="skill_instruction_update",
                proposed_version="unused",
                validation_plan=[],
                rollback_plan="unused",
            )
        with pytest.raises(ValueError, match="component_type and component_id"):
            create_hardening_candidate_from_learning_event(
                conn,
                candidate_id="unattributed",
                learning_event_id="learn-unattributed",
                hardening_type="skill_instruction_update",
                proposed_version="unused",
                validation_plan=[],
                rollback_plan="unused",
            )


def test_hardening_loop_uses_temp_db_not_live_db(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    live_db = Path.home() / ".dream-studio" / "state" / "studio.db"
    with _connect(db_path) as conn:
        _seed_recurring_gap(conn)
        create_hardening_candidate_from_learning_event(
            conn,
            candidate_id="hardening-candidate-ds-core",
            learning_event_id="learn-gap-2",
            hardening_type="skill_instruction_update",
            proposed_version="route-first-no-prompt-chain",
            validation_plan=["run route-first regression tests"],
            rollback_plan="Restore route-first skill instructions.",
        )
        report = hardening_candidate_lifecycle(conn, "hardening-candidate-ds-core")

    assert report["candidate"]["candidate_id"] == "hardening-candidate-ds-core"
    assert db_path.is_file()
    assert db_path != live_db


def _seed_recurring_gap(conn) -> None:
    base = {
        "project_id": "dream-studio",
        "milestone_id": "skill_workflow_hardening_loop_maturation",
        "task_id": "wo-hardening-loop",
        "process_run_id": "process-hardening-loop-test",
        "component_type": "skill",
        "component_id": "ds-core",
        "event_class": "skill_gap",
        "severity": "high",
        "recurrence_key": "prompt-chain",
        "promotion_status": "observed",
        "source_refs": ["sqlite:learning_event_records"],
        "evidence_refs": ["tests/unit/test_shared_intelligence_hardening_loop.py"],
    }
    record_learning_event(
        conn,
        learning_event_id="learn-gap-1",
        **base,
        summary="Skill allowed prompt chaining once.",
    )
    record_learning_event(
        conn,
        learning_event_id="learn-gap-2",
        **base,
        summary="Skill allowed prompt chaining again.",
    )
    conn.commit()
