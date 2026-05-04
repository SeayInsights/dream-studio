-- Migration 008: Research caching and wave execution tracking

-- ── Research cache with trust scoring ───────────────────────────────────────

CREATE TABLE IF NOT EXISTS raw_research (
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
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    ttl_days INTEGER DEFAULT 30,
    expires_at TEXT,
    CONSTRAINT chk_confidence_range CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    CONSTRAINT chk_trust_range CHECK (trust_score >= 0.0 AND trust_score <= 1.0),
    CONSTRAINT chk_success_rate_range CHECK (success_rate >= 0.0 AND success_rate <= 1.0),
    CONSTRAINT chk_validation_status CHECK (validation_status IN ('pending', 'validated', 'rejected')),
    CONSTRAINT chk_source_type CHECK (source_type IN ('stack', 'security', 'docs', 'pattern', 'general'))
);

-- ── Research source reliability tracking ────────────────────────────────────

CREATE TABLE IF NOT EXISTS reg_research_sources (
    source_url TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    trust_score REAL DEFAULT 0.5,
    total_queries INTEGER DEFAULT 0,
    successful_queries INTEGER DEFAULT 0,
    failed_queries INTEGER DEFAULT 0,
    avg_validation_time REAL,
    last_used TEXT,
    first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_source_trust_range CHECK (trust_score >= 0.0 AND trust_score <= 1.0),
    CONSTRAINT chk_source_type CHECK (source_type IN ('stack', 'security', 'docs', 'pattern', 'general'))
);

-- ── Wave execution tracking ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pi_waves (
    wave_id TEXT PRIMARY KEY,
    project_id TEXT,
    session_id TEXT NOT NULL,
    wave_number INTEGER NOT NULL,
    wave_name TEXT NOT NULL,
    description TEXT,
    depends_on_wave_id TEXT,
    status TEXT DEFAULT 'pending',
    started_at TEXT,
    completed_at TEXT,
    duration_seconds REAL,
    tasks_total INTEGER DEFAULT 0,
    tasks_completed INTEGER DEFAULT 0,
    tasks_failed INTEGER DEFAULT 0,
    success_rate REAL,
    CONSTRAINT chk_wave_status CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    CONSTRAINT chk_wave_success_rate CHECK (success_rate IS NULL OR (success_rate >= 0.0 AND success_rate <= 1.0)),
    FOREIGN KEY (depends_on_wave_id) REFERENCES pi_waves(wave_id)
);

-- ── Individual task tracking within waves ────────────────────────────────────

CREATE TABLE IF NOT EXISTS pi_wave_tasks (
    wave_task_id TEXT PRIMARY KEY,
    wave_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    task_number INTEGER NOT NULL,
    parallel_group INTEGER DEFAULT 1,
    estimated_hours REAL,
    actual_hours REAL,
    started_at TEXT,
    completed_at TEXT,
    status TEXT DEFAULT 'pending',
    CONSTRAINT chk_task_status CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    FOREIGN KEY (wave_id) REFERENCES pi_waves(wave_id)
);

-- ── Auto-adjust source trust on validation outcome ───────────────────────────

CREATE TRIGGER IF NOT EXISTS trg_update_source_trust
AFTER UPDATE OF validation_status ON raw_research
WHEN old.validation_status != new.validation_status AND new.source_url IS NOT NULL
BEGIN
    -- Update trust score based on validation outcome
    UPDATE reg_research_sources
    SET trust_score = CASE
        WHEN new.validation_status = 'validated' THEN MIN(trust_score + 0.1, 1.0)
        WHEN new.validation_status = 'rejected' THEN MAX(trust_score - 0.2, 0.0)
        ELSE trust_score
    END,
    total_queries = total_queries + 1,
    successful_queries = CASE
        WHEN new.validation_status = 'validated' THEN successful_queries + 1
        ELSE successful_queries
    END,
    failed_queries = CASE
        WHEN new.validation_status = 'rejected' THEN failed_queries + 1
        ELSE failed_queries
    END,
    last_used = datetime('now')
    WHERE source_url = new.source_url;

    -- Insert source if it doesn't exist
    INSERT OR IGNORE INTO reg_research_sources (source_url, source_type, trust_score, total_queries, successful_queries, failed_queries, last_used)
    VALUES (
        new.source_url,
        new.source_type,
        CASE WHEN new.validation_status = 'validated' THEN 0.6 ELSE 0.3 END,
        1,
        CASE WHEN new.validation_status = 'validated' THEN 1 ELSE 0 END,
        CASE WHEN new.validation_status = 'rejected' THEN 1 ELSE 0 END,
        datetime('now')
    );
END;

-- ── Indexes for query performance ────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_research_query_hash ON raw_research(query_hash);
CREATE INDEX IF NOT EXISTS idx_research_expires ON raw_research(expires_at);
CREATE INDEX IF NOT EXISTS idx_research_validation ON raw_research(validation_status);
CREATE INDEX IF NOT EXISTS idx_wave_session ON pi_waves(session_id);
CREATE INDEX IF NOT EXISTS idx_wave_tasks_wave ON pi_wave_tasks(wave_id);
CREATE INDEX IF NOT EXISTS idx_wave_tasks_status ON pi_wave_tasks(status);
