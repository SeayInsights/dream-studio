-- Migration 085: Brownfield intake — stack profile + security scan baseline tracking
--
-- Adds two capabilities needed for the brownfield vertical slice (18.x):
--
-- 1. Stack profile columns on business_projects:
--    detected_stack (string identifier: "nextjs", "python", "go", "rust", etc.)
--    stack_json (full detection signal dump for auditing)
--    These were previously on reg_projects (deleted in migration 084), but never
--    successfully written because engine.py's project_source INSERT was broken.
--    Now they land on the canonical project authority.
--
-- 2. security_scan_runs — baseline/delta tracking for security findings:
--    Every scan gets a scan_id. The first scan on a project is is_baseline=1.
--    Subsequent scans can compute delta by comparing against the baseline scan_id.
--    security_findings.scan_id already exists (migration 037) — this table makes
--    the scan metadata queryable and the baseline concept explicit.

-- ── 1. Stack profile on business_projects ─────────────────────────────────────

ALTER TABLE business_projects ADD COLUMN detected_stack TEXT;
ALTER TABLE business_projects ADD COLUMN stack_json TEXT;

CREATE INDEX IF NOT EXISTS idx_business_projects_stack
ON business_projects(detected_stack);

-- ── 2. Security scan runs (baseline/delta) ────────────────────────────────────

CREATE TABLE IF NOT EXISTS security_scan_runs (
    scan_id      TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL REFERENCES business_projects(project_id),
    is_baseline  INTEGER NOT NULL DEFAULT 0 CHECK(is_baseline IN (0, 1)),
    scope        TEXT NOT NULL DEFAULT 'full_repo',  -- full_repo | changed | sample
    target_path  TEXT,
    tool_versions_json TEXT NOT NULL DEFAULT '{}',   -- {"gitleaks": "8.x", "bandit": "1.x", ...}
    findings_count    INTEGER NOT NULL DEFAULT 0,
    critical_count    INTEGER NOT NULL DEFAULT 0,
    high_count        INTEGER NOT NULL DEFAULT 0,
    medium_count      INTEGER NOT NULL DEFAULT 0,
    low_count         INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'running'
                      CHECK(status IN ('running', 'completed', 'failed')),
    started_at   TEXT NOT NULL,
    completed_at TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now','utc'))
);

CREATE INDEX IF NOT EXISTS idx_security_scan_runs_project
ON security_scan_runs(project_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_security_scan_runs_baseline
ON security_scan_runs(project_id, is_baseline);
