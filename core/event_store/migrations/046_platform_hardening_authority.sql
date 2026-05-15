-- Dream Studio platform hardening authority records.
--
-- Additive-only migration. These tables store evaluated, policy-backed,
-- sanitized platform-readiness evidence without replacing existing authority
-- tables such as validation_results, security_findings, Work Orders, or
-- analytics ingestion records.

CREATE TABLE IF NOT EXISTS skill_evaluation_runs (
    evaluation_id TEXT PRIMARY KEY,
    target_type TEXT NOT NULL CHECK (target_type IN ('skill', 'workflow')),
    target_id TEXT NOT NULL,
    target_version TEXT,
    fixture_id TEXT,
    expected_output_contract_json TEXT NOT NULL DEFAULT '{}',
    rubric_scores_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL CHECK (status IN ('pass', 'warn', 'fail', 'manual_review_required', 'unavailable')),
    promotion_decision TEXT NOT NULL DEFAULT 'manual_review_required',
    rollback_decision TEXT NOT NULL DEFAULT 'manual_review_required',
    failure_patterns_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS policy_decision_records (
    decision_id TEXT PRIMARY KEY,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT,
    scope_json TEXT NOT NULL DEFAULT '{}',
    risk_level TEXT NOT NULL CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
    approval_requirement TEXT NOT NULL,
    evidence_requirement TEXT NOT NULL,
    rollback_requirement TEXT NOT NULL,
    decision_state TEXT NOT NULL CHECK (decision_state IN ('allowed', 'denied', 'deferred')),
    reason TEXT,
    source_authority TEXT NOT NULL DEFAULT 'dream_studio_policy_engine',
    dashboard_attention_impact TEXT NOT NULL DEFAULT 'none',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS connector_ingestion_runs (
    ingestion_run_id TEXT PRIMARY KEY,
    connector_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    authentication_requirement TEXT NOT NULL DEFAULT 'none',
    read_write_mode TEXT NOT NULL DEFAULT 'read_only',
    supported_records_json TEXT NOT NULL DEFAULT '[]',
    normalization_targets_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL CHECK (status IN ('planned', 'imported', 'partial', 'failed', 'manual_review_required')),
    records_planned_json TEXT NOT NULL DEFAULT '{}',
    records_written_json TEXT NOT NULL DEFAULT '{}',
    privacy_rules_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS privacy_redaction_export_records (
    export_id TEXT PRIMARY KEY,
    visibility_mode TEXT NOT NULL CHECK (visibility_mode IN ('private_internal', 'operator_private', 'team_safe', 'client_safe', 'public_sanitized')),
    export_type TEXT NOT NULL,
    redaction_profile TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pass', 'blocked', 'manual_review_required')),
    blocked_reasons_json TEXT NOT NULL DEFAULT '[]',
    sanitized_fields_json TEXT NOT NULL DEFAULT '[]',
    leakage_checks_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS local_watch_schedule_records (
    watch_id TEXT PRIMARY KEY,
    watch_type TEXT NOT NULL,
    schedule TEXT NOT NULL,
    scope_json TEXT NOT NULL DEFAULT '{}',
    opt_in_required INTEGER NOT NULL DEFAULT 1,
    enabled INTEGER NOT NULL DEFAULT 0,
    read_write_behavior TEXT NOT NULL DEFAULT 'read_only',
    risk_level TEXT NOT NULL DEFAULT 'low',
    evidence_output TEXT NOT NULL DEFAULT 'dashboard_attention',
    failure_behavior TEXT NOT NULL DEFAULT 'attention_only',
    disable_command TEXT NOT NULL DEFAULT 'ds watch disable',
    approval_requirement TEXT NOT NULL DEFAULT 'operator_enable_required',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS team_rollup_records (
    rollup_id TEXT PRIMARY KEY,
    visibility_mode TEXT NOT NULL DEFAULT 'team_safe',
    aggregation_scope_json TEXT NOT NULL DEFAULT '{}',
    summary_json TEXT NOT NULL DEFAULT '{}',
    excluded_private_data_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL CHECK (status IN ('pass', 'blocked', 'manual_review_required')),
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS installer_distribution_checks (
    check_id TEXT PRIMARY KEY,
    check_type TEXT NOT NULL,
    command TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pass', 'warn', 'fail', 'manual_review_required')),
    mutation_authorized INTEGER NOT NULL DEFAULT 0,
    rollback_guidance TEXT,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS demo_case_study_packets (
    packet_id TEXT PRIMARY KEY,
    packet_type TEXT NOT NULL,
    audience TEXT,
    visibility_mode TEXT NOT NULL DEFAULT 'private_internal',
    status TEXT NOT NULL CHECK (status IN ('draft', 'ready', 'blocked', 'manual_review_required')),
    sanitized INTEGER NOT NULL DEFAULT 0,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    blocked_private_fields_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_skill_evaluation_runs_target
ON skill_evaluation_runs(target_type, target_id);

CREATE INDEX IF NOT EXISTS idx_policy_decision_records_action
ON policy_decision_records(action, decision_state);

CREATE INDEX IF NOT EXISTS idx_connector_ingestion_runs_source
ON connector_ingestion_runs(source_type, status);

CREATE INDEX IF NOT EXISTS idx_privacy_redaction_export_records_visibility
ON privacy_redaction_export_records(visibility_mode, status);

CREATE INDEX IF NOT EXISTS idx_local_watch_schedule_records_enabled
ON local_watch_schedule_records(watch_type, enabled);
