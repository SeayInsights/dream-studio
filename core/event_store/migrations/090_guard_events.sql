-- Migration 090: Create guard_events table for runtime LLM guard operational telemetry.
--
-- Boundary with findings table:
--   findings — scan-time observations on files (rule fired on code, advisory result).
--             Written by on-skill-input hook per file match.
--   guard_events — runtime action decisions (memory skipped, injection logged, block
--                  decisions). Operational telemetry distinct from scan-findings.
--
-- Same project_id foreign key as findings; both queryable per project.
-- skill_scan_runs.scan_id links guard_events back to the scan that triggered them.

CREATE TABLE IF NOT EXISTS guard_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,          -- 'guard_finding_logged' | 'memory_skipped_tainted' | 'guard_candidate_logged'
    rule_id TEXT,                      -- guard-NNN, or NULL for memory events
    severity TEXT,                     -- critical | high | medium | low | NULL
    source_type TEXT NOT NULL,         -- 'repo_file' | 'memory_entry' | 'prompt' | 'output'
    source_id TEXT,                    -- file path, memory_id, etc.
    project_id TEXT,                   -- FK to business_projects.project_id
    scan_id TEXT,                      -- FK to scan_runs.scan_id (nullable for memory events)
    action TEXT NOT NULL DEFAULT 'logged',  -- 'logged' | 'sanitized' | 'blocked' | 'skipped'
    confidence REAL,                   -- 0.0–1.0 from pattern risk_weight
    details TEXT NOT NULL DEFAULT '{}', -- JSON with matched_text, description, etc.
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

CREATE INDEX IF NOT EXISTS idx_guard_events_project
ON guard_events(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_guard_events_type
ON guard_events(event_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_guard_events_scan
ON guard_events(scan_id) WHERE scan_id IS NOT NULL;
