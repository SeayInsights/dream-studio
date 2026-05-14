from __future__ import annotations

import pytest

from core.work_orders import WorkOrderError, build_work_order_sequence
from core.work_orders.validation import validate_work_order


def test_build_work_order_sequence_links_valid_drafts(tmp_path) -> None:
    sequence = build_work_order_sequence(
        project_name="Dream Studio",
        target_path=tmp_path,
        created_at="2026-05-13T00:00:00Z",
        default_validation_commands=[
            "python -m pytest tests/unit/test_work_order_sequencing.py -q --tb=line"
        ],
        milestones=[
            {
                "milestone_id": "alpha_maturation",
                "objective": "Mature alpha capability with bounded validation.",
                "risk_level": "low",
                "approval_mode": "approval_required",
            },
            {
                "milestone_id": "beta_maturation",
                "objective": "Mature beta capability after alpha evidence exists.",
                "risk_level": "medium",
                "approval_mode": "approval_required",
            },
        ],
    )

    first, second = sequence["work_orders"]

    assert sequence["draft_only"] is True
    assert sequence["execution_authorized"] is False
    assert first["sequence"]["next_work_order_id"] == second["work_order_id"]
    assert first["sequence"]["previous_work_order_id"] is None
    assert second["sequence"]["previous_work_order_id"] == first["work_order_id"]
    assert second["sequence"]["route_decision_on_success"] == "milestone_complete"
    assert first["sequence"]["execution_authorized_by_sequence"] is False
    assert validate_work_order(first).ok is True
    assert validate_work_order(second).ok is True


def test_work_order_sequence_rejects_missing_milestone_data(tmp_path) -> None:
    with pytest.raises(WorkOrderError, match="milestone_id is required"):
        build_work_order_sequence(
            project_name="Dream Studio",
            target_path=tmp_path,
            milestones=[{"objective": "missing id"}],
        )


def test_work_order_sequence_does_not_grant_mutation_or_cleanup_authority(tmp_path) -> None:
    sequence = build_work_order_sequence(
        project_name="Dream Studio",
        target_path=tmp_path,
        milestones=[
            {
                "milestone_id": "cleanup_planning",
                "objective": "Plan cleanup without executing cleanup.",
                "include": ["cleanup manifest review"],
            }
        ],
    )
    work_order = sequence["work_orders"][0]
    forbidden = "\n".join(work_order["forbidden_actions"]).lower()

    assert "delete" in forbidden
    assert "archive" in forbidden
    assert "live sqlite db" in forbidden
    assert sequence["execution_authorized"] is False
