-- Migration 043: AI adapter usage accounting and operational value telemetry
-- Tracks adapter/model billing visibility honestly without converting tokens
-- into dollars unless cost metadata is explicitly available.

CREATE TABLE IF NOT EXISTS token_usage_records (
    token_usage_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    process_run_id TEXT,
    agent_id TEXT,
    skill_id TEXT,
    workflow_id TEXT,
    hook_id TEXT,
    model_id TEXT,
    provider TEXT,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_cost NUMERIC(20, 8) NOT NULL DEFAULT 0,
    purpose TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]'
);

ALTER TABLE token_usage_records
ADD COLUMN adapter_id TEXT;

ALTER TABLE token_usage_records
ADD COLUMN billing_mode TEXT NOT NULL DEFAULT 'unknown';

ALTER TABLE token_usage_records
ADD COLUMN token_visibility TEXT NOT NULL DEFAULT 'exact';

ALTER TABLE token_usage_records
ADD COLUMN cost_visibility TEXT NOT NULL DEFAULT 'unknown';

ALTER TABLE token_usage_records
ADD COLUMN usage_source TEXT NOT NULL DEFAULT 'local_telemetry';

ALTER TABLE token_usage_records
ADD COLUMN cost_source TEXT NOT NULL DEFAULT 'unknown';

ALTER TABLE token_usage_records
ADD COLUMN accounting_confidence TEXT NOT NULL DEFAULT 'medium';

CREATE TABLE IF NOT EXISTS ai_adapter_accounting_profiles (
    profile_id TEXT PRIMARY KEY,
    adapter_id TEXT NOT NULL,
    provider TEXT,
    model_id TEXT,
    configuration_label TEXT NOT NULL,
    billing_mode TEXT NOT NULL,
    token_visibility TEXT NOT NULL,
    cost_visibility TEXT NOT NULL,
    usage_source TEXT NOT NULL,
    cost_source TEXT NOT NULL DEFAULT 'unavailable',
    confidence TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (billing_mode IN (
        'subscription_plan',
        'plan_allowance',
        'token_metered',
        'api_metered',
        'credit_metered',
        'enterprise_contract',
        'unknown',
        'unavailable'
    )),
    CHECK (token_visibility IN ('exact', 'partial', 'estimated', 'unavailable')),
    CHECK (cost_visibility IN (
        'exact',
        'provider_reported',
        'estimated',
        'allocated_subscription_cost',
        'unavailable',
        'unknown'
    )),
    CHECK (usage_source IN (
        'provider_metadata',
        'provider_usage_export',
        'local_telemetry',
        'plan_usage_panel',
        'manual_config',
        'unavailable'
    )),
    CHECK (cost_source IN (
        'provider_metadata',
        'provider_usage_export',
        'billing_api',
        'plan_allocation_config',
        'local_estimate',
        'unavailable',
        'unknown'
    )),
    CHECK (confidence IN ('high', 'medium', 'low', 'unknown')),
    CHECK (active IN (0, 1)),
    FOREIGN KEY (adapter_id) REFERENCES adapter_authority_profiles(adapter_id)
);

CREATE TABLE IF NOT EXISTS ai_usage_operational_records (
    usage_record_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    work_order_id TEXT,
    process_run_id TEXT,
    adapter_id TEXT NOT NULL,
    provider TEXT,
    model_id TEXT,
    accounting_profile_id TEXT,
    token_usage_id TEXT,
    billing_mode TEXT NOT NULL DEFAULT 'unknown',
    token_visibility TEXT NOT NULL DEFAULT 'unavailable',
    cost_visibility TEXT NOT NULL DEFAULT 'unknown',
    usage_source TEXT NOT NULL DEFAULT 'local_telemetry',
    cost_source TEXT NOT NULL DEFAULT 'unknown',
    confidence TEXT NOT NULL DEFAULT 'unknown',
    input_tokens INTEGER,
    output_tokens INTEGER,
    cached_tokens INTEGER,
    total_tokens INTEGER,
    cost_amount NUMERIC(20, 8),
    cost_currency TEXT,
    run_count INTEGER NOT NULL DEFAULT 1,
    files_touched_json TEXT NOT NULL DEFAULT '[]',
    commands_run_json TEXT NOT NULL DEFAULT '[]',
    validation_result TEXT,
    pr_result_outcome TEXT,
    success INTEGER,
    failure_reason TEXT,
    rework_needed INTEGER,
    security_findings_json TEXT NOT NULL DEFAULT '[]',
    readiness_findings_json TEXT NOT NULL DEFAULT '[]',
    duration_ms INTEGER,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (billing_mode IN (
        'subscription_plan',
        'plan_allowance',
        'token_metered',
        'api_metered',
        'credit_metered',
        'enterprise_contract',
        'unknown',
        'unavailable'
    )),
    CHECK (token_visibility IN ('exact', 'partial', 'estimated', 'unavailable')),
    CHECK (cost_visibility IN (
        'exact',
        'provider_reported',
        'estimated',
        'allocated_subscription_cost',
        'unavailable',
        'unknown'
    )),
    CHECK (usage_source IN (
        'provider_metadata',
        'provider_usage_export',
        'local_telemetry',
        'plan_usage_panel',
        'manual_config',
        'unavailable'
    )),
    CHECK (cost_source IN (
        'provider_metadata',
        'provider_usage_export',
        'billing_api',
        'plan_allocation_config',
        'local_estimate',
        'unavailable',
        'unknown'
    )),
    CHECK (confidence IN ('high', 'medium', 'low', 'unknown')),
    CHECK (success IN (0, 1) OR success IS NULL),
    CHECK (rework_needed IN (0, 1) OR rework_needed IS NULL),
    FOREIGN KEY (adapter_id) REFERENCES adapter_authority_profiles(adapter_id),
    FOREIGN KEY (accounting_profile_id) REFERENCES ai_adapter_accounting_profiles(profile_id),
    FOREIGN KEY (token_usage_id) REFERENCES token_usage_records(token_usage_id)
);

CREATE INDEX IF NOT EXISTS idx_ai_accounting_profiles_adapter
ON ai_adapter_accounting_profiles(adapter_id, provider, model_id, active);

CREATE INDEX IF NOT EXISTS idx_ai_usage_operational_scope
ON ai_usage_operational_records(project_id, milestone_id, task_id, work_order_id, adapter_id);

CREATE INDEX IF NOT EXISTS idx_ai_usage_operational_process
ON ai_usage_operational_records(process_run_id, adapter_id, model_id);
