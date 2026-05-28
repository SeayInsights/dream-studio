-- Migration 081: Convert financial REAL columns to NUMERIC(20, 8).
--
-- Background:
--   ds-quality:database Batch 7 audit (18.4.2) surfaced 4 critical db-005
--   findings: estimated_cost REAL in token_usage_records and cost_amount REAL
--   in ai_usage_operational_records. REAL (IEEE 754 float) accumulates rounding
--   error over repeated additions. NUMERIC(20, 8) provides exact decimal
--   arithmetic adequate for USD costs and microcents precision.
--
-- Pattern:
--   SQLite does not support ALTER COLUMN TYPE. This migration uses the standard
--   table-reconstruction pattern: (1) create new table with corrected type,
--   (2) copy data with explicit CAST, (3) drop old table, (4) rename new table.
--   Followed by recreation of any associated objects (FK-dependent tables are
--   not altered — only the FK-source ai_usage_operational_records references
--   token_usage_records.token_usage_id (PK), which is unchanged).
--
-- Safety:
--   - CAST(REAL AS NUMERIC) is lossless for the cost values stored (small floats
--     representing USD amounts with sub-cent precision).
--   - PRAGMA foreign_keys = OFF used to suppress FK constraint checking during
--     reconstruction. Re-enabled at the end.
--   - IF NOT EXISTS / DROP TABLE IF EXISTS used throughout for idempotency.
--   - Backup of live DB before applying is the recommended rollback path.
--
-- Affected columns:
--   1. token_usage_records.estimated_cost  REAL NOT NULL DEFAULT 0  → NUMERIC(20,8)
--   2. ai_usage_operational_records.cost_amount  REAL               → NUMERIC(20,8)

PRAGMA foreign_keys = OFF;
-- SQLite 3.26+ validates all views during ALTER TABLE RENAME; any view referencing
-- a missing table aborts the rename.  vw_activity_timeline references canonical_events,
-- which is owned by EventStore._init_tables() and absent from migrations (pre-existing
-- architectural debt captured in .planning/workstreams/18-4-2-followup-1/findings.md).
-- Alternative pattern: drop all views before reconstruction then recreate (migration 062
-- approach), but that cannot recreate vw_activity_timeline for the same reason.
-- legacy_alter_table is scoped to this migration: ON here, OFF at end.
PRAGMA legacy_alter_table = ON;

-- ── Part 1: token_usage_records.estimated_cost ──────────────────────────────

CREATE TABLE IF NOT EXISTS token_usage_records_new (
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
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    adapter_id TEXT,
    billing_mode TEXT NOT NULL DEFAULT 'unknown',
    token_visibility TEXT NOT NULL DEFAULT 'exact',
    cost_visibility TEXT NOT NULL DEFAULT 'unknown',
    usage_source TEXT NOT NULL DEFAULT 'local_telemetry',
    cost_source TEXT NOT NULL DEFAULT 'unknown',
    accounting_confidence TEXT NOT NULL DEFAULT 'medium'
);

INSERT INTO token_usage_records_new
SELECT
    token_usage_id,
    project_id,
    milestone_id,
    task_id,
    process_run_id,
    agent_id,
    skill_id,
    workflow_id,
    hook_id,
    model_id,
    provider,
    input_tokens,
    output_tokens,
    cached_tokens,
    total_tokens,
    CAST(estimated_cost AS NUMERIC) AS estimated_cost,
    purpose,
    created_at,
    source_refs_json,
    evidence_refs_json,
    adapter_id,
    billing_mode,
    token_visibility,
    cost_visibility,
    usage_source,
    cost_source,
    accounting_confidence
FROM token_usage_records;

DROP TABLE token_usage_records;
ALTER TABLE token_usage_records_new RENAME TO token_usage_records;

-- ── Part 2: ai_usage_operational_records.cost_amount ────────────────────────

CREATE TABLE IF NOT EXISTS ai_usage_operational_records_new (
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
        'subscription_plan', 'plan_allowance', 'token_metered', 'api_metered',
        'credit_metered', 'enterprise_contract', 'unknown', 'unavailable'
    )),
    CHECK (token_visibility IN ('exact', 'partial', 'estimated', 'unavailable')),
    CHECK (cost_visibility IN (
        'exact', 'provider_reported', 'estimated', 'allocated_subscription_cost',
        'unavailable', 'unknown'
    )),
    CHECK (usage_source IN (
        'provider_metadata', 'provider_usage_export', 'local_telemetry',
        'plan_usage_panel', 'manual_config', 'unavailable'
    )),
    CHECK (cost_source IN (
        'provider_metadata', 'provider_usage_export', 'billing_api',
        'plan_allocation_config', 'local_estimate', 'unavailable', 'unknown'
    )),
    CHECK (confidence IN ('high', 'medium', 'low', 'unknown')),
    CHECK (success IN (0, 1) OR success IS NULL),
    CHECK (rework_needed IN (0, 1) OR rework_needed IS NULL),
    FOREIGN KEY (adapter_id) REFERENCES adapter_authority_profiles(adapter_id),
    FOREIGN KEY (accounting_profile_id)
        REFERENCES ai_adapter_accounting_profiles(profile_id),
    FOREIGN KEY (token_usage_id) REFERENCES token_usage_records(token_usage_id)
);

INSERT INTO ai_usage_operational_records_new
SELECT
    usage_record_id,
    project_id,
    milestone_id,
    task_id,
    work_order_id,
    process_run_id,
    adapter_id,
    provider,
    model_id,
    accounting_profile_id,
    token_usage_id,
    billing_mode,
    token_visibility,
    cost_visibility,
    usage_source,
    cost_source,
    confidence,
    input_tokens,
    output_tokens,
    cached_tokens,
    total_tokens,
    CAST(cost_amount AS NUMERIC) AS cost_amount,
    cost_currency,
    run_count,
    files_touched_json,
    commands_run_json,
    validation_result,
    pr_result_outcome,
    success,
    failure_reason,
    rework_needed,
    security_findings_json,
    readiness_findings_json,
    duration_ms,
    source_refs_json,
    evidence_refs_json,
    created_at
FROM ai_usage_operational_records;

DROP TABLE ai_usage_operational_records;
ALTER TABLE ai_usage_operational_records_new RENAME TO ai_usage_operational_records;

PRAGMA legacy_alter_table = OFF;
PRAGMA foreign_keys = ON;
