from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from core.career_ops import (
    PUBLIC_EXPORT_EXCLUSIONS,
    career_ops_dashboard_summary,
    record_career_profile,
)
from core.config.database import DB_PATH_ENV, DatabaseRuntime
from core.event_store.studio_db import _connect
from core.shared_intelligence.capability_center import (
    capability_center_summary,
    validate_capability_center_summary,
)
from core.shared_intelligence.adapter_alignment import register_default_adapter_authority_profiles
from core.shared_intelligence.contract_atlas import build_contract_atlas, validate_contract_atlas
from core.shared_intelligence.github_repo_intake import (
    classify_github_repo_evaluation,
    github_repo_intake_dashboard_summary,
    record_github_repo_evaluation,
    validate_github_repo_intake_workflow,
)
from core.shared_intelligence.scoped_agents import (
    scoped_agent_registry,
    scoped_context_packet,
    validate_scoped_agent_registry,
)
from projections.api.main import app


def test_career_ops_is_private_opt_in_and_scores_are_honest(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        disabled = career_ops_dashboard_summary(conn)

        assert disabled["enabled"] is False
        assert disabled["private_by_default"] is True
        assert "career_profiles" in disabled["source_tables"]
        assert "career_applications" in PUBLIC_EXPORT_EXCLUSIONS
        assert disabled["sections"]["profile_completeness"]["status"] == "unavailable"

        record_career_profile(
            conn,
            profile_id="profile-1",
            owner_label="Operator",
            enabled=True,
            headline="Private profile",
        )
        enabled = career_ops_dashboard_summary(conn)

    assert enabled["enabled"] is True
    assert enabled["editable_when_enabled"] is True
    assert enabled["career_data_in_public_exports"] is False
    scorecards = enabled["sections"]["scorecards"]["items"]
    assert scorecards
    assert all(item["status"] == "unavailable" for item in scorecards)


def test_capability_center_and_scoped_agents_are_authority_backed(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        registry = scoped_agent_registry(conn)
        summary = capability_center_summary(conn, project_id="dream-studio", repo_root=_repo_root())
        packet = scoped_context_packet(
            conn,
            agent_id="implementation_worker",
            task_summary="Implement bounded source change",
            project_id="dream-studio",
            requested_data_classes=["career_private"],
            career_scope_approved=True,
        )

    assert validate_scoped_agent_registry(registry) == []
    assert validate_capability_center_summary(summary) == []
    assert registry["agent_is_authority"] is False
    assert registry["dream_studio_remains_canonical"] is True
    assert summary["sections"]["agents"]["count"] >= 1
    assert summary["sections"]["workflows"]["count"] == 11
    assert summary["sections"]["controls"]["count"] > 47
    assert packet["execution_authorized"] is False
    assert "full_conversation_history" in packet["excluded_context"]
    assert "career_private_data_without_scope" in packet["excluded_context"]


def test_scoped_agent_can_include_career_data_only_when_enabled_and_scoped(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        record_career_profile(conn, profile_id="career-enabled", enabled=True)
        packet = scoped_context_packet(
            conn,
            agent_id="career_application_assistant",
            task_summary="Map selected application fields",
            requested_data_classes=["career_private"],
            career_scope_approved=True,
        )

    assert packet["included_context"]["career_private_scope"] == "included"
    assert "career_private_data_without_scope" not in packet["excluded_context"]
    assert packet["agent_is_authority"] is False


def test_github_repo_intake_routes_unclear_license_and_security_review(tmp_path: Path) -> None:
    legal = classify_github_repo_evaluation(
        {
            "repo_url": "https://github.com/example/unclear",
            "commit_sha_reviewed": "abc123",
            "license": "",
        }
    )
    security = classify_github_repo_evaluation(
        {
            "repo_url": "https://github.com/example/dep",
            "commit_sha_reviewed": "abc123",
            "license": "MIT",
            "dependency_requested": True,
        }
    )

    assert legal["integration_decision"] == "legal_review_required"
    assert legal["copy_code_allowed"] is False
    assert security["integration_decision"] == "security_review_required"
    assert security["dependency_add_allowed"] is False

    with _connect(_db(tmp_path)) as conn:
        result = record_github_repo_evaluation(
            conn,
            evaluation_id="eval-1",
            repo_url="https://github.com/example/repo",
            owner_name="example",
            repo_name="repo",
            commit_sha_reviewed="abc123",
            license="MIT",
            security_files=["SECURITY.md"],
            candidate_components=["workflow idea"],
            evidence_refs=["repo://example/repo@abc123"],
        )
        summary = github_repo_intake_dashboard_summary(conn)

    assert result["integration_decision"] == "integration_work_order_ready"
    assert validate_github_repo_intake_workflow(summary) == []
    assert summary["evaluation_count"] == 1
    assert summary["evaluations"][0]["evidence_refs"] == ["repo://example/repo@abc123"]


def test_contract_atlas_and_public_export_include_private_boundaries(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    with _connect(_db(tmp_path)) as conn:
        register_default_adapter_authority_profiles(conn)
        atlas = build_contract_atlas(conn, repo_root=repo_root, project_id="dream-studio")
        public = build_contract_atlas(
            conn,
            repo_root=repo_root,
            project_id="dream-studio",
            export_scope="public",
        )

    assert validate_contract_atlas(atlas) == []
    assert atlas["career_ops_module"]["private_by_default"] is True
    assert atlas["career_ops_module"]["public_export_excluded"] is True
    assert atlas["capability_center"]["validation_status"] == "pass"
    assert atlas["scoped_agent_execution"]["agent_is_authority"] is False
    assert atlas["github_repo_intake"]["copy_code_allowed_without_approval"] is False
    assert public["career_ops_module"]["public_export_excluded"] is True
    assert "profile_count" not in public["career_ops_module"]


def test_shared_intelligence_routes_expose_new_private_surfaces(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = _db(tmp_path)
    with _connect(db_path):
        pass
    DatabaseRuntime.reset_instance()
    monkeypatch.setenv(DB_PATH_ENV, str(db_path))

    client = TestClient(app)
    for path in (
        "/api/shared-intelligence/career-ops",
        "/api/shared-intelligence/capability-center",
        "/api/shared-intelligence/agents/registry",
        "/api/shared-intelligence/agents/context-packet",
        "/api/shared-intelligence/github-repo-intake",
    ):
        response = client.get(path)
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["derived_view"] is True
        assert payload["execution_authorized"] is False


def _db(tmp_path: Path) -> Path:
    return tmp_path / "career-capability-github" / "studio.db"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]
