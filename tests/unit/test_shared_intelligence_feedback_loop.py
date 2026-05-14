from __future__ import annotations

from pathlib import Path

from core.event_store.studio_db import _connect
from core.shared_intelligence.adapter_alignment import register_default_adapter_authority_profiles
from core.shared_intelligence.authority import record_learning_event, record_model_provider_profile
from core.shared_intelligence.feedback_loop import cross_model_learning_feedback
from core.shared_intelligence.result_normalization import record_normalized_adapter_result


def _db(tmp_path: Path) -> Path:
    return tmp_path / "feedback-loop" / "studio.db"


def test_cross_model_feedback_recommends_hardening_and_preference_candidates(
    tmp_path: Path,
) -> None:
    with _connect(_db(tmp_path)) as conn:
        _seed_feedback(conn)
        feedback = cross_model_learning_feedback(conn, project_id="dream-studio")

    actions = {(item["action"], item["target_id"]) for item in feedback["recommendations"]}
    assert feedback["derived_view"] is True
    assert feedback["primary_authority"] is False
    assert feedback["routing_authority"] is False
    assert feedback["policy_mutation_authorized"] is False
    assert ("harden_adapter", "codex") in actions
    assert ("prefer_adapter_candidate", "chatgpt") in actions
    assert ("harden_skill", "ds-core") in actions
    assert ("review_model_profile", "openai-gpt-feedback") in actions
    assert feedback["preferred_adapter_candidates"][0]["adapter_id"] == "chatgpt"
    assert feedback["preferred_adapter_candidates"][0]["policy_mutation_authorized"] is False
    assert all(item["execution_authorized"] is False for item in feedback["recommendations"])


def test_cross_model_feedback_empty_state_is_non_authoritative(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        feedback = cross_model_learning_feedback(conn, project_id="missing")

    assert feedback["recommendations"] == []
    assert feedback["preferred_adapter_candidates"] == []
    assert (
        feedback["empty_state"]
        == "No cross-model learning feedback is available from recorded facts."
    )
    assert feedback["policy_mutation_authorized"] is False


def test_cross_model_feedback_uses_temp_db_not_live_db(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    live_db = Path.home() / ".dream-studio" / "state" / "studio.db"
    with _connect(db_path) as conn:
        _seed_feedback(conn)
        feedback = cross_model_learning_feedback(conn, project_id="dream-studio")

    assert feedback["recommendations"]
    assert db_path.is_file()
    assert db_path != live_db


def _seed_feedback(conn) -> None:
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
    record_learning_event(
        conn,
        learning_event_id="learning-ds-core-repeat",
        project_id="dream-studio",
        component_type="skill",
        component_id="ds-core",
        event_class="skill_gap",
        severity="high",
        summary="Skill repeated a route mistake.",
        recurrence_key="route-mistake",
        promotion_status="candidate",
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
