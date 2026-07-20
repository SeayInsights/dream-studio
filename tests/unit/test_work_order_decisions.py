from __future__ import annotations

from pathlib import Path

import pytest


def _work_order(target_path: Path, *, work_order_id: str = "wo-decision-001") -> dict:
    return {
        "work_order_id": work_order_id,
        "project_name": "Decision Test",
        "target_path": str(target_path),
        "objective": "Request an operator decision.",
        "approval_mode": "observe_only",
        "risk_level": "medium",
        "scope": {"include": ["README.md"], "exclude": ["secrets"]},
        "allowed_skills": ["ds-core"],
        "allowed_agents": [],
        "workflow": "decision",
        "forbidden_actions": ["no edits", "no commits", "no target repo mutation"],
        "validation_commands": ["python -m pytest -q"],
        "expected_outputs": ["decision evidence"],
        "stop_conditions": ["missing decision"],
        "created_by": "pytest",
        "created_at": "2026-05-11T00:00:00Z",
        "status": "reported",
        "storage_class": "file_backed",
        "privacy_export_classification": "local_only",
    }


def _snapshot(path: Path) -> dict[str, str]:
    return {
        str(item.relative_to(path)): item.read_text(encoding="utf-8")
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def test_create_decision_request_for_push_planning(tmp_path) -> None:
    from core.work_orders.decisions import create_decision_request, decision_status
    from core.work_orders.storage import save_work_order

    target = tmp_path / "target"
    target.mkdir()
    (target / "README.md").write_text("before\n", encoding="utf-8")
    before = _snapshot(target)
    storage_root = tmp_path / "store"
    save_work_order(_work_order(target), storage_root=storage_root)

    request = create_decision_request(
        "wo-decision-001",
        phase_type="push_planning",
        question="Choose push path.",
        recommended_decision="RUN_BROADER_VALIDATION_FIRST",
        storage_root=storage_root,
    )
    status = decision_status("wo-decision-001", storage_root=storage_root)

    assert request["status"] == "pending_operator_decision"
    assert request["allowed_decisions"] == [
        "PUSH_READY_WITH_APPROVAL",
        "RUN_BROADER_VALIDATION_FIRST",
        "HOLD",
        "FAIL",
    ]
    assert status["status"] == "pending_operator_decision"
    # WO-FILESDB-C4: decisions live in the authority-free packet store, not decisions/*.json.
    from core.work_orders.packet_store import get_packet_artifact

    assert not (storage_root / "wo-decision-001" / "decisions").exists()
    assert get_packet_artifact("wo-decision-001", "decision_request", storage_root=storage_root)
    assert _snapshot(target) == before
    assert not (tmp_path / "home" / ".dream-studio" / "state" / "studio.db").exists()


def test_valid_operator_decision_records_file_backed_artifact(tmp_path) -> None:
    from core.work_orders.decisions import (
        create_decision_request,
        decision_status,
        record_operator_decision,
    )
    from core.work_orders.storage import save_work_order

    target = tmp_path / "target"
    target.mkdir()
    storage_root = tmp_path / "store"
    save_work_order(_work_order(target), storage_root=storage_root)
    create_decision_request(
        "wo-decision-001",
        phase_type="push_planning",
        question="Choose push path.",
        recommended_decision="RUN_BROADER_VALIDATION_FIRST",
        storage_root=storage_root,
    )

    decision = record_operator_decision(
        "wo-decision-001",
        decision="RUN_BROADER_VALIDATION_FIRST",
        reason="Run broader validation before push.",
        decided_by="operator",
        storage_root=storage_root,
    )
    status = decision_status("wo-decision-001", storage_root=storage_root)

    assert decision["decision"] == "RUN_BROADER_VALIDATION_FIRST"
    assert decision["approved_next_handoff_type"] == "normal_next_work_order"
    assert status["status"] == "decided"
    # WO-FILESDB-C4: operator decision lives in the packet store, not on disk.
    from core.work_orders.packet_store import get_packet_artifact

    assert get_packet_artifact("wo-decision-001", "operator_decision", storage_root=storage_root)


def test_invalid_decision_fails(tmp_path) -> None:
    from core.work_orders.decisions import create_decision_request, record_operator_decision
    from core.work_orders.models import WorkOrderError
    from core.work_orders.storage import save_work_order

    target = tmp_path / "target"
    target.mkdir()
    storage_root = tmp_path / "store"
    save_work_order(_work_order(target), storage_root=storage_root)
    create_decision_request(
        "wo-decision-001",
        phase_type="push_planning",
        question="Choose push path.",
        recommended_decision="HOLD",
        storage_root=storage_root,
    )

    with pytest.raises(WorkOrderError):
        record_operator_decision(
            "wo-decision-001",
            decision="PUSH_NOW",
            reason="not allowed",
            decided_by="operator",
            storage_root=storage_root,
        )


def test_missing_reason_fails_when_required(tmp_path) -> None:
    from core.work_orders.decisions import create_decision_request, record_operator_decision
    from core.work_orders.models import WorkOrderError
    from core.work_orders.storage import save_work_order

    target = tmp_path / "target"
    target.mkdir()
    storage_root = tmp_path / "store"
    save_work_order(_work_order(target), storage_root=storage_root)
    create_decision_request(
        "wo-decision-001",
        phase_type="push_planning",
        question="Choose push path.",
        recommended_decision="HOLD",
        storage_root=storage_root,
    )

    with pytest.raises(WorkOrderError):
        record_operator_decision(
            "wo-decision-001",
            decision="HOLD",
            reason="",
            decided_by="operator",
            storage_root=storage_root,
        )
