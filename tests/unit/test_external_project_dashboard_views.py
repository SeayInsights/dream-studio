from __future__ import annotations

from core.projects.dashboard_views import build_external_project_dashboard_view


def test_external_dashboard_view_is_derived_and_non_authoritative() -> None:
    view = build_external_project_dashboard_view([])

    assert view["derived_view"] is True
    assert view["primary_authority"] is False
    assert view["routing_authority"] is False
    assert view["external_repo_inspected"] is False
    assert view["external_repo_mutated"] is False
    assert view["empty_state"] is True


def test_external_dashboard_card_shows_paused_target_and_risks() -> None:
    view = build_external_project_dashboard_view(
        [
            {
                "target_id": "external-a",
                "status": "paused",
                "source_boundary": "external_project",
                "dirty_state": "unknown",
            }
        ]
    )

    card = view["cards"][0]
    risk_ids = {risk["id"] for risk in card["risks"]}
    assert card["target_id"] == "external-a"
    assert card["resume_state"] == "paused"
    assert card["approval_status"] == "approval_required"
    assert card["mutation_allowed"] is False
    assert "dirty_state_not_clean" in risk_ids
    assert "operator_approval_required" in risk_ids
    assert view["summary"]["paused_count"] == 1


def test_external_dashboard_card_surfaces_resume_ready_validation_entrypoint() -> None:
    view = build_external_project_dashboard_view(
        [
            {
                "target_id": "external-b",
                "status": "paused",
                "source_boundary": "external_project",
                "dirty_state": "clean",
                "repo_clean": True,
                "operator_approval_refs": ["approval.json"],
                "source_evidence_refs": ["boundary.md"],
            }
        ]
    )

    card = view["cards"][0]
    assert card["resume_state"] == "resume_ready"
    assert card["approval_status"] == "approved_for_planning"
    assert card["next_action"] == "prepare_read_only_validation_work_order"
    assert card["validation_status"] == "not_run"
    assert card["commit_policy"]["commit_allowed"] is False
    assert view["summary"]["resume_ready_count"] == 1
