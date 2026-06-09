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

from core.analytics_ingestion import ingest_analytics_payload

PLATFORM_HARDENING_SCHEMA = "dream_studio.platform_hardening.v1"

PLATFORM_HARDENING_TABLES: tuple[str, ...] = (
    "skill_evaluation_runs",
    "policy_decision_records",
    "connector_ingestion_runs",
    "privacy_redaction_export_records",
    "local_watch_schedule_records",
    "team_rollup_records",
    "installer_distribution_checks",
    "demo_case_study_packets",
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
        "normalization_targets": ["reg_projects", "validation_results", "artifact_records"],
    },
    {
        "connector_id": "github_actions_metadata",
        "source_type": "github_actions",
        "authentication_requirement": "optional_token_or_export",
        "read_write_mode": "read_only",
        "supported_records": ["validations", "ci_logs"],
        "normalization_targets": ["validation_results", "artifact_records"],
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
            "privacy_redaction_secret_boundary": privacy_redaction_status(conn),
            "local_watch_scheduled_validation": local_watch_scheduler_status(conn),
            "team_pilot_rollup_reporting": team_pilot_rollup_status(conn),
            "installer_distribution_hardening": installer_distribution_status(conn),
            "demo_case_study_system": demo_case_study_system_status(conn),
        },
        "validation": {
            "status": "pass" if not validate_platform_hardening_summary(conn) else "fail",
            "errors": validate_platform_hardening_summary(conn),
        },
    }


