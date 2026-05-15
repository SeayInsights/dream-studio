-- Migration 045: Task Attribution And Execution Outcome Authority
-- Created: 2026-05-15
-- Purpose:
--   Additive authority for meaningful AI/adapter execution units so dashboard,
--   Work Orders, Project Details, Adapter Usage, Capability Center, and
--   security/readiness views can explain who did what work and what happened.

CREATE TABLE IF NOT EXISTS task_attribution_records (
    attribution_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    work_order_id TEXT,
    process_run_id TEXT,
    event_id TEXT,
    adapter_id TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'unknown',
    model_id TEXT NOT NULL DEFAULT 'unknown',
    model_visibility TEXT NOT NULL DEFAULT 'unknown',
    agent_id TEXT,
    skill_ids_json TEXT NOT NULL DEFAULT '[]',
    workflow_ids_json TEXT NOT NULL DEFAULT '[]',
    hook_ids_json TEXT NOT NULL DEFAULT '[]',
    tool_ids_json TEXT NOT NULL DEFAULT '[]',
    files_touched_json TEXT NOT NULL DEFAULT '[]',
    files_touched_status TEXT NOT NULL DEFAULT 'unavailable',
    files_touched_unavailable_reason TEXT,
    commands_run_json TEXT NOT NULL DEFAULT '[]',
    commands_run_status TEXT NOT NULL DEFAULT 'unavailable',
    validations_json TEXT NOT NULL DEFAULT '[]',
    validation_status TEXT NOT NULL DEFAULT 'unknown',
    security_impact_json TEXT NOT NULL DEFAULT '{}',
    readiness_impact_json TEXT NOT NULL DEFAULT '{}',
    outcome_status TEXT NOT NULL DEFAULT 'manual_review_required',
    outcome_summary TEXT,
    commit_refs_json TEXT NOT NULL DEFAULT '[]',
    pr_refs_json TEXT NOT NULL DEFAULT '[]',
    result_refs_json TEXT NOT NULL DEFAULT '[]',
    rework_needed INTEGER,
    rework_status TEXT NOT NULL DEFAULT 'unknown',
    ai_usage_record_id TEXT,
    token_usage_id TEXT,
    adapter_result_id TEXT,
    source_class TEXT NOT NULL DEFAULT 'dream_studio_routed',
    confidence TEXT NOT NULL DEFAULT 'unknown',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (model_visibility IN ('exact', 'partial', 'unknown', 'unavailable')),
    CHECK (files_touched_status IN ('available', 'unavailable', 'partial')),
    CHECK (commands_run_status IN ('available', 'unavailable', 'partial')),
    CHECK (validation_status IN ('passed', 'failed', 'partial', 'not_run', 'unknown', 'manual_review_required')),
    CHECK (outcome_status IN (
        'completed',
        'committed',
        'pr_opened',
        'released',
        'partial',
        'failed',
        'manual_review_required',
        'unknown'
    )),
    CHECK (rework_needed IN (0, 1) OR rework_needed IS NULL),
    CHECK (source_class IN (
        'dream_studio_routed',
        'adapter_reported',
        'analytics_ingest',
        'imported_manual',
        'untracked'
    )),
    CHECK (confidence IN ('high', 'medium', 'low', 'unknown'))
);

CREATE INDEX IF NOT EXISTS idx_task_attribution_project
ON task_attribution_records(project_id, milestone_id, task_id, created_at);

CREATE INDEX IF NOT EXISTS idx_task_attribution_work_order
ON task_attribution_records(work_order_id, created_at);

CREATE INDEX IF NOT EXISTS idx_task_attribution_process
ON task_attribution_records(process_run_id, adapter_id, created_at);

CREATE INDEX IF NOT EXISTS idx_task_attribution_adapter
ON task_attribution_records(adapter_id, provider, model_id, outcome_status);

CREATE INDEX IF NOT EXISTS idx_task_attribution_outcome
ON task_attribution_records(outcome_status, validation_status, rework_needed);
