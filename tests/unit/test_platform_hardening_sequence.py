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
    platform_hardening_summary,
    record_policy_decision,
    # ingest_connector_payload removed — connector_ingestion_records dropped migration 131.
    # record_skill_evaluation removed — skill_evaluation_records dropped migration 131.
    # sanitize_export_packet removed — privacy_redaction_export_records dropped in migration 128.
    validate_platform_hardening_summary,
)
from projections.api.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_platform_hardening_summary_covers_all_milestones(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        summary = platform_hardening_summary(conn)

    assert validate_platform_hardening_summary(conn) == []
    assert summary["validation"]["status"] == "pass"
    # privacy_redaction_secret_boundary, local_watch_scheduled_validation,
    # team_pilot_rollup_reporting, installer_distribution_hardening,
    # demo_case_study_system removed — backing tables dropped in migration 128.
    assert set(summary["milestones"]) == {
        "skill_evaluation_harness",
        "policy_permission_engine",
        "engineering_connector_ingestion",
    }
    assert summary["milestones"]["skill_evaluation_harness"]["record_count"] == 0
    assert len(summary["milestones"]["skill_evaluation_harness"]["evaluated_workflows"]) == len(
        EVALUATED_WORKFLOWS
    )


# test_skill_evaluation_and_policy_records_persist removed —
# record_skill_evaluation deleted; skill_evaluation_records dropped migration 131.

# test_connector_ingestion_normalizes_into_current_authority removed —
# ingest_connector_payload deleted; connector_ingestion_records dropped migration 131.


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


def test_policy_decision_persists(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
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

    assert summary["milestones"]["policy_permission_engine"]["decision_count"] == 1
    assert summary["milestones"]["policy_permission_engine"]["decision_state_counts"] == {
        "deferred": 1
    }


# test_privacy_redaction_blocks_private_fields_and_secret_like_keys removed —
# sanitize_export_packet deleted; privacy_redaction_export_records dropped in migration 128.


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
        # /privacy, /watchers, /team-rollup, /installer, /demo removed —
        # backing tables dropped in migration 128.
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
