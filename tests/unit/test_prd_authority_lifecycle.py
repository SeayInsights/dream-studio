from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from core.config.database import DB_PATH_ENV, DatabaseRuntime
from core.event_store.studio_db import _connect
from core.shared_intelligence.adapter_alignment import register_default_adapter_authority_profiles
from core.shared_intelligence.adapter_config_projection import adapter_config_projection_report
from core.shared_intelligence.context_packets import generate_shared_context_packet
from core.shared_intelligence.contract_atlas import build_contract_atlas, validate_contract_atlas
from core.shared_intelligence.prd_authority import (
    build_project_intake_plan,
    classify_change_request,
    context_packet_prd_authority,
    create_project_change_order,
    formalize_in_flight_project,
    generate_milestones_from_prd,
    generate_prd_draft,
    generate_work_orders_from_milestones,
    project_prd_authority_summary,
    record_milestone_sequence,
    record_prd_route_reconciliation,
    record_prd_version,
    record_project_intake,
    record_work_order_sequence,
    validate_prd_authority_summary,
)
from projections.api.main import app


def test_new_project_intake_creates_adaptive_prd_authority(tmp_path: Path) -> None:
    description = (
        "Build a local dashboard app for operators. It stores SQLite data, uses AI "
        "adapters, and should continue through safe milestones."
    )
    with _connect(_db(tmp_path)) as conn:
        plan = record_project_intake(
            conn,
            intake_id="intake-demo",
            project_id="demo-project",
            project_name="Demo Project",
            project_description=description,
            mode="quick_start",
        )
        prd = generate_prd_draft(
            project_id="demo-project",
            project_name="Demo Project",
            project_description=description,
            intake_plan=plan,
        )
        version = record_prd_version(conn, project_id="demo-project", prd_payload=prd)
        milestones = generate_milestones_from_prd(prd)
        work_orders = generate_work_orders_from_milestones(
            project_id="demo-project",
            milestones=milestones,
        )
        record_milestone_sequence(
            conn,
            project_id="demo-project",
            prd_id=version["prd_id"],
            prd_version_id=version["prd_version_id"],
            milestones=milestones,
        )
        record_work_order_sequence(
            conn,
            project_id="demo-project",
            prd_id=version["prd_id"],
            prd_version_id=version["prd_version_id"],
            work_orders=work_orders,
        )
        summary = project_prd_authority_summary(conn, project_id="demo-project")

    assert plan["question_mode"] == "quick_start"
    assert all(question["criticality"] == "critical" for question in plan["questions"])
    assert plan["policy"]["do_not_jump_straight_to_code"] is True
    assert prd["lifecycle_status"] == "draft_generated"
    assert prd["prd"]["known_unknowns"]
    assert version["prd_version_id"].endswith("-v1")
    assert len(summary["current_milestones"]) == 9
    assert len(summary["active_work_orders"]) == 9
    assert summary["policy"]["change_orders_required_for_material_changes"] is True
    assert validate_prd_authority_summary(summary) == []


def test_standard_intake_does_not_overask_when_description_answers_groups() -> None:
    sparse = build_project_intake_plan("Build something useful.", mode="standard_discovery")
    detailed = build_project_intake_plan(
        (
            "Build a dashboard for operators with target users, core workflows, MVP, "
            "SQLite storage, API integrations, deployment expectations, success "
            "criteria, constraints, and autonomy level."
        ),
        mode="standard_discovery",
    )

    assert detailed["question_count"] < sparse["question_count"]
    assert detailed["assumptions"]


