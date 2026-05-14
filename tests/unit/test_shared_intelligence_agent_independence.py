from __future__ import annotations

from pathlib import Path

from core.event_store.studio_db import _connect
from core.shared_intelligence.adapter_alignment import register_default_adapter_authority_profiles
from core.shared_intelligence.agent_independence import (
    agent_model_independence_validation,
    validate_agent_model_independence_report,
)
from core.shared_intelligence.authority import record_learning_event


def _db(tmp_path: Path) -> Path:
    return tmp_path / "agent-independence" / "studio.db"


def test_second_adapter_can_resume_from_sqlite_authority_without_private_memory(
    tmp_path: Path,
) -> None:
    with _connect(_db(tmp_path)) as conn:
        register_default_adapter_authority_profiles(conn)
        record_learning_event(
            conn,
            learning_event_id="learn-agent-independence",
            project_id="dream-studio",
            milestone_id="agent_model_independence_validation",
            task_id="wo-agent-independence",
            component_type="adapter",
            component_id="codex",
            event_class="successful_hardening",
            severity="info",
            summary="Codex produced evidence that ChatGPT can resume from authority.",
            promotion_status="observed",
        )
        report = agent_model_independence_validation(
            conn,
            source_adapter_id="codex",
            target_adapter_id="chatgpt",
            project_id="dream-studio",
            milestone_id="agent_model_independence_validation",
            task_id="wo-agent-independence",
        )

    assert validate_agent_model_independence_report(report) == []
    assert report["independence_passed"] is True
    assert report["model_private_memory_required"] is False
    assert report["external_model_call_performed"] is False
    assert report["source_packet"]["adapter_id"] == "codex"
    assert report["target_packet"]["adapter_id"] == "chatgpt"
    assert report["target_packet"]["authority_boundary"]["sqlite_is_source_authority"] is True
    assert report["target_packet"]["learning_event_summary"]["event_count"] == 1
    assert (
        "Use SQLite authority and evidence refs as the source of truth."
        in report["target_packet"]["resume_instructions"]
    )


def test_agent_independence_validation_uses_temp_db_not_live_db(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    live_db = Path.home() / ".dream-studio" / "state" / "studio.db"
    with _connect(db_path) as conn:
        register_default_adapter_authority_profiles(conn)
        report = agent_model_independence_validation(
            conn,
            source_adapter_id="codex",
            target_adapter_id="claude",
            project_id="dream-studio",
        )

    assert report["independence_passed"] is True
    assert db_path.is_file()
    assert db_path != live_db


def test_agent_independence_validator_rejects_private_memory_dependency() -> None:
    report = {
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "external_model_call_performed": True,
        "adapter_config_write_required": False,
        "model_private_memory_required": True,
        "source_missing_sections": ["authority_context"],
        "target_missing_sections": [],
    }

    assert validate_agent_model_independence_report(report) == [
        "external_model_call_performed must be false",
        "model_private_memory_required must be false",
        "source packet is missing required sections",
    ]
