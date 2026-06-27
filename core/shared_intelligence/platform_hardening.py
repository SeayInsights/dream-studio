"""Platform-hardening authority and read models.

This module groups the next product-hardening sequence into one deterministic
authority-backed surface. It is intentionally dry-run and local-first by
default: connector ingestion can plan normalized writes, policy decisions can
deny/defer risky actions, and exports are sanitized before they leave private
operator scope.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from typing import Any

PLATFORM_HARDENING_SCHEMA = "dream_studio.platform_hardening.v1"

PLATFORM_HARDENING_TABLES: tuple[str, ...] = (
    "policy_decision_records",
    # skill_evaluation_runs: dropped migration 131
    # connector_ingestion_runs: dropped migration 131
)

EVALUATED_WORKFLOWS: tuple[str, ...] = (
    "intentional_implementation_workflow",
    "code_quality_architecture_workflow",
    "root_cause_debugging_workflow",
    "performance_efficiency_workflow",
    "frontend_design_excellence_workflow",
    "seo_content_growth_workflow",
    "documentation_quality_workflow",
    "data_modeling_authority_workflow",
    "api_integration_design_workflow",
    "product_demo_and_case_study_workflow",
    "security_readiness_workflow",
)


def _policy(
    action: str,
    risk_level: str,
    approval_requirement: str,
    default_decision: str,
) -> dict[str, Any]:
    return {
        "action": action,
        "risk_level": risk_level,
        "approval_requirement": approval_requirement,
        "default_decision": default_decision,
        "evidence_requirement": "evidence_refs_required_for_medium_or_higher_risk",
        "rollback_requirement": "rollback_or_hold_required_before_mutation",
    }


POLICY_ACTIONS: tuple[dict[str, Any], ...] = (
    _policy("read_only_action", "low", "none", "allowed"),
    _policy("repo_mutation", "medium", "current_operator_scope", "deferred"),
    _policy("live_sqlite_write", "high", "explicit_live_update_approval", "deferred"),
    _policy(
        "external_project_inspection", "medium", "explicit_current_target_selection", "deferred"
    ),
    _policy("external_project_mutation", "high", "scoped_mutation_approval", "deferred"),
    _policy(
        "cleanup_delete_archive_dedup_compaction", "critical", "explicit_cleanup_approval", "denied"
    ),
    _policy("push_tag_merge_deploy", "critical", "explicit_release_approval", "denied"),
    _policy("adapter_execution", "medium", "route_or_adapter_policy", "deferred"),
    _policy("browser_automation", "medium", "operator_scope_and_review", "deferred"),
    _policy(
        "career_application_submission", "critical", "per_application_submission_approval", "denied"
    ),
    _policy(
        "secret_sensitive_access", "critical", "do_not_inspect_without_explicit_approval", "denied"
    ),
    _policy("docker_runtime_execution", "high", "docker_runtime_approval", "deferred"),
    _policy("package_dependency_change", "high", "security_license_maintenance_review", "deferred"),
)

CONNECTOR_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "connector_id": "github_prs_issues_checks",
        "source_type": "github",
        "authentication_requirement": "optional_token_or_export",
        "read_write_mode": "read_only",
        "supported_records": ["projects", "validations", "manual_evidence_packets"],
        "normalization_targets": ["reg_projects", "validation_results"],
        # artifact_records: dropped migration 130
    },
    {
        "connector_id": "github_actions_metadata",
        "source_type": "github_actions",
        "authentication_requirement": "optional_token_or_export",
        "read_write_mode": "read_only",
        "supported_records": ["validations", "ci_logs"],
        "normalization_targets": ["validation_results"],
        # artifact_records: dropped migration 130
    },
    {
        "connector_id": "junit_report",
        "source_type": "junit",
        "authentication_requirement": "none",
        "read_write_mode": "local_file_read",
        "supported_records": ["validations"],
        "normalization_targets": ["validation_results"],
    },
    {
        "connector_id": "sarif_security_report",
        "source_type": "sarif",
        "authentication_requirement": "none",
        "read_write_mode": "local_file_read",
        "supported_records": ["findings"],
        "normalization_targets": ["findings"],
    },
    {
        "connector_id": "coverage_report",
        "source_type": "coverage",
        "authentication_requirement": "none",
        "read_write_mode": "local_file_read",
        "supported_records": ["validations"],
        "normalization_targets": ["validation_results"],
    },
    {
        "connector_id": "package_manifest",
        "source_type": "package_manifest",
        "authentication_requirement": "none",
        "read_write_mode": "local_file_read",
        "supported_records": ["dependencies", "stack"],
        "normalization_targets": ["pi_components", "pi_dependencies"],
    },
    {
        "connector_id": "csv_json_manual_import",
        "source_type": "manual_import",
        "authentication_requirement": "none",
        "read_write_mode": "local_file_read",
        "supported_records": [
            "projects",
            "validations",
            "findings",
            "token_usage",
            "ai_usage",
        ],
        "normalization_targets": ["current_sqlite_authority"],
    },
    {
        "connector_id": "token_ai_usage_import",
        "source_type": "ai_usage_export",
        "authentication_requirement": "provider_export_or_manual_config",
        "read_write_mode": "local_file_read",
        "supported_records": ["token_usage", "ai_usage"],
        "normalization_targets": ["token_usage_records", "ai_usage_operational_records"],
    },
)

VISIBILITY_MODES: tuple[str, ...] = (
    "private_internal",
    "operator_private",
    "team_safe",
    "client_safe",
    "public_sanitized",
)

PRIVATE_EXPORT_FIELDS: tuple[str, ...] = (
    "raw_work_orders",
    "handoffs",
    "operator_decisions",
    "raw_telemetry",
    "local_paths",
    "local_evidence",
    "cutover_rollback_details",
    "private_project_details",
    "career_application_data",
    "compensation_strategy",
    "secrets_auth_config_values",
    "unsanitized_security_findings",
)

WATCH_TASKS: tuple[dict[str, Any], ...] = (
    {
        "watch_id": "scheduled_dashboard_health",
        "watch_type": "dashboard_health",
        "schedule": "manual_or_daily_opt_in",
        "read_write_behavior": "read_only",
    },
    {
        "watch_id": "release_gate_watcher",
        "watch_type": "release_gate",
        "schedule": "manual_or_before_release_opt_in",
        "read_write_behavior": "read_only",
    },
    {
        "watch_id": "adapter_staleness_watcher",
        "watch_type": "adapter_staleness",
        "schedule": "manual_or_daily_opt_in",
        "read_write_behavior": "read_only",
    },
    {
        "watch_id": "contract_atlas_freshness_watcher",
        "watch_type": "contract_atlas_freshness",
        "schedule": "manual_or_daily_opt_in",
        "read_write_behavior": "read_only",
    },
    {
        "watch_id": "docs_drift_watcher",
        "watch_type": "docs_drift",
        "schedule": "manual_or_pre_commit_opt_in",
        "read_write_behavior": "read_only",
    },
    {
        "watch_id": "project_registry_freshness_watcher",
        "watch_type": "project_registry_freshness",
        "schedule": "manual_or_weekly_opt_in",
        "read_write_behavior": "read_only",
    },
    {
        "watch_id": "security_readiness_watcher",
        "watch_type": "security_readiness",
        "schedule": "manual_or_release_opt_in",
        "read_write_behavior": "read_only",
    },
    {
        "watch_id": "backup_restore_health_watcher",
        "watch_type": "backup_restore_health",
        "schedule": "manual_or_weekly_opt_in",
        "read_write_behavior": "read_only",
    },
)

INSTALLER_COMMANDS: tuple[str, ...] = (
    "ds install",
    "ds version",
    "ds doctor",
    "ds repair",
    "ds update-check",
    "ds backup",
    "ds restore-check",
    "ds uninstall-check",
    "ds acceptance",
)

DEMO_PACKETS: tuple[dict[str, Any], ...] = (
    {"packet_id": "demo_5_minute", "packet_type": "5_minute_demo_script"},
    {"packet_id": "demo_15_minute_technical", "packet_type": "15_minute_technical_walkthrough"},
    {"packet_id": "demo_disaster_prevention", "packet_type": "disaster_prevention_demo"},
    {
        "packet_id": "demo_external_project_validation",
        "packet_type": "external_project_validation_demo",
    },
    {"packet_id": "demo_analytics_only_pilot", "packet_type": "analytics_only_company_pilot_demo"},
    {"packet_id": "demo_architecture_packet", "packet_type": "architecture_diagram_packet"},
    {"packet_id": "demo_before_after_proof", "packet_type": "before_after_proof_packet"},
    {"packet_id": "demo_sanitized_case_study", "packet_type": "sanitized_portfolio_case_study"},
)


def platform_hardening_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return the full platform-hardening dashboard read model."""

    table_status = _table_status(conn)
    return {
        "schema": PLATFORM_HARDENING_SCHEMA,
        "model_name": "dream_studio_platform_hardening",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "db_write_authorized": False,
        "execution_authorized": False,
        "source_tables": list(PLATFORM_HARDENING_TABLES),
        "source_status": table_status,
        "milestones": {
            "skill_evaluation_harness": skill_evaluation_harness_status(conn),
            "policy_permission_engine": policy_engine_status(conn),
            "engineering_connector_ingestion": connector_ingestion_framework_status(conn),
        },
        "validation": {
            "status": "pass" if not validate_platform_hardening_summary(conn) else "fail",
            "errors": validate_platform_hardening_summary(conn),
        },
    }


