-- Migration 113: Brownfield onboarding additions (WO-W).
--
-- 1. vision_statement on business_projects (AD-10): captures intended vision per
--    project directly on the entity rather than in a prd_* table (prd_* retired).
--
-- 2. pending_audits: scheduling table for deferred readiness audits. Orthogonal to
--    the security_events/readiness_events findings spines — this tracks SCHEDULING,
--    not findings content. Populated via emit->business_canonical_events (AD-6);
--    projected by PendingAuditProjection. Surfaced at project activation / WO start.

-- 1. Add vision_statement to business_projects (no-op if column exists)
ALTER TABLE business_projects ADD COLUMN vision_statement TEXT;

-- 2. pending_audits read-model (scheduling layer, not findings spine)
CREATE TABLE IF NOT EXISTS pending_audits (
    audit_id        TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES business_projects(project_id),
    audit_type      TEXT NOT NULL CHECK (audit_type IN ('security', 'readiness', 'stack', 'custom')),
    status          TEXT NOT NULL DEFAULT 'deferred'
                        CHECK (status IN ('deferred', 'scheduled', 'running', 'complete', 'cancelled')),
    correlation_id  TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    scheduled_at    TEXT,
    completed_at    TEXT,
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_pending_audits_project_status
    ON pending_audits (project_id, status);
