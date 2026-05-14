-- Migration 022: Guardrail metadata tables
-- Created: 2026-05-06
-- Purpose: Support guardrail engine audit trail and rule tracking
-- Part of: Track A (Data Plane) - event-driven refactor

-- Table: guardrail_decisions
-- Stores audit trail of all guardrail evaluations (allow/block/require_approval)
CREATE TABLE IF NOT EXISTS guardrail_decisions (
    decision_id TEXT PRIMARY KEY,
    rule_id TEXT NOT NULL,
    event_id TEXT,
    action TEXT NOT NULL CHECK (action IN ('allow', 'block', 'require_approval', 'advisory')),
    message TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    metadata TEXT
);

-- Table: guardrail_rules_audit
-- Tracks when rules are loaded/modified from YAML files
CREATE TABLE IF NOT EXISTS guardrail_rules_audit (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id TEXT NOT NULL,
    loaded_at TEXT NOT NULL,
    file_path TEXT NOT NULL,
    rule_hash TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1))
);

-- Indexes for guardrail_decisions
CREATE INDEX IF NOT EXISTS idx_guardrail_decisions_rule_id ON guardrail_decisions(rule_id);
CREATE INDEX IF NOT EXISTS idx_guardrail_decisions_evaluated_at ON guardrail_decisions(evaluated_at);
CREATE INDEX IF NOT EXISTS idx_guardrail_decisions_action ON guardrail_decisions(action);

-- Indexes for guardrail_rules_audit
CREATE INDEX IF NOT EXISTS idx_guardrail_rules_audit_rule_id ON guardrail_rules_audit(rule_id);
