from __future__ import annotations

import json
from pathlib import Path

from core.config.sqlite_bootstrap import latest_migration_version
from core.event_store.studio_db import _connect
from core.shared_intelligence.authority import (
    REQUIRED_SHARED_INTELLIGENCE_TABLES,
    build_adapter_context_packet,
    record_adapter_authority_profile,
    record_adapter_result,
    record_artifact_authority,
    record_capability_route,
    record_hardening_candidate,
    record_learning_event,
    record_model_provider_profile,
    record_shared_context_packet,
    require_shared_intelligence_tables,
)


def _db(tmp_path: Path) -> Path:
    return tmp_path / "shared-intelligence" / "studio.db"


def test_migration_038_creates_shared_intelligence_tables(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    with _connect(db_path) as conn:
        schema_version = conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0]
        assert schema_version == latest_migration_version()
        assert schema_version >= 38
        require_shared_intelligence_tables(conn)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert tables >= REQUIRED_SHARED_INTELLIGENCE_TABLES


def test_records_make_sqlite_primary_authority_and_files_exports(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    with _connect(db_path) as conn:
        _seed_shared_records(conn)
        conn.commit()
        artifact = conn.execute(
            "SELECT * FROM artifact_authority_records WHERE record_id = ?",
            ("artifact-work-order-1",),
        ).fetchone()
        adapter = conn.execute(
            "SELECT * FROM adapter_authority_profiles WHERE adapter_id = ?",
            ("codex",),
        ).fetchone()
        packet = conn.execute(
            "SELECT * FROM shared_context_packets WHERE packet_id = ?",
            ("packet-codex-1",),
        ).fetchone()

    assert artifact["authority_status"] == "canonical"
    assert artifact["file_is_export"] == 1
    assert json.loads(artifact["payload_json"])["final_verdict"] == "passed"
    assert adapter["authority_role"] == "projection"
    assert adapter["owns_source_of_truth"] == 0
    assert packet["source_authority"] == "sqlite"
    assert packet["model_private_memory_required"] == 0


def test_adapter_context_packet_is_generated_from_sqlite_records(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    with _connect(db_path) as conn:
        _seed_shared_records(conn)
        packet = build_adapter_context_packet(
            conn,
            adapter_id="codex",
            project_id="dream-studio",
        )
        record_shared_context_packet(
            conn,
            packet_id="packet-generated-from-sqlite",
            adapter_id="codex",
            project_id="dream-studio",
            milestone_id="sqlite_first_artifact_authority_maturation",
            packet_type="codex_resume",
            payload=packet,
            source_refs=["sqlite:artifact_authority_records"],
            evidence_refs=["tests/unit/test_shared_intelligence_sqlite_authority.py"],
        )
        conn.commit()
        saved = conn.execute(
            "SELECT payload_json FROM shared_context_packets WHERE packet_id = ?",
            ("packet-generated-from-sqlite",),
        ).fetchone()

    payload = json.loads(saved["payload_json"])
    assert payload["source_authority"] == "sqlite"
    assert payload["model_private_memory_required"] is False
    assert payload["adapter"]["adapter_id"] == "codex"
    assert payload["artifact_authority_records"][0]["record_id"] == "artifact-work-order-1"
    assert payload["learning_events"][0]["learning_event_id"] == "learning-event-1"


def test_adapter_results_and_capability_routes_are_normalized(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    with _connect(db_path) as conn:
        _seed_shared_records(conn)
        result = conn.execute(
            "SELECT * FROM adapter_result_records WHERE result_id = ?",
            ("adapter-result-1",),
        ).fetchone()
        route = conn.execute(
            "SELECT * FROM capability_route_records WHERE capability_route_id = ?",
            ("capability-route-1",),
        ).fetchone()

    assert result["adapter_id"] == "codex"
    assert result["normalized_status"] == "validated"
    assert json.loads(result["evidence_refs_json"]) == ["evidence://validation"]
    assert route["selected_adapter_id"] == "codex"
    assert route["selected_model_profile_id"] == "openai-gpt-5"
    assert route["validation_required"] == 1
    assert route["operator_approval_required"] == 0


def test_shared_intelligence_tests_use_temp_db_not_live_db(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    live_db = Path.home() / ".dream-studio" / "state" / "studio.db"
    with _connect(db_path) as conn:
        require_shared_intelligence_tables(conn)

    assert db_path.is_file()
    assert db_path != live_db


def _seed_shared_records(conn) -> None:
    scope = {
        "project_id": "dream-studio",
        "milestone_id": "sqlite_first_artifact_authority_maturation",
        "task_id": "shared-intelligence-foundation",
        "process_run_id": "process-shared-intelligence-test",
    }
    record_adapter_authority_profile(
        conn,
        adapter_id="codex",
        adapter_type="codex",
        adapter_name="Codex",
        supported_context_packets=["codex_resume"],
        supported_result_types=["code_change", "validation", "decision"],
        stale_detection_policy={"source": "sqlite_authority"},
    )
    record_model_provider_profile(
        conn,
        model_profile_id="openai-gpt-5",
        provider="openai",
        model_id="gpt-5",
        capability_tags=["code", "reasoning", "tool_use"],
        context_limit_tokens=200000,
        cost_profile={"authority": "estimate"},
    )
    record_artifact_authority(
        conn,
        record_id="artifact-work-order-1",
        record_type="work_order",
        **scope,
        source_path="meta/work-orders/example/planning/work_order.md",
        authority_status="canonical",
        file_is_export=True,
        human_export_path="meta/work-orders/example/planning/work_order.md",
        payload={"final_verdict": "passed"},
        source_refs=["sqlite:artifact_authority_records"],
        evidence_refs=["evidence://work-order"],
    )
    record_learning_event(
        conn,
        learning_event_id="learning-event-1",
        **scope,
        component_type="skill",
        component_id="ds-core",
        event_class="operator_correction",
        severity="medium",
        summary="Operator correction should become shared authority.",
        observed_pattern="Model-specific memory is insufficient.",
        root_cause="Learning was not in SQLite authority.",
        remediation_hint="Promote to shared learning event.",
        recurrence_key="operator-correction-shared-authority",
        promotion_status="candidate",
    )
    record_hardening_candidate(
        conn,
        candidate_id="hardening-candidate-1",
        learning_event_id="learning-event-1",
        component_type="skill",
        component_id="ds-core",
        current_version="unversioned",
        proposed_version="sqlite-learning-aware",
        hardening_type="skill_instruction_update",
        validation_plan=["focused test", "recurrence check"],
        rollback_plan="Keep prior skill version available.",
    )
    record_shared_context_packet(
        conn,
        packet_id="packet-codex-1",
        adapter_id="codex",
        **scope,
        packet_type="codex_resume",
        payload={"source_authority": "sqlite", "record_refs": ["artifact-work-order-1"]},
    )
    record_adapter_result(
        conn,
        result_id="adapter-result-1",
        adapter_id="codex",
        packet_id="packet-codex-1",
        **scope,
        result_type="code_change",
        normalized_status="validated",
        evidence_refs=["evidence://validation"],
        validation_refs=["validation://pytest"],
        artifact_refs=["artifact-work-order-1"],
        payload={"files_changed": []},
    )
    record_capability_route(
        conn,
        capability_route_id="capability-route-1",
        **scope,
        task_class="sqlite_authority_foundation",
        selected_adapter_id="codex",
        selected_model_profile_id="openai-gpt-5",
        route_basis={"capability": "code", "risk": "bounded"},
        risk_level="medium",
        cost_sensitivity="medium",
        validation_required=True,
        operator_approval_required=False,
    )