def test_in_flight_project_without_prd_formalizes_from_evidence_without_files(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    readme = repo / "README.md"
    readme.write_text("# Demo Project\n\nCurrent behavior evidence.\n", encoding="utf-8")
    with _connect(_db(tmp_path)) as conn:
        _seed_project(conn, project_id="demo-project", project_path=str(repo))
        result = formalize_in_flight_project(
            conn,
            project_id="demo-project",
            repo_root=repo,
            persist=True,
        )
        summary = project_prd_authority_summary(conn, project_id="demo-project")

    assert result["formalization_status"] == "in_flight_formalization"
    assert result["repo_mutation_authorized"] is False
    assert result["files_written"] == []
    assert result["persisted_version"]["confidence"] == "medium_confidence_needs_review"
    assert summary["prd_count"] >= 1
    assert summary["current_prds"][0]["operator_review_required"] is True
    assert str(readme) in summary["current_prds"][0]["source_refs"]


def test_existing_draft_prd_is_classified_needs_update(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        _seed_project(conn, project_id="draft-project")
        conn.execute("""
            INSERT INTO prd_documents(prd_id, project_id, title, status, file_path, created_at)
            VALUES ('legacy-prd', 'draft-project', 'Legacy Draft', 'draft', 'legacy.md', datetime('now'))
            """)
        result = formalize_in_flight_project(
            conn,
            project_id="draft-project",
            persist=False,
        )

    assert result["formalization_status"] == "needs_update"
    assert result["confidence"] == "medium_confidence_needs_review"
    assert result["operator_review_required"] is True


def test_material_change_request_creates_change_order_and_preserves_prd_lineage(
    tmp_path: Path,
) -> None:
    with _connect(_db(tmp_path)) as conn:
        register_default_adapter_authority_profiles(conn)
        _seed_prd_authority(conn, project_id="demo-project")
        change = create_project_change_order(
            conn,
            change_order_id="co-security-addition",
            project_id="demo-project",
            user_request="Add authentication and PII storage to the MVP.",
        )
        summary = project_prd_authority_summary(conn, project_id="demo-project")

    assert classify_change_request("Add authentication")["change_type"] == (
        "security_or_privacy_change"
    )
    assert change["approval_requirement"] == "operator_approval_required"
    assert change["risk_classification"] == "high"
    assert change["original_prd_refs"]
    assert summary["pending_change_orders"][0]["change_order_id"] == "co-security-addition"
    assert summary["current_prds"][0]["version_number"] == 1


def test_route_reconciliation_records_planned_vs_actual_closeout(
    tmp_path: Path,
) -> None:
    with _connect(_db(tmp_path)) as conn:
        version = _seed_prd_authority(conn, project_id="demo-project")
        result = record_prd_route_reconciliation(
            conn,
            reconciliation_id="recon-demo",
            project_id="demo-project",
            prd_id=version["prd_id"],
            prd_version_id=version["prd_version_id"],
            planned_route={"milestones": ["intake", "implementation"]},
            actual_route={"milestones": ["intake", "implementation", "validation"]},
            completed_milestones=["intake", "implementation"],
            completed_work_orders=["wo-demo"],
            accepted_deviations=[{"reason": "Validation split out explicitly."}],
            final_project_status="in_progress",
            current_next_action="Run validation milestone.",
        )
        summary = project_prd_authority_summary(conn, project_id="demo-project")

    assert result["planned_vs_actual"]["accepted_deviation_count"] == 1
    assert summary["route_reconciliation_status"]["status"] == "current"
    assert summary["route_reconciliations"][0]["current_next_action"] == "Run validation milestone."


def test_context_packets_include_prd_milestone_change_order_authority(
    tmp_path: Path,
) -> None:
    with _connect(_db(tmp_path)) as conn:
        register_default_adapter_authority_profiles(conn)
        _seed_prd_authority(conn, project_id="demo-project")
        create_project_change_order(
            conn,
            change_order_id="co-dashboard",
            project_id="demo-project",
            user_request="Change the dashboard UI labels.",
        )
        scoped = context_packet_prd_authority(conn, project_id="demo-project")
        packet = generate_shared_context_packet(
            conn,
            packet_id="dry-run-demo",
            adapter_id="codex",
            packet_type="resume",
            project_id="demo-project",
            persist=False,
        )

    assert scoped["status"] == "available"
    assert scoped["current_prd_version"]["prd_version_id"]
    assert scoped["current_milestone"]["milestone_id"]
    assert scoped["active_work_order"]["work_order_id"]
    assert scoped["relevant_change_orders"][0]["change_order_id"] == "co-dashboard"
    assert "prd_project_authority" in packet
    assert packet["prd_project_authority"]["forbidden_context"]


def test_dashboard_project_details_and_shared_routes_expose_prd_authority(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = _db(tmp_path)
    with _connect(db_path) as conn:
        _seed_project(conn, project_id="demo-project")
        _seed_prd_authority(conn, project_id="demo-project")
    DatabaseRuntime.reset_instance()
    monkeypatch.setenv(DB_PATH_ENV, str(db_path))

    client = TestClient(app)
    details = client.get("/api/v1/projects/demo-project/details")
    shared = client.get(
        "/api/shared-intelligence/prd-authority",
        params={"project_id": "demo-project"},
    )
    status = client.get("/api/shared-intelligence/status", params={"project_id": "demo-project"})

    assert details.status_code == 200, details.text
    assert shared.status_code == 200, shared.text
    assert details.json()["prd_lifecycle_authority"]["prd_count"] == 1
    assert details.json()["prd_version"]["prd_version_id"]
    assert details.json()["current_milestones"]
    assert details.json()["active_work_orders"]
    assert shared.json()["dashboard_consumable"] is True
    assert any(
        surface["surface_id"] == "prd-authority-lifecycle" for surface in status.json()["surfaces"]
    )


def test_contract_atlas_reflects_prd_authority_model(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    with _connect(_db(tmp_path)) as conn:
        register_default_adapter_authority_profiles(conn)
        projection_report = adapter_config_projection_report(conn, project_id="demo-project")
        _write_projection_files(repo_root, projection_report)
        _seed_prd_authority(conn, project_id="demo-project")
        atlas = build_contract_atlas(conn, repo_root=repo_root, project_id="demo-project")

    assert validate_contract_atlas(atlas) == []
    assert atlas["prd_authority_lifecycle"]["validation_status"] == "pass"
    assert atlas["prd_authority_lifecycle"]["prd_count"] == 1
    assert any(
        item["area"] == "prd_authority_lifecycle" and item["sqlite_is_prd_authority"] is True
        for item in atlas["maturity_scorecard"]
    )
    assert any(
        edge["source"] == "module:prd_authority_lifecycle"
        and edge["target"] == "table:prd_version_records"
        for edge in atlas["confirmed_dependency_graph"]["edges"]
    )


def _seed_project(
    conn,
    *,
    project_id: str,
    project_path: str | None = None,
) -> None:
    # reg_projects deleted in migration 084; use business_projects
    conn.execute(
        """
        INSERT OR IGNORE INTO business_projects (
            project_id, name, description, status,
            project_path, detected_stack, stack_json,
            created_at, updated_at
        ) VALUES (?, ?, ?, 'active', ?, ?, ?, datetime('now'), datetime('now'))
        """,
        (
            project_id,
            "Demo Project",
            "application",
            project_path or str(Path.cwd()),
            "python",
            '{"dependencies": ["fastapi"], "config_files": ["pyproject.toml"]}',
        ),
    )


def _seed_prd_authority(conn, *, project_id: str) -> dict[str, str]:
    plan = build_project_intake_plan(
        "Build an operator dashboard with SQLite storage and validation gates.",
        project_id=project_id,
    )
    prd = generate_prd_draft(
        project_id=project_id,
        project_name="Demo Project",
        project_description="Build an operator dashboard with SQLite storage and validation gates.",
        intake_plan=plan,
    )
    version = record_prd_version(conn, project_id=project_id, prd_payload=prd)
    milestones = generate_milestones_from_prd(prd)
    work_orders = generate_work_orders_from_milestones(
        project_id=project_id,
        milestones=milestones,
    )
    record_milestone_sequence(
        conn,
        project_id=project_id,
        prd_id=version["prd_id"],
        prd_version_id=version["prd_version_id"],
        milestones=milestones,
    )
    record_work_order_sequence(
        conn,
        project_id=project_id,
        prd_id=version["prd_id"],
        prd_version_id=version["prd_version_id"],
        work_orders=work_orders,
    )
    return version


def _db(tmp_path: Path) -> Path:
    return tmp_path / "prd-authority" / "studio.db"


def _write_projection_files(repo_root: Path, projection_report: dict) -> None:
    for projection in projection_report["projections"]:
        path = repo_root / projection["projection_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(projection["content"], encoding="utf-8")
    (repo_root / "AGENTS.md").write_text(
        "Dream Studio SQLite authority projection for Codex.\n"
        "adapter-projections/codex/AGENTS.md\n",
        encoding="utf-8",
    )
    (repo_root / "CLAUDE.md").write_text(
        "Dream Studio SQLite authority projection for Claude.\n"
        "adapter-projections/claude/CLAUDE.md\n",
        encoding="utf-8",
    )
