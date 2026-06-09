-- Migration 019: Security Findings Tracking (Spoke Tables)
-- Created: 2026-05-06
-- Purpose: Track security scan results, manual reviews, CVEs, and hook checks, linked to activity_log hub
-- Links: activity_log (hub) → sec_sarif_findings + sec_manual_reviews + sec_cve_matches + sec_hook_checks (spokes)
-- Enables: Vuln tracking, deduplication, remediation workflows, and compliance reporting

PRAGMA foreign_keys = ON;

-- ============================================================================
-- SARIF FINDINGS
-- ============================================================================

-- Tracks security findings from SARIF-compliant tools (Semgrep, Bandit, etc.)
CREATE TABLE IF NOT EXISTS sec_sarif_findings (
    sarif_finding_id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER NOT NULL,  -- FK to activity_log (hub)
    scan_tool TEXT NOT NULL,  -- 'semgrep', 'bandit', 'trivy', etc.
    rule_id TEXT NOT NULL,  -- Tool-specific rule identifier
    rule_name TEXT,
    severity TEXT CHECK(severity IN ('critical', 'high', 'medium', 'low', 'info')),
    file_path TEXT NOT NULL,
    line_number INTEGER,
    message TEXT NOT NULL,
    cwe_ids TEXT,  -- JSON array: ["CWE-79", "CWE-89"]
    cvss_score REAL,
    status TEXT CHECK(status IN ('open', 'mitigated', 'false_positive', 'accepted')) DEFAULT 'open',
    mitigated_at TEXT,  -- ISO8601 timestamp
    mitigation_task_id TEXT,  -- FK to prd_tasks (nullable - not all findings need tasks)
    created_at TEXT DEFAULT (datetime('now')),

    -- Foreign key: cascade delete when activity is removed
    FOREIGN KEY (activity_id) REFERENCES activity_log(activity_id) ON DELETE CASCADE,
    FOREIGN KEY (mitigation_task_id) REFERENCES prd_tasks(task_id) ON DELETE SET NULL
);

-- ============================================================================
-- MANUAL REVIEWS
-- ============================================================================

-- Tracks manual security/code/architecture reviews
CREATE TABLE IF NOT EXISTS sec_manual_reviews (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER NOT NULL,  -- FK to activity_log (hub)
    reviewer TEXT NOT NULL,  -- Name or identifier of the reviewer
    review_type TEXT CHECK(review_type IN ('code_review', 'architecture_review', 'security_review')),
    findings TEXT,  -- Markdown or JSON blob
    risk_level TEXT CHECK(risk_level IN ('critical', 'high', 'medium', 'low')),
    recommendations TEXT,
    status TEXT CHECK(status IN ('draft', 'published', 'closed')) DEFAULT 'draft',
    created_at TEXT DEFAULT (datetime('now')),

    -- Foreign key: cascade delete when activity is removed
    FOREIGN KEY (activity_id) REFERENCES activity_log(activity_id) ON DELETE CASCADE
);

-- ============================================================================
-- CVE MATCHES
-- ============================================================================

-- Tracks CVE matches from dependency scanners (npm audit, pip-audit, Trivy, etc.)
CREATE TABLE IF NOT EXISTS sec_cve_matches (
    cve_match_id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER NOT NULL,  -- FK to activity_log (hub)
    cve_id TEXT NOT NULL,  -- e.g., 'CVE-2024-1234'
    package_name TEXT NOT NULL,
    package_version TEXT NOT NULL,
    severity TEXT CHECK(severity IN ('critical', 'high', 'medium', 'low')),
    cvss_score REAL,
    description TEXT,
    fixed_version TEXT,  -- Nullable - might not have a fix yet
    status TEXT CHECK(status IN ('vulnerable', 'patched', 'mitigated')) DEFAULT 'vulnerable',
    patched_at TEXT,  -- ISO8601 timestamp (nullable)
    created_at TEXT DEFAULT (datetime('now')),

    -- Foreign key: cascade delete when activity is removed
    FOREIGN KEY (activity_id) REFERENCES activity_log(activity_id) ON DELETE CASCADE
);

