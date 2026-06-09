from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from core.config.database import DB_PATH_ENV, DatabaseRuntime
from core.event_store.studio_db import _connect
from core.shared_intelligence.adapter_alignment import register_default_adapter_authority_profiles
from core.shared_intelligence.contract_atlas import build_contract_atlas, validate_contract_atlas
from core.shared_intelligence.platform_hardening import (
    EVALUATED_WORKFLOWS,
    evaluate_policy_decision,
    ingest_connector_payload,
    platform_hardening_summary,
    record_policy_decision,
    record_skill_evaluation,
    sanitize_export_packet,
    validate_platform_hardening_summary,
)
from projections.api.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_platform_hardening_summary_covers_all_milestones(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        summary = platform_hardening_summary(conn)

    assert validate_platform_hardening_summary(conn) == []
    assert summary["validation"]["status"] == "pass"
    assert set(summary["milestones"]) == {
        "skill_evaluation_harness",
        "policy_permission_engine",
        "engineering_connector_ingestion",
        "privacy_redaction_secret_boundary",
        "local_watch_scheduled_validation",
        "team_pilot_rollup_reporting",
        "installer_distribution_hardening",
        "demo_case_study_system",
    }
    assert summary["milestones"]["skill_evaluation_harness"]["record_count"] == 0
    assert len(summary["milestones"]["skill_evaluation_harness"]["evaluated_workflows"]) == len(
        EVALUATED_WORKFLOWS
    )
    assert summary["milestones"]["local_watch_scheduled_validation"]["opt_in"] is True
    assert (
        summary["milestones"]["local_watch_scheduled_validation"]["background_processes_started"]
        is False
    )


def test_skill_evaluation_and_policy_records_persist(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        record_skill_evaluation(
            conn,
            evaluation_id="eval-docs-quality-1",
            target_type="workflow",
            target_id="documentation_quality_workflow",
            fixture_id="golden-docs-install",
            expected_output_contract={"fields": ["status", "evidence_refs"]},
            rubric_scores={"new_user_installability": "pass"},
            status="pass",
            promotion_decision="promote_candidate",
            rollback_decision="rollback_on_regression",
            evidence_refs=["tests/unit/test_platform_hardening_sequence.py"],
        )
        record_policy_decision(
            conn,
            decision_id="policy-live-write-1",
            actor="codex",
            action="live_sqlite_write",
            target="installed_state",
            scope={"home": "redacted"},
            approved=False,
            evidence_refs=["operator_decision"],
        )
        summary = platform_hardening_summary(conn)

    assert summary["milestones"]["skill_evaluation_harness"]["record_count"] == 1
    assert summary["milestones"]["skill_evaluation_harness"]["status_counts"] == {"pass": 1}
    assert summary["milestones"]["policy_permission_engine"]["decision_count"] == 1
    assert summary["milestones"]["policy_permission_engine"]["decision_state_counts"] == {
        "deferred": 1
    }


def test_policy_engine_denies_or_defers_risky_actions_without_approval() -> None:
    secret = evaluate_policy_decision(
        actor="adapter",
        action="secret_sensitive_access",
        target="env",
    )
    push = evaluate_policy_decision(
        actor="operator",
        action="push_tag_merge_deploy",
        target="origin/main",
        approved=True,
    )
    read_only = evaluate_policy_decision(actor="operator", action="read_only_action")

    assert secret["decision_state"] == "denied"
    assert push["decision_state"] == "denied"
    assert read_only["decision_state"] == "allowed"


def test_connector_ingestion_normalizes_into_current_authority(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        dry_run = ingest_connector_payload(
            conn,
            ingestion_run_id="connector-run-1",
            source_type="manual_import",
            payload={
                "source_refs": ["manual://packet/1"],
                "evidence_refs": ["evidence://validation/1"],
                "projects": [{"project_id": "pilot", "project_name": "Pilot"}],
                "validations": [
                    {
                        "validation_id": "validation-1",
                        "project_id": "pilot",
                        "status": "passed",
                        "validation_type": "junit",
                    }
                ],
            },
            execute=False,
        )
        executed = ingest_connector_payload(
            conn,
            ingestion_run_id="connector-run-2",
            source_type="manual_import",
            payload={
                "source_refs": ["manual://packet/1"],
                "evidence_refs": ["evidence://validation/1"],
                "projects": [{"project_id": "pilot", "project_name": "Pilot"}],
                "validations": [
                    {
                        "validation_id": "validation-1",
                        "project_id": "pilot",
                        "status": "passed",
                        "validation_type": "junit",
                    }
                ],
            },
            execute=True,
        )
        project_count = conn.execute(
            "SELECT COUNT(*) FROM business_projects WHERE project_id = 'pilot'"
        ).fetchone()[0]
        validation_count = conn.execute(
            "SELECT COUNT(*) FROM validation_results WHERE validation_id = 'validation-1'"
        ).fetchone()[0]
        summary = platform_hardening_summary(conn)

    assert dry_run["status"] == "planned"
    assert dry_run["analytics_ingestion"]["dry_run"] is True
    assert executed["status"] == "imported"
    assert executed["parallel_truth_created"] is False
    assert project_count == 1
    assert validation_count == 1
    assert summary["milestones"]["engineering_connector_ingestion"]["run_count"] == 2
    assert (
        summary["milestones"]["engineering_connector_ingestion"]["analytics_only_supported"] is True
    )


def test_privacy_redaction_blocks_private_fields_and_secret_like_keys() -> None:
    sanitized = sanitize_export_packet(
        {
            "summary": "pilot safe",
            "raw_work_orders": ["private"],
            "local_paths": ["C:/Users/Example/private"],
        },
        visibility_mode="public_sanitized",
    )
    blocked = sanitize_export_packet({"summary": "bad", "api_key": "not-read"})

    assert sanitized["status"] == "pass"
    assert "raw_work_orders" not in sanitized["sanitized_packet"]
    assert sanitized["secret_values_inspected"] is False
    assert blocked["status"] == "blocked"
    assert blocked["secret_values_inspected"] is False


def test_contract_atlas_and_api_expose_platform_hardening(tmp_path: Path, monkeypatch) -> None:
    db_path = _db(tmp_path)
    with _connect(db_path) as conn:
        register_default_adapter_authority_profiles(conn)
        atlas = build_contract_atlas(conn, repo_root=REPO_ROOT, project_id="dream-studio")

    assert validate_contract_atlas(atlas) == []
    assert atlas["platform_hardening"]["validation_status"] == "pass"
    assert "platform_hardening_sequence" in {item["area"] for item in atlas["maturity_scorecard"]}
    assert any(
        edge["source"] == "module:platform_hardening_sequence"
        for edge in atlas["confirmed_dependency_graph"]["edges"]
    )

    DatabaseRuntime.reset_instance()
    monkeypatch.setenv(DB_PATH_ENV, str(db_path))
    client = TestClient(app)
    for path in (
        "/api/shared-intelligence/platform-hardening",
        "/api/shared-intelligence/platform-hardening/skill-evaluations",
        "/api/shared-intelligence/platform-hardening/policy-decision",
        "/api/shared-intelligence/platform-hardening/connectors",
        "/api/shared-intelligence/platform-hardening/privacy",
        "/api/shared-intelligence/platform-hardening/watchers",
        "/api/shared-intelligence/platform-hardening/team-rollup",
        "/api/shared-intelligence/platform-hardening/installer",
        "/api/shared-intelligence/platform-hardening/demo",
    ):
        response = client.get(path)
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["derived_view"] is True
        assert payload["execution_authorized"] is False


def test_installed_cli_platform_hardening_commands_work_outside_repo(tmp_path: Path) -> None:
    home = tmp_path / "home"
    db_path = home / "state" / "studio.db"
    with _connect(db_path):
        pass

    commands = [
        ["version"],
        ["doctor"],
        ["repair"],
        ["policy", "--action", "secret_sensitive_access"],
        ["platform-hardening"],
    ]
    for command in commands:
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "interfaces" / "cli" / "ds.py"),
                "--source-root",
                str(REPO_ROOT),
                "--home",
                str(home),
                *command,
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        assert payload["derived_view"] is True


def _db(tmp_path: Path) -> Path:
    return tmp_path / "platform-hardening" / "studio.db"
