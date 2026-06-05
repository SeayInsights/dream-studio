from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

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
        )

    assert validate_scoped_agent_registry(registry) == []
    assert validate_capability_center_summary(summary) == []
    assert registry["agent_is_authority"] is False
    assert registry["dream_studio_remains_canonical"] is True
    assert summary["sections"]["agents"]["count"] >= 1
    assert summary["sections"]["workflows"]["count"] == 10
    assert summary["sections"]["controls"]["count"] > 47
    assert packet["execution_authorized"] is False
    assert "full_conversation_history" in packet["excluded_context"]
    # Career Ops has been removed; career data is always excluded from packets.
    assert "career_private_data_without_scope" in packet["excluded_context"]
    assert packet["included_context"]["career_private_scope"] == "excluded"


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
    assert "career_ops_module" not in atlas
    assert "career_ops_module" not in public
    assert atlas["capability_center"]["validation_status"] == "pass"
    assert atlas["scoped_agent_execution"]["agent_is_authority"] is False
    assert atlas["github_repo_intake"]["copy_code_allowed_without_approval"] is False


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
