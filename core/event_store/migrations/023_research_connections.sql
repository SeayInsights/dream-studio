-- Migration 022: Research Connections (Phase 3 Cross-Domain Traceability)
-- Created: 2026-05-06
-- Purpose: Add FK columns to link research to activity_log, PRDs, and tasks
-- Links: research_cache + raw_research → activity_log + prd_documents + prd_tasks
-- Enables: Complete research audit trail, cross-domain impact analysis, research-to-task traceability

PRAGMA foreign_keys = ON;

-- ============================================================================
-- ALTER research_cache: Add FK columns
-- ============================================================================

-- Add activity_id FK to research_cache
ALTER TABLE research_cache
ADD COLUMN activity_id INTEGER;

-- Add prd_id FK to research_cache
ALTER TABLE research_cache
ADD COLUMN prd_id TEXT;

-- Add task_id FK to research_cache
ALTER TABLE research_cache
ADD COLUMN task_id TEXT;

-- ============================================================================
-- ALTER raw_research: Add FK columns
-- ============================================================================

-- Add activity_id FK to raw_research
ALTER TABLE raw_research
ADD COLUMN activity_id INTEGER;

-- Add prd_id FK to raw_research
ALTER TABLE raw_research
ADD COLUMN prd_id TEXT;

-- Add task_id FK to raw_research
ALTER TABLE raw_research
ADD COLUMN task_id TEXT;

-- ============================================================================
-- FOREIGN KEY CONSTRAINTS
-- ============================================================================

-- Constraints for research_cache
CREATE TABLE research_cache_temp AS SELECT * FROM research_cache;

DROP TABLE research_cache;

CREATE TABLE research_cache (
    cache_id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    focus_areas TEXT,                      -- JSON array
    sources TEXT,                          -- JSON array of {url, title, summary, tier}
    findings TEXT,                         -- Markdown summary
    confidence_score REAL,                 -- 0.0-1.0
    triangulation_score REAL,              -- 0.0-1.0 (based on source count)
    activity_id INTEGER,
    prd_id TEXT,
    task_id TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    expires_at TEXT,                        -- datetime('now', '+30 days')

    -- Foreign keys: SET NULL on delete to preserve research history
    FOREIGN KEY (activity_id) REFERENCES activity_log(activity_id) ON DELETE SET NULL,
    FOREIGN KEY (prd_id) REFERENCES prd_documents(prd_id) ON DELETE SET NULL,
    FOREIGN KEY (task_id) REFERENCES prd_tasks(task_id) ON DELETE SET NULL
);

INSERT INTO research_cache
SELECT * FROM research_cache_temp;

DROP TABLE research_cache_temp;

-- Constraints for raw_research
CREATE TABLE raw_research_temp AS SELECT * FROM raw_research;

DROP TABLE raw_research;

CREATE TABLE raw_research (
    research_id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    query_hash TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_url TEXT,
    findings TEXT NOT NULL,
    confidence_score REAL DEFAULT 0.5,
    trust_score REAL DEFAULT 0.5,
    validation_status TEXT DEFAULT 'pending',
    validated_by TEXT,
    validated_at TEXT,
    times_referenced INTEGER DEFAULT 0,
    success_rate REAL DEFAULT 0.5,
    activity_id INTEGER,
    prd_id TEXT,
    task_id TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    ttl_days INTEGER DEFAULT 30,
    expires_at TEXT,
    CONSTRAINT chk_confidence_range CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    CONSTRAINT chk_trust_range CHECK (trust_score >= 0.0 AND trust_score <= 1.0),
    CONSTRAINT chk_success_rate_range CHECK (success_rate >= 0.0 AND success_rate <= 1.0),
    CONSTRAINT chk_validation_status CHECK (validation_status IN ('pending', 'validated', 'rejected')),
    CONSTRAINT chk_source_type CHECK (source_type IN ('stack', 'security', 'docs', 'pattern', 'general')),

    -- Foreign keys: SET NULL on delete to preserve research history
    FOREIGN KEY (activity_id) REFERENCES activity_log(activity_id) ON DELETE SET NULL,
    FOREIGN KEY (prd_id) REFERENCES prd_documents(prd_id) ON DELETE SET NULL,
    FOREIGN KEY (task_id) REFERENCES prd_tasks(task_id) ON DELETE SET NULL
);

INSERT INTO raw_research
SELECT * FROM raw_research_temp;

DROP TABLE raw_research_temp;

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

-- research_cache indexes
CREATE INDEX IF NOT EXISTS idx_research_cache_task
ON research_cache(task_id);

CREATE INDEX IF NOT EXISTS idx_research_cache_prd
ON research_cache(prd_id);

CREATE INDEX IF NOT EXISTS idx_research_cache_activity
ON research_cache(activity_id);

-- raw_research indexes
CREATE INDEX IF NOT EXISTS idx_raw_research_task
ON raw_research(task_id);

CREATE INDEX IF NOT EXISTS idx_raw_research_prd
ON raw_research(prd_id);

CREATE INDEX IF NOT EXISTS idx_raw_research_activity
ON raw_research(activity_id);
