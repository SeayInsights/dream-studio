from __future__ import annotations

from pathlib import Path

from core.event_store.studio_db import _connect
from core.shared_intelligence.adapter_alignment import register_default_adapter_authority_profiles
from core.shared_intelligence.authority import record_learning_event
from core.shared_intelligence.multi_agent_demo import (
    multi_agent_shared_intelligence_demo_packet,
    validate_multi_agent_shared_intelligence_demo_packet,
)
from core.shared_intelligence.result_normalization import record_normalized_adapter_result


def _db(tmp_path: Path) -> Path:
    return tmp_path / "multi-agent-demo" / "studio.db"


def test_multi_agent_demo_proves_continuity_from_codex_to_chatgpt(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        _seed_demo(conn)
        packet = multi_agent_shared_intelligence_demo_packet(
            conn,
            project_id="dream-studio",
            first_adapter_id="codex",
            second_adapter_id="chatgpt",
            milestone_id="multi_agent_shared_intelligence_demo",
            task_id="wo-multi-agent-demo",
        )

    assert validate_multi_agent_shared_intelligence_demo_packet(packet) == []
    assert packet["demo_passed"] is True
    assert packet["external_model_calls_performed"] is False
    assert packet["adapter_private_memory_required"] is False
    assert packet["demo_steps"][0] == {
        "step": "first_adapter_records_result",
        "adapter_id": "codex",
        "evidence_count": 1,
        "satisfied": True,
    }
    assert packet["demo_steps"][1]["adapter_id"] == "chatgpt"
    assert packet["independence_validation"]["independence_passed"] is True
    assert packet["adapter_result_summary"]["adapter_counts"] == {"codex": 1}
    assert packet["dashboard_learning_hardening_view"]["sections"]["lessons_learned"]["count"] == 1


def test_multi_agent_demo_requires_recorded_first_adapter_result(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        register_default_adapter_authority_profiles(conn)
        packet = multi_agent_shared_intelligence_demo_packet(
            conn,
            project_id="dream-studio",
            first_adapter_id="codex",
            second_adapter_id="claude",
        )

    assert packet["demo_passed"] is False
    assert packet["demo_steps"][0]["satisfied"] is False
    assert packet["demo_steps"][1]["satisfied"] is True
    assert validate_multi_agent_shared_intelligence_demo_packet(packet) == []


def test_multi_agent_demo_uses_temp_db_not_live_db(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    live_db = Path.home() / ".dream-studio" / "state" / "studio.db"
    with _connect(db_path) as conn:
        _seed_demo(conn)
        packet = multi_agent_shared_intelligence_demo_packet(
            conn,
            project_id="dream-studio",
            first_adapter_id="codex",
            second_adapter_id="chatgpt",
        )

    assert packet["demo_passed"] is True
    assert db_path.is_file()
    assert db_path != live_db


def test_multi_agent_demo_validator_rejects_execution_authority() -> None:
    report = {
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "external_model_calls_performed": True,
        "adapter_private_memory_required": True,
        "execution_authorized": True,
        "demo_steps": [],
    }

    assert validate_multi_agent_shared_intelligence_demo_packet(report) == [
        "external_model_calls_performed must be false",
        "adapter_private_memory_required must be false",
        "execution_authorized must be false",
        "demo_steps must be present",
    ]


def _seed_demo(conn) -> None:
    register_default_adapter_authority_profiles(conn)
    record_normalized_adapter_result(
        conn,
        result_id="codex-demo-result",
        adapter_id="codex",
        project_id="dream-studio",
        milestone_id="multi_agent_shared_intelligence_demo",
        task_id="wo-multi-agent-demo",
        raw_result={
            "result_type": "code_change",
            "status": "completed",
            "summary": "Codex implemented a bounded shared intelligence slice.",
            "evidence_refs": ["tests/unit/test_shared_intelligence_multi_agent_demo.py"],
        },
    )
    record_learning_event(
        conn,
        learning_event_id="learn-demo-continuity",
        project_id="dream-studio",
        milestone_id="multi_agent_shared_intelligence_demo",
        task_id="wo-multi-agent-demo",
        component_type="adapter",
        component_id="codex",
        event_class="successful_hardening",
        severity="info",
        summary="Dream Studio preserved adapter result for another model to resume.",
        promotion_status="observed",
    )
    conn.commit()
