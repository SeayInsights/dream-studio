from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from core.config.database import DB_PATH_ENV, DatabaseRuntime
from core.event_store.studio_db import _connect
from core.shared_intelligence.adapter_alignment import register_default_adapter_authority_profiles
from core.shared_intelligence.authority import (
    record_hardening_candidate,
    record_learning_event,
    record_model_provider_profile,
)
from core.shared_intelligence.result_normalization import record_normalized_adapter_result
from projections.api.main import app


def _client_with_shared_db(tmp_path: Path, monkeypatch) -> tuple[TestClient, Path]:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    db_path = tmp_path / "shared-intelligence-routes" / "studio.db"
    with _connect(db_path) as conn:
        _seed_shared_intelligence(conn)
        conn.commit()
    DatabaseRuntime.reset_instance()
    monkeypatch.setenv(DB_PATH_ENV, str(db_path))
    return TestClient(app), db_path


def test_actual_app_mounts_shared_intelligence_learning_dashboard(
    tmp_path: Path, monkeypatch
) -> None:
    client, _db_path = _client_with_shared_db(tmp_path, monkeypatch)

    response = client.get(
        "/api/shared-intelligence/learning-dashboard", params={"project_id": "dream-studio"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["model_name"] == "shared_intelligence_learning_hardening_dashboard_view"
    assert payload["derived_view"] is True
    assert payload["primary_authority"] is False
    assert payload["routing_authority"] is False
    assert payload["dashboard_consumable"] is True
    assert payload["execution_authorized"] is False
    assert payload["sections"]["lessons_learned"]["count"] >= 1
    assert payload["sections"]["hardening_candidates"]["items"][0]["execution_authorized"] is False


def test_actual_app_exposes_adapter_projection_and_staleness_surfaces(
    tmp_path: Path, monkeypatch
) -> None:
    client, _db_path = _client_with_shared_db(tmp_path, monkeypatch)

    projections = client.get(
        "/api/shared-intelligence/adapters/projections", params={"project_id": "dream-studio"}
    )
    staleness = client.get(
        "/api/shared-intelligence/adapters/staleness", params={"project_id": "dream-studio"}
    )

    assert projections.status_code == 200
    assert staleness.status_code == 200
    assert projections.json()["config_write_authorized"] is False
    assert projections.json()["projections"][0]["adapter_owns_source_of_truth"] is False
    assert staleness.json()["repair_execution_authorized"] is False
    assert staleness.json()["aligned_count"] == staleness.json()["adapter_count"]
    assert staleness.json()["active_repo_surface_count"] == 2
    assert staleness.json()["live_execution_proven"] is False
    assert staleness.json()["repair_work_order_candidates"] == []
    checks = {check["adapter_id"]: check for check in staleness.json()["checks"]}
    for adapter_id in ("claude", "codex"):
        assert "generated_projection" in checks[adapter_id]["state_classifications"]
        assert "active_repo_surface" in checks[adapter_id]["state_classifications"]
        assert "live_execution_unproven" in checks[adapter_id]["state_classifications"]
        assert checks[adapter_id]["active_repo_surface"]["consumes_dream_studio_authority"] is True
        assert checks[adapter_id]["active_repo_surface"]["active_matches_generated_sha256"] is False
    assert staleness.json()["derived_view"] is True


def test_actual_app_previews_context_packets_without_persisting(
    tmp_path: Path, monkeypatch
) -> None:
    client, db_path = _client_with_shared_db(tmp_path, monkeypatch)
    before = _count(db_path, "shared_context_packets")

    response = client.get(
        "/api/shared-intelligence/context-packets/codex",
        params={"project_id": "dream-studio", "packet_type": "resume", "limit": 5},
    )

    after = _count(db_path, "shared_context_packets")
    payload = response.json()
    assert response.status_code == 200
    assert before == after
    assert payload["packet_schema"] == "dream_studio.shared_context.v2"
    assert payload["model_private_memory_required"] is False
    assert payload["authority_boundary"]["adapters_are_projections"] is True


def test_actual_app_exposes_capability_and_model_provider_surfaces(
    tmp_path: Path, monkeypatch
) -> None:
    client, db_path = _client_with_shared_db(tmp_path, monkeypatch)
    before_routes = _count(db_path, "capability_route_records")

    routes = client.get(
        "/api/shared-intelligence/capability-routes", params={"project_id": "dream-studio"}
    )
    recommendation = client.get(
        "/api/shared-intelligence/capability-routes/recommendation",
        params={
            "project_id": "dream-studio",
            "task_class": "code",
            "required_capabilities": "code,tool_use",
            "risk_level": "high",
        },
    )
    providers = client.get("/api/shared-intelligence/model-providers")
    matrix = client.get(
        "/api/shared-intelligence/model-providers/capability-matrix",
        params={"required_capabilities": "code", "min_context_tokens": 1000},
    )
    after_routes = _count(db_path, "capability_route_records")

    assert routes.status_code == 200
    assert recommendation.status_code == 200
    assert providers.status_code == 200
    assert matrix.status_code == 200
    assert before_routes == after_routes
    assert recommendation.json()["execution_authorized"] is False
    assert recommendation.json()["operator_approval_required"] is True
    assert providers.json()["provider_api_calls_performed"] is False
    assert matrix.json()["match_count"] == 1
    assert matrix.json()["matches"][0]["model_profile_id"] == "openai-gpt-route"


def test_actual_app_exposes_contract_atlas_without_authorizing_execution(
    tmp_path: Path, monkeypatch
) -> None:
    client, _db_path = _client_with_shared_db(tmp_path, monkeypatch)

    private = client.get(
        "/api/shared-intelligence/contract-atlas",
        params={"project_id": "dream-studio"},
    )
    public = client.get(
        "/api/shared-intelligence/contract-atlas",
        params={"project_id": "dream-studio", "export_scope": "public"},
    )

    assert private.status_code == 200
    assert public.status_code == 200
    private_payload = private.json()
    public_payload = public.json()
    assert private_payload["model_name"] == "dream_studio_contract_atlas"
    assert private_payload["private_by_default"] is True
    assert private_payload["derived_view"] is True
    assert private_payload["primary_authority"] is False
    assert private_payload["execution_authorized"] is False
    assert private_payload["db_write_authorized"] is False
    assert (
        private_payload["active_adapter_execution_validation"]["live_claude_execution_proven"]
        is False
    )
    assert private_payload["confirmed_dependency_graph"]["inferred_edges_included"] is False
    assert private_payload["boundary_violation_report"]["cleanup_execution_authorized"] is False
    assert public_payload["export_scope"] == "public"
    assert public_payload["sanitized_public_export"] is True
    assert public_payload["repo_root"] == "<sanitized-local-path>"
    assert private_payload["current_maturity_ledger"]["area_count"] >= 20


def test_actual_app_exposes_contract_atlas_maturity_and_docs_drift_views(
    tmp_path: Path, monkeypatch
) -> None:
    client, _db_path = _client_with_shared_db(tmp_path, monkeypatch)

    maturity = client.get(
        "/api/shared-intelligence/contract-atlas/maturity-ledger",
        params={"project_id": "dream-studio"},
    )
    drift = client.get(
        "/api/shared-intelligence/contract-atlas/docs-drift",
        params={
            "changed_files": (
                "core/shared_intelligence/contract_atlas.py,"
                "docs/architecture/contract-atlas.md,"
                "docs/README.md,"
                "docs/operations/lint-format-baseline-policy.md"
            )
        },
    )

    assert maturity.status_code == 200
    assert drift.status_code == 200
    assert maturity.json()["model_name"] == "dream_studio_current_maturity_ledger"
    assert maturity.json()["status_counts"]["runtime_validated"] >= 8
    assert maturity.json()["primary_authority"] is False
    assert drift.json()["status"] == "pass"
    assert set(drift.json()["gate_distinctions"]) >= {
        "docs_update_required",
        "docs_reviewed_no_change_needed",
        "prd_update_required",
        "contract_atlas_update_required",
        "publication_risk_detected",
        "private_artifact_risk_detected",
    }


def test_actual_app_shared_intelligence_status_is_non_authoritative(
    tmp_path: Path, monkeypatch
) -> None:
    client, _db_path = _client_with_shared_db(tmp_path, monkeypatch)

    response = client.get("/api/shared-intelligence/status", params={"project_id": "dream-studio"})

    payload = response.json()
    assert response.status_code == 200
    assert payload["model_name"] == "shared_intelligence_runtime_surface_status"
    assert payload["derived_view"] is True
    assert payload["primary_authority"] is False
    assert payload["execution_authorized"] is False
    assert {surface["surface_id"] for surface in payload["surfaces"]} >= {
        "learning-dashboard",
        "adapter-projections",
        "context-packet-preview",
        "capability-routes",
        "model-providers",
        "contract-atlas",
        "maturity-ledger",
        "contract-docs-drift",
    }


def _seed_shared_intelligence(conn) -> None:
    register_default_adapter_authority_profiles(conn)
    record_learning_event(
        conn,
        learning_event_id="learn-route-runtime-1",
        project_id="dream-studio",
        milestone_id="shared_authority_runtime_surface_maturation",
        task_id="route-surface-test",
        process_run_id="process-shared-route-test",
        component_type="skill",
        component_id="ds-core",
        event_class="operator_correction",
        severity="medium",
        summary="Prompt chaining recurrence recorded.",
        recurrence_key="prompt-chaining-regression",
        promotion_status="dashboard_attention",
        source_refs=["sqlite:learning_event_records"],
        evidence_refs=["tests/unit/test_actual_shared_intelligence_routes.py"],
    )
    record_hardening_candidate(
        conn,
        candidate_id="hardening-route-runtime-1",
        learning_event_id="learn-route-runtime-1",
        component_type="skill",
        component_id="ds-core",
        hardening_type="skill_instruction_update",
        status="candidate",
        validation_plan=["run actual shared-intelligence route tests"],
        recurrence_check={"recurrence_key": "prompt-chaining-regression"},
        rollback_plan="Revert the route surface if validation fails.",
    )
    record_model_provider_profile(
        conn,
        model_profile_id="openai-gpt-route",
        provider="openai",
        model_id="gpt-route",
        capability_tags=["code", "tool_use"],
        context_limit_tokens=200000,
        failure_modes=["tool_retry"],
        cost_profile={"authority": "recorded_estimate"},
    )
    record_normalized_adapter_result(
        conn,
        result_id="codex-result-route",
        adapter_id="codex",
        project_id="dream-studio",
        raw_result={"result_type": "code_change", "status": "passed"},
    )


def _count(db_path: Path, table: str) -> int:
    with _connect(db_path) as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0)
