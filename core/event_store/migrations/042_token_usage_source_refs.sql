-- Migration 042: Token usage source references
-- Preserves source/evidence provenance for reconciled legacy token usage rows.

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
ADD COLUMN source_refs_json TEXT NOT NULL DEFAULT '[]';

ALTER TABLE token_usage_records
ADD COLUMN evidence_refs_json TEXT NOT NULL DEFAULT '[]';