-- ============================================================================
-- HOOK SECURITY CHECKS
-- ============================================================================

-- Tracks security checks performed by hooks (credentials check, permissions check, etc.)
CREATE TABLE IF NOT EXISTS sec_hook_checks (
    hook_check_id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER NOT NULL,  -- FK to activity_log (hub)
    hook_exec_id INTEGER NOT NULL,  -- FK to hook_executions
    check_type TEXT CHECK(check_type IN ('credentials_check', 'permissions_check', 'config_check')),
    check_result TEXT CHECK(check_result IN ('pass', 'fail', 'warning')),
    details TEXT,  -- JSON blob: what was checked, specific findings
    remediation TEXT,  -- Nullable - suggestions for fixing failures/warnings
    created_at TEXT DEFAULT (datetime('now')),

    -- Foreign keys: cascade delete when activity or execution is removed
    FOREIGN KEY (activity_id) REFERENCES activity_log(activity_id) ON DELETE CASCADE,
    FOREIGN KEY (hook_exec_id) REFERENCES hook_executions(hook_exec_id) ON DELETE CASCADE
);

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

-- SARIF Findings Indexes

-- Index for queries filtering by activity (e.g., "show all findings for task T001")
CREATE INDEX IF NOT EXISTS idx_sarif_activity
ON sec_sarif_findings(activity_id);

-- Index for queries filtering by status (e.g., "show open findings")
CREATE INDEX IF NOT EXISTS idx_sarif_status
ON sec_sarif_findings(status);

-- Index for queries filtering by severity (e.g., "show critical findings")
CREATE INDEX IF NOT EXISTS idx_sarif_severity
ON sec_sarif_findings(severity);

-- Composite index for deduplication (same rule + file + line = duplicate finding)
CREATE INDEX IF NOT EXISTS idx_sarif_rule_file
ON sec_sarif_findings(rule_id, file_path, line_number);

-- Manual Reviews Indexes

-- Index for queries filtering by activity
CREATE INDEX IF NOT EXISTS idx_review_activity
ON sec_manual_reviews(activity_id);

-- Index for queries filtering by status (e.g., "show published reviews")
CREATE INDEX IF NOT EXISTS idx_review_status
ON sec_manual_reviews(status);

-- Index for queries filtering by risk level (e.g., "show critical reviews")
CREATE INDEX IF NOT EXISTS idx_review_risk
ON sec_manual_reviews(risk_level);

-- CVE Matches Indexes

-- Index for queries filtering by activity
CREATE INDEX IF NOT EXISTS idx_cve_activity
ON sec_cve_matches(activity_id);

-- Index for queries filtering by status (e.g., "show vulnerable packages")
CREATE INDEX IF NOT EXISTS idx_cve_status
ON sec_cve_matches(status);

-- Index for queries filtering by severity (e.g., "show critical CVEs")
CREATE INDEX IF NOT EXISTS idx_cve_severity
ON sec_cve_matches(severity);

-- Composite index for package lookups (e.g., "show all CVEs for lodash@4.17.20")
CREATE INDEX IF NOT EXISTS idx_cve_package
ON sec_cve_matches(package_name, package_version);

-- Hook Checks Indexes

-- Index for queries filtering by activity
CREATE INDEX IF NOT EXISTS idx_hook_check_activity
ON sec_hook_checks(activity_id);

-- Index for queries filtering by hook execution
CREATE INDEX IF NOT EXISTS idx_hook_check_exec
ON sec_hook_checks(hook_exec_id);

-- Index for queries filtering by check result (e.g., "show failed checks")
CREATE INDEX IF NOT EXISTS idx_hook_check_result
ON sec_hook_checks(check_result);