def skill_evaluation_harness_status(conn: sqlite3.Connection) -> dict[str, Any]:
    # skill_evaluation_runs: dropped migration 131 (dead writer, test-only callers)
    return {
        "milestone_id": "skill_evaluation_harness",
        "status": "table_dropped",
        "evaluated_workflows": [
            {"workflow_id": workflow_id} for workflow_id in EVALUATED_WORKFLOWS
        ],
        "record_count": 0,
        "status_counts": {},
        "empty_state": "skill_evaluation_runs dropped in migration 131.",
    }


def policy_engine_status(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = _rows(conn, "policy_decision_records")
    return {
        "milestone_id": "policy_permission_engine_maturation",
        "status": (
            "runtime_validated"
            if "policy_decision_records" in _existing_tables(conn)
            else "schema_pending"
        ),
        "actions": [dict(item) for item in POLICY_ACTIONS],
        "decision_count": len(rows),
        "decision_state_counts": dict(
            sorted(Counter(row.get("decision_state") for row in rows).items())
        ),
        "integration_targets": [
            "Work Orders",
            "route decisions",
            "dashboard attention",
            "release readiness",
            "security/readiness gates",
            "external project pipeline",
            "career/application automation",
            "Contract Atlas",
        ],
        "empty_state": "No policy decisions recorded yet; default action matrix remains enforceable.",
    }


def evaluate_policy_decision(
    *,
    actor: str,
    action: str,
    target: str | None = None,
    scope: dict[str, Any] | None = None,
    approved: bool = False,
) -> dict[str, Any]:
    policy = next((item for item in POLICY_ACTIONS if item["action"] == action), None)
    if policy is None:
        return {
            "decision_state": "deferred",
            "risk_level": "high",
            "approval_requirement": "manual_review_required",
            "evidence_requirement": "action_not_registered",
            "rollback_requirement": "manual_review_required",
            "reason": "Unknown policy action routes to manual review.",
        }
    default_state = str(policy["default_decision"])
    state = "allowed" if approved and default_state != "denied" else default_state
    return {
        "actor": actor,
        "action": action,
        "target": target,
        "scope": scope or {},
        "risk_level": policy["risk_level"],
        "approval_requirement": policy["approval_requirement"],
        "evidence_requirement": "evidence_refs_required_for_medium_or_higher_risk",
        "rollback_requirement": "rollback_or_hold_required_before_mutation",
        "decision_state": state,
        "reason": (
            "Approved within current scope."
            if state == "allowed"
            else "Approval boundary not satisfied."
        ),
        "source_authority": "dream_studio_policy_engine",
        "dashboard_attention_impact": "attention_required" if state != "allowed" else "none",
    }


def record_policy_decision(conn: sqlite3.Connection, *, decision_id: str, **values: Any) -> None:
    evidence_refs = values.get("evidence_refs")
    decision_inputs = {
        key: values[key]
        for key in ("actor", "action", "target", "scope", "approved")
        if key in values
    }
    decision = evaluate_policy_decision(**decision_inputs)
    _require_table(conn, "policy_decision_records")
    conn.execute(
        """
        INSERT OR REPLACE INTO policy_decision_records (
            decision_id, actor, action, target, scope_json, risk_level,
            approval_requirement, evidence_requirement, rollback_requirement,
            decision_state, reason, source_authority, dashboard_attention_impact,
            evidence_refs_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            decision_id,
            decision["actor"],
            decision["action"],
            decision.get("target"),
            _json(decision.get("scope"), {}),
            decision["risk_level"],
            decision["approval_requirement"],
            decision["evidence_requirement"],
            decision["rollback_requirement"],
            decision["decision_state"],
            decision["reason"],
            decision["source_authority"],
            decision["dashboard_attention_impact"],
            _json(evidence_refs, []),
        ),
    )
    conn.commit()


def connector_ingestion_framework_status(conn: sqlite3.Connection) -> dict[str, Any]:
    # connector_ingestion_runs: dropped migration 131 (dead writer, test-only callers)
    return {
        "milestone_id": "engineering_connector_ingestion_framework",
        "status": "table_dropped",
        "connectors": [dict(connector) for connector in CONNECTOR_DEFINITIONS],
        "run_count": 0,
        "status_counts": {},
        "analytics_only_supported": True,
    }


def _connector_project_records(records: Any, *, source_type: str) -> list[dict[str, Any]]:
    if not isinstance(records, list):
        return []
    normalized: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        project_id = str(record.get("project_id") or record.get("id") or "").strip()
        normalized.append(
            {
                **record,
                "project_id": project_id or stable_platform_hardening_id("project", record),
                "project_name": record.get("project_name") or record.get("name") or project_id,
                "project_path": record.get("project_path") or "unavailable",
                "project_source": record.get("project_source") or f"connector:{source_type}",
            }
        )
    return normalized


def validate_platform_hardening_summary(conn: sqlite3.Connection) -> list[str]:
    errors: list[str] = []
    # PLATFORM_HARDENING_TABLES now only contains policy_decision_records;
    # skill_evaluation_runs and connector_ingestion_runs dropped in migration 131.
    tables = _existing_tables(conn)
    missing = sorted(set(PLATFORM_HARDENING_TABLES) - tables)
    if missing:
        errors.append(f"missing platform hardening tables: {missing}")
    if len(EVALUATED_WORKFLOWS) < 11:
        errors.append("representative workflow evaluation set is incomplete")
    policy_actions = {item["action"] for item in POLICY_ACTIONS}
    for required in (
        "live_sqlite_write",
        "external_project_mutation",
        "push_tag_merge_deploy",
        "secret_sensitive_access",
        "career_application_submission",
        "docker_runtime_execution",
    ):
        if required not in policy_actions:
            errors.append(f"missing policy action: {required}")
    for connector in CONNECTOR_DEFINITIONS:
        if connector["read_write_mode"] not in {"read_only", "local_file_read"}:
            errors.append(f"connector {connector['connector_id']} is not read-only")
    return errors


def _connector_for_source(source_type: str) -> dict[str, Any]:
    for connector in CONNECTOR_DEFINITIONS:
        if connector["source_type"] == source_type:
            return dict(connector)
    raise ValueError(f"unsupported connector source type: {source_type}")


def _table_status(conn: sqlite3.Connection) -> dict[str, Any]:
    tables = _existing_tables(conn)
    missing = sorted(set(PLATFORM_HARDENING_TABLES) - tables)
    return {
        "status": "available" if not missing else "partial",
        "missing_tables": missing,
    }


def _existing_tables(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        ).fetchall()
    }


def _rows(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    if table not in _existing_tables(conn):
        return []
    cursor = conn.execute(f"SELECT * FROM {table} ORDER BY created_at DESC LIMIT 200")
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]


def _require_table(conn: sqlite3.Connection, table: str) -> None:
    if table not in _existing_tables(conn):
        raise RuntimeError(f"required platform hardening table missing: {table}")


def _json(value: Any, default: Any) -> str:
    if value is None:
        value = default
    return json.dumps(value, sort_keys=True)


def _contains_secret_like_keys(value: dict[str, Any]) -> bool:
    secret_terms = ("secret", "token", "password", "api_key", "credential")
    return any(any(term in str(key).lower() for term in secret_terms) for key in value)


def stable_platform_hardening_id(prefix: str, payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"
