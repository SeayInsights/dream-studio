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

-- policy_decision_records: dropped in migration 133 (test-only writer — record_policy_decision()
-- only called from tests/unit/test_platform_hardening_sequence.py; no production CLI, hook,
-- or route calls the write function; evaluate_policy_decision() is the production path,
-- which is read-only and does not touch this table).

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

-- privacy_redaction_export_records, local_watch_schedule_records,
-- team_rollup_records, installer_distribution_checks, demo_case_study_packets
-- removed in migration 128 (dead tables; sanitize_export_packet and similar
-- functions in platform_hardening.py that wrote to them have been removed).
-- skill_evaluation_runs, policy_decision_records, connector_ingestion_runs
-- are KEPT (live consumers remain in platform_hardening.py).

CREATE INDEX IF NOT EXISTS idx_skill_evaluation_runs_target
ON skill_evaluation_runs(target_type, target_id);

-- idx_policy_decision_records_action: dropped with policy_decision_records in migration 133.

CREATE INDEX IF NOT EXISTS idx_connector_ingestion_runs_source
ON connector_ingestion_runs(source_type, status);

-- idx_privacy_redaction_export_records_visibility and
-- idx_local_watch_schedule_records_enabled removed in migration 128 (dead tables).
