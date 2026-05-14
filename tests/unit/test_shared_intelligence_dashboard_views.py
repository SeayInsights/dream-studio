from __future__ import annotations

from pathlib import Path

from core.event_store.studio_db import _connect
from core.shared_intelligence.adapter_alignment import register_default_adapter_authority_profiles
from core.shared_intelligence.authority import (
    record_hardening_candidate,
    record_learning_event,
    record_model_provider_profile,
)
from core.shared_intelligence.dashboard_views import (
    learning_hardening_dashboard_view,
    validate_learning_hardening_dashboard_view,
)
from core.shared_intelligence.hardening_loop import record_hardening_validation
from core.shared_intelligence.result_normalization import record_normalized_adapter_result


def _db(tmp_path: Path) -> Path:
    return tmp_path / "dashboard-learning-views" / "studio.db"


def test_learning_hardening_dashboard_view_composes_dashboard_sections(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        _seed_dashboard_learning(conn)
        view = learning_hardening_dashboard_view(conn, project_id="dream-studio")

    assert validate_learning_hardening_dashboard_view(view) == []
    assert view["model_name"] == "shared_intelligence_learning_hardening_dashboard_view"
    assert view["derived_view"] is True
    assert view["primary_authority"] is False
    assert view["dashboard_authority"] is False
    assert view["execution_authorized"] is False
    assert view["sections"]["lessons_learned"]["count"] == 4
    assert view["sections"]["recurring_failures"]["items"][0] == {
        "recurrence_key": "prompt-chaining-regression",
        "event_count": 2,
    }
    assert view["sections"]["hardening_candidates"]["count"] >= 1
    assert view["sections"]["attention_queue"]["count"] == 3
    assert view["sections"]["skill_health"]["items"][0]["component_id"] == "ds-core"
    assert (
        view["sections"]["workflow_improvement_opportunities"]["items"][0]["component_id"]
        == "release-gate"
    )
    assert (
        view["sections"]["model_comparisons"]["preferred_adapter_candidates"][0]["adapter_id"]
        == "chatgpt"
    )


def test_learning_hardening_dashboard_view_empty_state_is_non_authoritative(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    live_db = Path.home() / ".dream-studio" / "state" / "studio.db"
    with _connect(db_path) as conn:
        view = learning_hardening_dashboard_view(conn, project_id="missing")

    assert validate_learning_hardening_dashboard_view(view) == []
    assert view["sections"]["lessons_learned"]["count"] == 0
    assert view["sections"]["attention_queue"]["empty_state"] == (
        "No learning or hardening attention items are pending."
    )
    assert db_path.is_file()
    assert db_path != live_db


def test_learning_hardening_dashboard_validator_rejects_authority_drift(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        view = learning_hardening_dashboard_view(conn)

    view["primary_authority"] = True
    view["execution_authorized"] = True

    assert validate_learning_hardening_dashboard_view(view) == [
        "primary_authority must be false",
        "execution_authorized must be false",
    ]


def _seed_dashboard_learning(conn) -> None:
    register_default_adapter_authority_profiles(conn)
    record_normalized_adapter_result(
        conn,
        result_id="codex-result-failed",
        adapter_id="codex",
        project_id="dream-studio",
        raw_result={"result_type": "validation", "status": "failed"},
    )
    record_normalized_adapter_result(
        conn,
        result_id="chatgpt-result-green",
        adapter_id="chatgpt",
        project_id="dream-studio",
        raw_result={"result_type": "research", "status": "passed"},
    )
    common = {
        "project_id": "dream-studio",
        "milestone_id": "dashboard_learning_and_hardening_views",
        "task_id": "wo-dashboard-learning",
        "process_run_id": "process-dashboard-learning-test",
        "source_refs": ["sqlite:learning_event_records"],
        "evidence_refs": ["tests/unit/test_shared_intelligence_dashboard_views.py"],
    }
    record_learning_event(
        conn,
        learning_event_id="learn-repeat-1",
        **common,
        component_type="skill",
        component_id="ds-core",
        event_class="operator_correction",
        severity="medium",
        summary="Prompt chaining reappeared during dogfood.",
        recurrence_key="prompt-chaining-regression",
        promotion_status="observed",
    )
    record_learning_event(
        conn,
        learning_event_id="learn-repeat-2",
        **common,
        component_type="skill",
        component_id="ds-core",
        event_class="operator_correction",
        severity="high",
        summary="Prompt chaining reappeared after route decision.",
        recurrence_key="prompt-chaining-regression",
        promotion_status="candidate",
    )
    record_learning_event(
        conn,
        learning_event_id="learn-attention",
        **common,
        component_type="workflow",
        component_id="release-gate",
        event_class="route_mistake",
        severity="warning",
        summary="Release gate needs dashboard attention.",
        promotion_status="dashboard_attention",
    )
    record_learning_event(
        conn,
        learning_event_id="learn-approval",
        **common,
        component_type="adapter",
        component_id="codex",
        event_class="adapter_gap",
        severity="medium",
        summary="Adapter config projection requires explicit operator approval.",
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
        validation_plan=["focused recurrence test"],
        recurrence_check={"recurrence_key": "prompt-chaining-regression"},
        rollback_plan="Keep previous skill instructions available.",
    )
    record_hardening_validation(
        conn,
        candidate_id="hardening-ds-core",
        status="validated",
        validation_refs=["pytest://test_shared_intelligence_dashboard_views"],
        validation_summary="Dashboard learning view validation passed.",
    )
    record_model_provider_profile(
        conn,
        model_profile_id="openai-gpt-feedback",
        provider="openai",
        model_id="gpt-feedback",
        capability_tags=["code"],
        context_limit_tokens=200000,
        failure_modes=["tool_retry"],
        cost_profile={"authority": "recorded_estimate"},
    )
    conn.commit()