def skill_evaluation_harness_status(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = _rows(conn, "skill_evaluation_runs")
    status_counts = Counter(row.get("status") for row in rows)
    return {
        "milestone_id": "skill_evaluation_harness",
        "status": (
            "runtime_validated"
            if "skill_evaluation_runs" in _existing_tables(conn)
            else "schema_pending"
        ),
        "evaluated_workflows": [
            {
                "workflow_id": workflow_id,
                "purpose": f"Evaluate {workflow_id} with golden fixtures and rubric scores.",
                "input_contract": [
                    "golden_task_fixture",
                    "expected_output_contract",
                    "evidence_refs",
                ],
                "output_contract": [
                    "rubric_scores",
                    "status",
                    "promotion_decision",
                    "rollback_decision",
                ],
                "expected_evidence": [
                    "fixture",
                    "actual_output",
                    "rubric_result",
                    "validation_result",
                ],
                "states": ["pass", "warn", "fail", "manual_review_required", "unavailable"],
                "promotion_threshold": "all_required_rubrics_pass_with_evidence",
                "rollback_threshold": "critical_regression_or_score_below_threshold",
                "known_limitations": "No skill is claimed improved without evaluation rows.",
                "contract_atlas_impact": "platform_hardening.skill_evaluation_harness",
            }
            for workflow_id in EVALUATED_WORKFLOWS
        ],
        "record_count": len(rows),
        "status_counts": dict(sorted(status_counts.items())),
        "empty_state": "No skill evaluation runs recorded yet; workflows are measurable but unscored.",
    }


def record_skill_evaluation(conn: sqlite3.Connection, **values: Any) -> None:
    # Superseded by Phase 19 gap/expansion pipeline (WO-LEARN). Skill
    # performance signals are now captured by FrictionSignalHarvester and
    # promoted by RetroactiveValidator via ds_user_extensions. This function
    # writes to skill_evaluation_runs (Shared Intelligence subsystem); it
    # remains callable for SI workflows but is not wired into end_session().
    _require_table(conn, "skill_evaluation_runs")
    conn.execute(
        """
        INSERT OR REPLACE INTO skill_evaluation_runs (
            evaluation_id, target_type, target_id, target_version, fixture_id,
            expected_output_contract_json, rubric_scores_json, status,
            promotion_decision, rollback_decision, failure_patterns_json,
            evidence_refs_json, source_refs_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            values["evaluation_id"],
            values.get("target_type", "workflow"),
            values["target_id"],
            values.get("target_version"),
            values.get("fixture_id"),
            _json(values.get("expected_output_contract"), {}),
            _json(values.get("rubric_scores"), {}),
            values.get("status", "manual_review_required"),
            values.get("promotion_decision", "manual_review_required"),
            values.get("rollback_decision", "manual_review_required"),
            _json(values.get("failure_patterns"), []),
            _json(values.get("evidence_refs"), []),
            _json(values.get("source_refs"), []),
        ),
    )
    conn.commit()


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
    rows = _rows(conn, "connector_ingestion_runs")
    return {
        "milestone_id": "engineering_connector_ingestion_framework",
        "status": (
            "runtime_validated"
            if "connector_ingestion_runs" in _existing_tables(conn)
            else "schema_pending"
        ),
        "connectors": [
            {
                **dict(connector),
                "privacy_sensitive_data_rules": [
                    "read only by default",
                    "normalize into current SQLite authority",
                    "do not create connector-specific truth",
                    "preserve evidence refs",
                    "redact secrets and private local paths before export",
                ],
                "retry_failure_behavior": "record failed/partial run and dashboard attention",
                "dashboard_visibility": "Project Details, Adapter Usage, validation/security/readiness summaries",
                "contract_atlas_impact": "platform_hardening.connector_ingestion",
            }
            for connector in CONNECTOR_DEFINITIONS
        ],
        "run_count": len(rows),
        "status_counts": dict(sorted(Counter(row.get("status") for row in rows).items())),
        "analytics_only_supported": True,
    }


def ingest_connector_payload(
    conn: sqlite3.Connection,
    *,
    ingestion_run_id: str,
    source_type: str,
    payload: dict[str, Any],
    execute: bool = False,
) -> dict[str, Any]:
    connector = _connector_for_source(source_type)
    normalized_payload = {
        "source_refs": payload.get("source_refs", []),
        "evidence_refs": payload.get("evidence_refs", []),
        "projects": _connector_project_records(
            payload.get("projects", []),
            source_type=source_type,
        ),
        "validations": payload.get("validations", []),
        "findings": payload.get("findings", []),
        "token_usage": payload.get("token_usage", []),
        "ai_usage": payload.get("ai_usage", []),
        "components": payload.get("components", []),
        "dependencies": payload.get("dependencies", []),
        "prds": payload.get("prds", []),
        "readiness_assessments": payload.get("readiness_assessments", []),
    }
    result = ingest_analytics_payload(conn, normalized_payload, execute=execute)
    _require_table(conn, "connector_ingestion_runs")
    conn.execute(
        """
        INSERT OR REPLACE INTO connector_ingestion_runs (
            ingestion_run_id, connector_id, source_type, authentication_requirement,
            read_write_mode, supported_records_json, normalization_targets_json,
            status, records_planned_json, records_written_json, privacy_rules_json,
            evidence_refs_json, source_refs_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            ingestion_run_id,
            connector["connector_id"],
            connector["source_type"],
            connector["authentication_requirement"],
            connector["read_write_mode"],
            _json(connector["supported_records"], []),
            _json(connector["normalization_targets"], []),
            "imported" if execute else "planned",
            _json(result["records_planned"], {}),
            _json(result["records_written"], {}),
            _json(["no_secret_values", "source_refs_required", "sanitize_before_export"], []),
            _json(payload.get("evidence_refs"), []),
            _json(payload.get("source_refs"), []),
        ),
    )
    conn.commit()
    return {
        "connector": connector,
        "analytics_ingestion": result,
        "status": "imported" if execute else "planned",
        "execute": execute,
        "parallel_truth_created": False,
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


def privacy_redaction_status(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = _rows(conn, "privacy_redaction_export_records")
    return {
        "milestone_id": "privacy_redaction_and_secret_boundary_maturation",
        "status": (
            "runtime_validated"
            if "privacy_redaction_export_records" in _existing_tables(conn)
            else "schema_pending"
        ),
        "visibility_modes": list(VISIBILITY_MODES),
        "private_export_fields": list(PRIVATE_EXPORT_FIELDS),
        "redaction_profiles": {
            "private_internal": {"redact_private_fields": False, "public_export_allowed": False},
            "operator_private": {"redact_private_fields": False, "public_export_allowed": False},
            "team_safe": {"redact_private_fields": True, "public_export_allowed": False},
            "client_safe": {"redact_private_fields": True, "public_export_allowed": False},
            "public_sanitized": {"redact_private_fields": True, "public_export_allowed": True},
        },
        "export_count": len(rows),
        "status_counts": dict(sorted(Counter(row.get("status") for row in rows).items())),
    }


def sanitize_export_packet(
    packet: dict[str, Any],
    *,
    visibility_mode: str = "public_sanitized",
) -> dict[str, Any]:
    if visibility_mode not in VISIBILITY_MODES:
        raise ValueError(f"unsupported visibility mode: {visibility_mode}")
    sanitized = {key: value for key, value in packet.items() if key not in PRIVATE_EXPORT_FIELDS}
    removed = [key for key in packet if key in PRIVATE_EXPORT_FIELDS]
    blocked = []
    if visibility_mode == "public_sanitized" and removed:
        blocked.append("private_fields_removed_before_public_export")
    return {
        "visibility_mode": visibility_mode,
        "status": "pass" if not _contains_secret_like_keys(sanitized) else "blocked",
        "sanitized_packet": sanitized,
        "sanitized_fields": removed,
        "blocked_reasons": (
            blocked if not _contains_secret_like_keys(sanitized) else ["secret_like_key_present"]
        ),
        "secret_values_inspected": False,
    }


def local_watch_scheduler_status(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = _rows(conn, "local_watch_schedule_records")
    return {
        "milestone_id": "local_watch_and_scheduled_validation_runtime",
        "status": (
            "runtime_validated"
            if "local_watch_schedule_records" in _existing_tables(conn)
            else "schema_pending"
        ),
        "opt_in": True,
        "background_processes_started": False,
        "watch_tasks": [
            {
                **dict(task),
                "opt_in_required": True,
                "enabled_by_default": False,
                "risk_level": "low",
                "evidence_output": "dashboard_attention",
                "failure_behavior": "attention_only",
                "disable_command": "ds watch disable",
                "approval_requirement": "operator_enable_required",
            }
            for task in WATCH_TASKS
        ],
        "configured_watch_count": len(rows),
        "enabled_count": sum(1 for row in rows if row.get("enabled")),
    }


def team_pilot_rollup_status(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = _rows(conn, "team_rollup_records")
    return {
        "milestone_id": "team_pilot_rollup_and_sanitized_reporting",
        "status": (
            "runtime_validated"
            if "team_rollup_records" in _existing_tables(conn)
            else "schema_pending"
        ),
        "local_first": True,
        "sanitized_by_default": True,
        "rollup_sections": [
            "project_milestone_task_summary",
            "security_readiness_summary",
            "adapter_usage_summary",
            "validation_release_summary",
            "attention_blocker_summary",
        ],
        "excluded_private_data": list(PRIVATE_EXPORT_FIELDS),
        "record_count": len(rows),
        "status_counts": dict(sorted(Counter(row.get("status") for row in rows).items())),
    }


def installer_distribution_status(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = _rows(conn, "installer_distribution_checks")
    return {
        "milestone_id": "installer_distribution_hardening",
        "status": (
            "runtime_validated"
            if "installer_distribution_checks" in _existing_tables(conn)
            else "schema_pending"
        ),
        "commands": list(INSTALLER_COMMANDS),
        "normal_user_workflow": [
            "install Dream Studio",
            "select modules",
            "run ds from anywhere",
            "launch dashboard",
            "validate runtime health",
            "configure supported adapters",
            "back up state",
            "run restore-check, update-check, and uninstall-check",
        ],
        "mutation_default": "plan_or_check_only",
        "check_count": len(rows),
        "status_counts": dict(sorted(Counter(row.get("status") for row in rows).items())),
    }


def demo_case_study_system_status(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = _rows(conn, "demo_case_study_packets")
    return {
        "milestone_id": "dream_studio_demo_and_case_study_system",
        "status": (
            "runtime_validated"
            if "demo_case_study_packets" in _existing_tables(conn)
            else "schema_pending"
        ),
        "packets": [
            {
                **dict(packet),
                "evidence_backed": True,
                "sanitized_required": True,
                "private_fields_forbidden": list(PRIVATE_EXPORT_FIELDS),
                "operator_approval_required_for_public_use": True,
            }
            for packet in DEMO_PACKETS
        ],
        "record_count": len(rows),
        "status_counts": dict(sorted(Counter(row.get("status") for row in rows).items())),
    }


def validate_platform_hardening_summary(conn: sqlite3.Connection) -> list[str]:
    errors: list[str] = []
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
    if "public_sanitized" not in VISIBILITY_MODES:
        errors.append("public_sanitized visibility mode missing")
    for connector in CONNECTOR_DEFINITIONS:
        if connector["read_write_mode"] not in {"read_only", "local_file_read"}:
            errors.append(f"connector {connector['connector_id']} is not read-only")
    for task in WATCH_TASKS:
        if task["read_write_behavior"] != "read_only":
            errors.append(f"watch task {task['watch_id']} is not read-only")
    if "ds doctor" not in INSTALLER_COMMANDS or "ds repair" not in INSTALLER_COMMANDS:
        errors.append("installer doctor/repair commands missing")
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
