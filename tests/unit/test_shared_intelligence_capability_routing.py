from __future__ import annotations

from pathlib import Path

from core.event_store.studio_db import _connect
from core.shared_intelligence.adapter_alignment import register_default_adapter_authority_profiles
from core.shared_intelligence.authority import record_model_provider_profile
from core.shared_intelligence.capability_routing import (
    capability_route_summary,
    recommend_capability_route,
)
from core.shared_intelligence.result_normalization import record_normalized_adapter_result


def _db(tmp_path: Path) -> Path:
    return tmp_path / "capability-routing" / "studio.db"


def test_recommend_capability_route_persists_non_executing_route(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        _seed_route_inputs(conn)
        route = recommend_capability_route(
            conn,
            capability_route_id="route-code-1",
            task_class="code_implementation",
            required_capabilities=["code", "tool_use"],
            project_id="dream-studio",
            risk_level="medium",
            min_context_tokens=100000,
        )
        summary = capability_route_summary(conn, project_id="dream-studio")

    assert route["selected_adapter_id"] == "chatgpt"
    assert route["selected_model_profile_id"] == "openai-gpt-route"
    assert route["validation_required"] is True
    assert route["operator_approval_required"] is False
    assert route["policy_mutation_authorized"] is False
    assert route["execution_authorized"] is False
    assert summary["route_count"] == 1
    assert summary["routes"][0]["capability_route_id"] == "route-code-1"
    assert summary["routes"][0]["route_basis"]["model_matches"] == ["openai-gpt-route"]


def test_high_risk_route_requires_operator_approval_and_can_dry_run(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        _seed_route_inputs(conn)
        route = recommend_capability_route(
            conn,
            capability_route_id="route-research-approval",
            task_class="research_material_risk",
            required_capabilities=["reasoning"],
            project_id="dream-studio",
            risk_level="high",
            persist=False,
        )
        summary = capability_route_summary(conn, project_id="dream-studio")

    assert route["selected_adapter_id"] == "chatgpt"
    assert route["operator_approval_required"] is True
    assert summary["route_count"] == 0


def test_capability_route_summary_empty_state_is_derived_not_authority(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        summary = capability_route_summary(conn, project_id="missing")

    assert summary["derived_view"] is True
    assert summary["primary_authority"] is False
    assert summary["routing_authority"] is False
    assert summary["route_count"] == 0
    assert (
        summary["empty_state"]
        == "No capability route recommendations recorded for the selected scope."
    )


def test_capability_routing_uses_temp_db_not_live_db(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    live_db = Path.home() / ".dream-studio" / "state" / "studio.db"
    with _connect(db_path) as conn:
        _seed_route_inputs(conn)
        recommend_capability_route(
            conn,
            capability_route_id="route-code-1",
            task_class="code_implementation",
            required_capabilities=["code"],
        )

    assert db_path.is_file()
    assert db_path != live_db


def _seed_route_inputs(conn) -> None:
    register_default_adapter_authority_profiles(conn)
    record_model_provider_profile(
        conn,
        model_profile_id="openai-gpt-route",
        provider="openai",
        model_id="gpt-route",
        capability_tags=["code", "tool_use", "reasoning"],
        context_limit_tokens=200000,
        cost_profile={"authority": "recorded_estimate"},
        failure_modes=[],
        best_use_patterns=["bounded implementation"],
    )
    record_normalized_adapter_result(
        conn,
        result_id="chatgpt-green",
        adapter_id="chatgpt",
        project_id="dream-studio",
        raw_result={"result_type": "research", "status": "passed"},
    )
    conn.commit()
