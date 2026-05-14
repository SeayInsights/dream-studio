-- Migration 024: Audit Run Tracking
-- Created: 2026-05-06
-- Purpose: Track security scans, code quality audits, performance checks, and compliance reviews
-- Links: activity_log (hub) → audit_runs (spoke)
-- Enables: Linking all audit types to tasks/PRDs, trending findings over time, audit impact analysis

-- Enable foreign key enforcement
PRAGMA foreign_keys = ON;

-- ============================================================================
-- AUDIT RUNS TABLE
-- ============================================================================

-- Tracks audit executions across all types (security, quality, performance, architecture, compliance)
CREATE TABLE IF NOT EXISTS audit_runs (
    audit_id TEXT PRIMARY KEY,  -- e.g., 'AUDIT-SEC-20260506-001', 'AUDIT-QUAL-20260506-002'
    activity_id INTEGER,  -- FK to activity_log (hub) - nullable for standalone audits

    -- Audit classification
    audit_type TEXT NOT NULL CHECK(audit_type IN ('code_quality', 'security', 'performance', 'architecture', 'compliance')),
    audit_scope TEXT NOT NULL CHECK(audit_scope IN ('project', 'prd', 'task', 'skill', 'file', 'function')),

    -- Target identification (what was audited)
    target_id TEXT NOT NULL,  -- e.g., 'dream-studio', 'PRD-001', 'T-042', 'core.py'
    target_type TEXT NOT NULL CHECK(target_type IN ('project', 'prd', 'task', 'skill', 'file', 'function', 'module')),

    -- Execution status
    status TEXT NOT NULL CHECK(status IN ('running', 'completed', 'failed', 'cancelled')) DEFAULT 'running',

    -- Finding counts by severity
    findings_count INTEGER DEFAULT 0,
    critical_count INTEGER DEFAULT 0,
    high_count INTEGER DEFAULT 0,
    medium_count INTEGER DEFAULT 0,
    low_count INTEGER DEFAULT 0,

    -- Results and reporting
    report_path TEXT,  -- Path to detailed report file (e.g., '.dream-studio/reports/audit/AUDIT-SEC-20260506-001.md')
    summary TEXT,  -- Brief summary of findings (e.g., "3 critical XSS vulnerabilities, 5 missing input validations")

    -- Timing
    started_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),  -- ISO8601
    completed_at TEXT,  -- ISO8601, nullable until completed
    duration_s REAL,  -- Duration in seconds, calculated on completion

    -- Foreign key: SET NULL when activity is removed (audit records preserved)
    FOREIGN KEY (activity_id) REFERENCES activity_log(activity_id) ON DELETE SET NULL
);

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

-- Index for queries filtering by target (e.g., "show all audits for PRD-001")
CREATE INDEX IF NOT EXISTS idx_audit_target
ON audit_runs(target_id, target_type);

-- Index for queries filtering by audit type and status (e.g., "show running security audits")
CREATE INDEX IF NOT EXISTS idx_audit_type_status
ON audit_runs(audit_type, status);

-- Index for time-series queries (most recent audits first)
CREATE INDEX IF NOT EXISTS idx_audit_started
ON audit_runs(started_at DESC);

-- Index for finding high-severity audits across all types
CREATE INDEX IF NOT EXISTS idx_audit_severity
ON audit_runs(critical_count DESC, high_count DESC)
WHERE status = 'completed';
