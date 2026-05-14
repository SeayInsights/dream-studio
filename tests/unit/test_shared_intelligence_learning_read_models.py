from __future__ import annotations

from pathlib import Path

from core.event_store.studio_db import _connect
from core.shared_intelligence.authority import (
    record_hardening_candidate,
    record_learning_event,
)
from core.shared_intelligence.read_models import (
    component_learning_health,
    learning_event_summary,
    learning_promotion_queue,
)


def _db(tmp_path: Path) -> Path:
    return tmp_path / "learning-read-models" / "studio.db"


def test_learning_event_summary_surfaces_recurrence_and_promotion_paths(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        _seed_learning(conn)
        summary = learning_event_summary(conn, project_id="dream-studio")

    assert summary["model_name"] == "shared_intelligence_learning_event_summary"
    assert summary["derived_view"] is True
    assert summary["primary_authority"] is False
    assert summary["routing_authority"] is False
    assert summary["source_tables"] == [
        "learning_event_records",
        "hardening_candidate_records",
    ]
    assert summary["event_count"] == 4
    assert summary["event_class_counts"]["operator_correction"] == 2
    assert summary["severity_counts"]["high"] == 1
    assert summary["promotion_status_counts"]["operator_approval_required"] == 1
    assert summary["recurrence_signals"][0] == {
        "recurrence_key": "prompt-chaining-regression",
        "event_count": 2,
    }
    assert summary["operator_approval_items"][0]["learning_event_id"] == "learn-approval"
    assert summary["dashboard_attention_items"][0]["learning_event_id"] == "learn-attention"
    assert summary["candidate_events"][0]["learning_event_id"] == "learn-repeat-2"
    assert summary["hardening_candidates"][0]["candidate_id"] == "hardening-ds-core"


def test_component_learning_health_groups_events_and_candidates(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        _seed_learning(conn)
        health = component_learning_health(conn, project_id="dream-studio")

    ds_core = next(
        row
        for row in health["components"]
        if row["component_type"] == "skill" and row["component_id"] == "ds-core"
    )
    assert ds_core["event_count"] == 3
    assert ds_core["highest_severity"] == "high"
    assert ds_core["event_class_counts"]["operator_correction"] == 2
    assert ds_core["promotion_status_counts"]["candidate"] == 1
    assert ds_core["recurrence_keys"] == ["prompt-chaining-regression"]
    assert ds_core["hardening_candidate_count"] == 1
    assert ds_core["hardening_candidates"][0]["validation_plan"] == [
        "focused recurrence test",
        "route model review",
    ]


def test_learning_promotion_queue_is_dashboard_safe_empty_state(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        empty = learning_promotion_queue(conn, project_id="missing-project")
        _seed_learning(conn)
        queue = learning_promotion_queue(conn, project_id="dream-studio")

    assert empty["derived_view"] is True
    assert empty["promotion_paths"] == {}
    assert empty["empty_state"] == "No learning events are awaiting promotion."
    assert queue["operator_approval_required"][0]["learning_event_id"] == "learn-approval"
    assert queue["dashboard_attention"][0]["learning_event_id"] == "learn-attention"
    assert queue["candidate"][0]["learning_event_id"] == "learn-repeat-2"
    assert queue["hardening_candidates"][0]["status"] == "candidate"


def test_learning_read_models_use_temp_db_not_live_db(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    live_db = Path.home() / ".dream-studio" / "state" / "studio.db"
    with _connect(db_path) as conn:
        summary = learning_event_summary(conn)

    assert summary["event_count"] == 0
    assert db_path.is_file()
    assert db_path != live_db


def _seed_learning(conn) -> None:
    base = {
        "project_id": "dream-studio",
        "milestone_id": "learning_event_spine_maturation",
        "task_id": "wo-learning-event-spine",
        "process_run_id": "process-learning-read-model-test",
        "component_type": "skill",
        "component_id": "ds-core",
        "source_refs": ["sqlite:learning_event_records"],
        "evidence_refs": ["tests/unit/test_shared_intelligence_learning_read_models.py"],
    }
    record_learning_event(
        conn,
        learning_event_id="learn-repeat-1",
        **base,
        event_class="operator_correction",
        severity="medium",
        summary="Prompt chaining reappeared during dogfood.",
        recurrence_key="prompt-chaining-regression",
        promotion_status="observed",
    )
    record_learning_event(
        conn,
        learning_event_id="learn-repeat-2",
        **base,
        event_class="operator_correction",
        severity="high",
        summary="Prompt chaining reappeared after route decision.",
        recurrence_key="prompt-chaining-regression",
        promotion_status="candidate",
    )
    record_learning_event(
        conn,
        learning_event_id="learn-attention",
        **base,
        event_class="route_mistake",
        severity="warning",
        summary="Route model needs dashboard attention when release gate blocks.",
        promotion_status="dashboard_attention",
    )
    record_learning_event(
        conn,
        learning_event_id="learn-approval",
        project_id="dream-studio",
        milestone_id="learning_event_spine_maturation",
        task_id="wo-learning-event-spine",
        process_run_id="process-learning-read-model-test",
        component_type="adapter",
        component_id="codex",
        event_class="adapter_gap",
        severity="medium",
        summary="Adapter config projection requires explicit operator approval.",
        recurrence_key="adapter-config-projection-boundary",
        promotion_status="operator_approval_required",
    )
    record_hardening_candidate(
        conn,
        candidate_id="hardening-ds-core",
        learning_event_id="learn-repeat-2",
        component_type="skill",
        component_id="ds-core",
        current_version="route-first",
        proposed_version="route-first-no-prompt-chain",
        hardening_type="skill_instruction_update",
        status="candidate",
        validation_plan=["focused recurrence test", "route model review"],
        recurrence_check={"recurrence_key": "prompt-chaining-regression"},
        rollback_plan="Keep previous skill instructions available.",
    )
    conn.commit()
