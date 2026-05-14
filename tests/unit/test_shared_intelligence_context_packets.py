from __future__ import annotations

import json
from pathlib import Path

from core.event_store.studio_db import _connect
from core.shared_intelligence.adapter_alignment import register_default_adapter_authority_profiles
from core.shared_intelligence.authority import (
    record_artifact_authority,
    record_learning_event,
    record_model_provider_profile,
)
from core.shared_intelligence.context_packets import (
    generate_shared_context_packet,
    shared_context_packet_policy,
)


def _db(tmp_path: Path) -> Path:
    return tmp_path / "shared-context-packets" / "studio.db"


def test_generate_shared_context_packet_from_sqlite_authority_and_persist(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        _seed_context(conn)
        packet = generate_shared_context_packet(
            conn,
            packet_id="packet-codex-resume",
            adapter_id="codex",
            packet_type="codex_resume",
            project_id="dream-studio",
            milestone_id="shared_context_packet_generation",
            task_id="wo-context-packets",
            process_run_id="process-context-packets",
        )
        saved = conn.execute(
            "SELECT * FROM shared_context_packets WHERE packet_id = ?",
            ("packet-codex-resume",),
        ).fetchone()

    payload = json.loads(saved["payload_json"])
    assert packet["packet_schema"] == "dream_studio.shared_context.v2"
    assert packet["source_authority"] == "sqlite"
    assert packet["model_private_memory_required"] is False
    assert packet["adapter_config_write_required"] is False
    assert packet["adapter_alignment"]["all_adapters_are_projections"] is True
    assert packet["model_provider_registry"]["model_count"] == 1
    assert packet["learning_event_summary"]["event_count"] == 1
    assert (
        packet["authority_context"]["artifact_authority_records"][0]["record_id"]
        == "artifact-context-1"
    )
    assert saved["source_authority"] == "sqlite"
    assert saved["model_private_memory_required"] == 0
    assert payload["packet_id"] == "packet-codex-resume"


def test_generate_shared_context_packet_can_be_dry_run_without_persisting(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        _seed_context(conn)
        packet = generate_shared_context_packet(
            conn,
            packet_id="packet-dry-run",
            adapter_id="chatgpt",
            packet_type="chatgpt_resume",
            project_id="dream-studio",
            persist=False,
        )
        count = conn.execute(
            "SELECT COUNT(*) FROM shared_context_packets WHERE packet_id = ?",
            ("packet-dry-run",),
        ).fetchone()[0]

    assert packet["adapter_id"] == "chatgpt"
    assert packet["model_private_memory_required"] is False
    assert count == 0


def test_shared_context_packet_policy_keeps_live_writes_approval_gated() -> None:
    policy = shared_context_packet_policy()

    assert policy["source_authority"] == "sqlite"
    assert policy["model_private_memory_required"] is False
    assert policy["adapter_config_write_required"] is False
    assert policy["live_db_write_requires_explicit_approval"] is True


def test_context_packet_generation_uses_temp_db_not_live_db(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    live_db = Path.home() / ".dream-studio" / "state" / "studio.db"
    with _connect(db_path) as conn:
        _seed_context(conn)
        generate_shared_context_packet(
            conn,
            packet_id="packet-temp-db",
            adapter_id="codex",
            packet_type="codex_resume",
            project_id="dream-studio",
        )

    assert db_path.is_file()
    assert db_path != live_db


def _seed_context(conn) -> None:
    register_default_adapter_authority_profiles(conn)
    record_model_provider_profile(
        conn,
        model_profile_id="openai-gpt-context-test",
        provider="openai",
        model_id="gpt-context-test",
        capability_tags=["code", "tool_use"],
        context_limit_tokens=200000,
        cost_profile={"authority": "recorded_estimate"},
        failure_modes=["context_overflow"],
        best_use_patterns=["resume from SQLite authority"],
    )
    record_artifact_authority(
        conn,
        record_id="artifact-context-1",
        record_type="work_order",
        project_id="dream-studio",
        milestone_id="shared_context_packet_generation",
        task_id="wo-context-packets",
        process_run_id="process-context-packets",
        authority_status="canonical",
        file_is_export=True,
        payload={"status": "ready"},
        source_refs=["sqlite:artifact_authority_records"],
        evidence_refs=["tests/unit/test_shared_intelligence_context_packets.py"],
    )
    record_learning_event(
        conn,
        learning_event_id="learning-context-1",
        project_id="dream-studio",
        milestone_id="shared_context_packet_generation",
        task_id="wo-context-packets",
        process_run_id="process-context-packets",
        component_type="adapter",
        component_id="codex",
        event_class="adapter_gap",
        severity="medium",
        summary="Context packet should not rely on private model memory.",
        recurrence_key="private-memory-boundary",
        promotion_status="candidate",
    )
    conn.commit()
