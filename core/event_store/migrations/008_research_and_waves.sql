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

-- reg_research_sources removed in migration 128 (dead table; no live consumer)

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

-- trg_update_source_trust removed in migration 128: its target reg_research_sources is dropped.

-- ── Indexes for query performance ────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_research_query_hash ON raw_research(query_hash);
CREATE INDEX IF NOT EXISTS idx_research_expires ON raw_research(expires_at);
CREATE INDEX IF NOT EXISTS idx_research_validation ON raw_research(validation_status);
CREATE INDEX IF NOT EXISTS idx_wave_session ON pi_waves(session_id);
CREATE INDEX IF NOT EXISTS idx_wave_tasks_wave ON pi_wave_tasks(wave_id);
CREATE INDEX IF NOT EXISTS idx_wave_tasks_status ON pi_wave_tasks(status);
