from __future__ import annotations

from pathlib import Path

from core.event_store.studio_db import _connect
from core.shared_intelligence.authority import record_learning_event
from core.shared_intelligence.promotion_policy import (
    learning_promotion_decision,
    learning_promotion_policy_report,
)


def _db(tmp_path: Path) -> Path:
    return tmp_path / "learning-promotion-policy" / "studio.db"


def test_learning_promotion_decision_maps_event_classes_without_execution() -> None:
    decision = learning_promotion_decision(
        {
            "learning_event_id": "learn-skill",
            "event_class": "skill_gap",
            "severity": "medium",
            "promotion_status": "candidate",
            "component_type": "skill",
            "component_id": "ds-core",
            "recurrence_key": "prompt-chain",
        }
    )

    assert decision["recommended_target"] == "skill_hardening_candidate"
    assert decision["recurrence_sensitive"] is True
    assert decision["requires_future_work_order"] is True
    assert decision["promotion_execution_authorized"] is False


def test_learning_promotion_policy_report_groups_targets_and_operator_approvals(
    tmp_path: Path,
) -> None:
    with _connect(_db(tmp_path)) as conn:
        _seed_policy_events(conn)
        report = learning_promotion_policy_report(conn, project_id="dream-studio")

    assert report["model_name"] == "shared_intelligence_learning_promotion_policy_report"
    assert report["derived_view"] is True
    assert report["primary_authority"] is False
    assert report["promotion_execution_authorized"] is False
    assert report["decision_count"] == 4
    assert report["target_counts"]["skill_hardening_candidate"] == 1
    assert report["target_counts"]["dashboard_attention_item"] == 1
    assert report["target_counts"]["operator_approval_item"] == 1
    assert report["target_counts"]["route_policy_candidate"] == 1
    assert report["operator_approval_required"][0]["learning_event_id"] == "learn-approval"


def test_high_risk_adapter_or_route_policy_requires_operator_approval() -> None:
    route = learning_promotion_decision(
        {
            "learning_event_id": "learn-route",
            "event_class": "route_mistake",
            "severity": "high",
            "promotion_status": "candidate",
        }
    )
    adapter = learning_promotion_decision(
        {
            "learning_event_id": "learn-adapter",
            "event_class": "adapter_gap",
            "severity": "critical",
            "promotion_status": "candidate",
        }
    )

    assert route["requires_operator_approval"] is True
    assert adapter["requires_operator_approval"] is True
    assert route["promotion_execution_authorized"] is False
    assert adapter["promotion_execution_authorized"] is False


def test_learning_promotion_policy_empty_state_and_temp_db(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    live_db = Path.home() / ".dream-studio" / "state" / "studio.db"
    with _connect(db_path) as conn:
        report = learning_promotion_policy_report(conn, project_id="missing")

    assert report["decision_count"] == 0
    assert report["empty_state"] == "No learning events recorded for promotion policy evaluation."
    assert db_path.is_file()
    assert db_path != live_db


def _seed_policy_events(conn) -> None:
    common = {
        "project_id": "dream-studio",
        "milestone_id": "learning_promotion_policy",
        "task_id": "wo-learning-promotion-policy",
        "process_run_id": "process-learning-promotion-policy",
        "source_refs": ["sqlite:learning_event_records"],
        "evidence_refs": ["tests/unit/test_shared_intelligence_learning_promotion_policy.py"],
    }
    record_learning_event(
        conn,
        learning_event_id="learn-skill",
        **common,
        component_type="skill",
        component_id="ds-core",
        event_class="skill_gap",
        severity="medium",
        summary="Skill needs hardening.",
        promotion_status="candidate",
    )
    record_learning_event(
        conn,
        learning_event_id="learn-dashboard",
        **common,
        event_class="validation_failure",
        severity="medium",
        summary="Validation failure needs dashboard attention.",
        promotion_status="dashboard_attention",
    )
    record_learning_event(
        conn,
        learning_event_id="learn-approval",
        **common,
        event_class="adapter_gap",
        severity="high",
        summary="Adapter policy needs operator approval.",
        promotion_status="operator_approval_required",
    )
    record_learning_event(
        conn,
        learning_event_id="learn-route",
        **common,
        event_class="route_mistake",
        severity="low",
        summary="Route policy candidate can be planned.",
        promotion_status="candidate",
    )
    conn.commit()
