-- Migration 012: PRD Schema Refactor
-- Created: 2026-05-05
-- Purpose: Add proper relational schema for PRD tracking (FR-009 from unified-discovery spec)
-- Replaces: Text-based plan_path in raw_handoffs with relational PRD tracking

-- ============================================================================
-- PRD TRACKING SCHEMA
-- ============================================================================

-- 1. PRD Documents (top-level entity)
CREATE TABLE IF NOT EXISTS prd_documents (
    prd_id TEXT PRIMARY KEY,              -- e.g., "unified-discovery"
    title TEXT NOT NULL,                  -- "Unified Discovery System"
    file_path TEXT NOT NULL,              -- "prd/unified-discovery/spec.md" (relative to .dream-studio/)
    status TEXT NOT NULL,                 -- draft | approved | in-progress | completed | abandoned
    project_id TEXT,                      -- Optional link to reg_projects
    created_at TEXT NOT NULL,
    approved_at TEXT,                     -- When Director approved
    completed_at TEXT,                    -- When last task shipped
    total_tasks INTEGER DEFAULT 0,
    completed_tasks INTEGER DEFAULT 0
);

-- 2. PRD Plans (implementation plans)
CREATE TABLE IF NOT EXISTS prd_plans (
    plan_id TEXT PRIMARY KEY,            -- e.g., "unified-discovery-phase4"
    prd_id TEXT NOT NULL,
    phase_name TEXT,                     -- "Phase 4: Discovery & Integration"
    file_path TEXT,                      -- "prd/unified-discovery/plan.md" (relative)
    created_at TEXT NOT NULL,
    FOREIGN KEY (prd_id) REFERENCES prd_documents(prd_id) ON DELETE CASCADE
);

-- 3. PRD Tasks (atomic work units)
CREATE TABLE IF NOT EXISTS prd_tasks (
    task_id TEXT PRIMARY KEY,            -- "T001", "T002", etc.
    plan_id TEXT NOT NULL,
    prd_id TEXT NOT NULL,                -- Denormalized for fast queries
    wave_id TEXT,                        -- Optional link to pi_waves
    task_name TEXT NOT NULL,             -- "Database migration"
    description TEXT,
    acceptance_criteria TEXT,            -- JSON array
    depends_on TEXT,                     -- JSON array of task_ids: ["T001", "T002"]
    status TEXT NOT NULL DEFAULT 'pending', -- pending | in_progress | completed | blocked
    phase TEXT,                          -- "Phase 4: Discovery"
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (plan_id) REFERENCES prd_plans(plan_id) ON DELETE CASCADE,
    FOREIGN KEY (prd_id) REFERENCES prd_documents(prd_id) ON DELETE CASCADE
);

-- 4. PRD Sessions (work sessions)
CREATE TABLE IF NOT EXISTS prd_sessions (
    session_id TEXT PRIMARY KEY,
    prd_id TEXT NOT NULL,
    plan_id TEXT,
    current_task_id TEXT,
    current_wave_id TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    context_kb REAL,
    FOREIGN KEY (prd_id) REFERENCES prd_documents(prd_id) ON DELETE CASCADE,
    FOREIGN KEY (plan_id) REFERENCES prd_plans(plan_id) ON DELETE SET NULL,
    FOREIGN KEY (current_task_id) REFERENCES prd_tasks(task_id) ON DELETE SET NULL
);

-- 5. Session-Task junction (many-to-many)
CREATE TABLE IF NOT EXISTS session_tasks (
    session_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    PRIMARY KEY (session_id, task_id),
    FOREIGN KEY (session_id) REFERENCES prd_sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (task_id) REFERENCES prd_tasks(task_id) ON DELETE CASCADE
);

-- 6. PRD Handoffs (refactored from raw_handoffs)
CREATE TABLE IF NOT EXISTS prd_handoffs (
    handoff_id INTEGER PRIMARY KEY AUTOINCREMENT,
    prd_id TEXT NOT NULL,
    session_id TEXT,
    current_task_id TEXT,
    current_wave_id TEXT,
    working TEXT,                        -- JSON array: ["PRD written", "Schema designed"]
    broken TEXT,                         -- JSON array: []
    pending_decisions TEXT,              -- JSON array: [{"decision": "...", "context": "..."}]
    next_action TEXT,
    lessons_json TEXT,                   -- JSON array
    created_at TEXT NOT NULL,
    FOREIGN KEY (prd_id) REFERENCES prd_documents(prd_id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES prd_sessions(session_id) ON DELETE SET NULL,
    FOREIGN KEY (current_task_id) REFERENCES prd_tasks(task_id) ON DELETE SET NULL
);

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_prd_status ON prd_documents(status);
CREATE INDEX IF NOT EXISTS idx_prd_project ON prd_documents(project_id);
CREATE INDEX IF NOT EXISTS idx_prd_created ON prd_documents(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_plan_prd ON prd_plans(prd_id);

CREATE INDEX IF NOT EXISTS idx_task_prd ON prd_tasks(prd_id);
CREATE INDEX IF NOT EXISTS idx_task_status ON prd_tasks(status);
CREATE INDEX IF NOT EXISTS idx_task_wave ON prd_tasks(wave_id);
CREATE INDEX IF NOT EXISTS idx_task_plan ON prd_tasks(plan_id);

CREATE INDEX IF NOT EXISTS idx_session_prd ON prd_sessions(prd_id);
CREATE INDEX IF NOT EXISTS idx_session_started ON prd_sessions(started_at DESC);

CREATE INDEX IF NOT EXISTS idx_handoff_prd ON prd_handoffs(prd_id);
CREATE INDEX IF NOT EXISTS idx_handoff_created ON prd_handoffs(created_at DESC);

-- ============================================================================
-- VIEWS FOR COMMON QUERIES
-- ============================================================================

-- View: PRD Progress Summary
CREATE VIEW IF NOT EXISTS vw_prd_progress AS
SELECT
    p.prd_id,
    p.title,
    p.status,
    p.total_tasks,
    p.completed_tasks,
    ROUND(100.0 * p.completed_tasks / NULLIF(p.total_tasks, 0), 1) AS pct_complete,
    p.created_at,
    p.approved_at,
    p.completed_at,
    (SELECT COUNT(*) FROM prd_handoffs h WHERE h.prd_id = p.prd_id) AS handoff_count,
    (SELECT COUNT(*) FROM prd_sessions s WHERE s.prd_id = p.prd_id) AS session_count
FROM prd_documents p;

-- View: Task Details with PRD Info
CREATE VIEW IF NOT EXISTS vw_task_details AS
SELECT
    t.task_id,
    t.task_name,
    t.description,
    t.status,
    t.phase,
    t.prd_id,
    p.title AS prd_title,
    p.status AS prd_status,
    t.wave_id,
    t.depends_on,
    t.started_at,
    t.completed_at,
    t.created_at
FROM prd_tasks t
JOIN prd_documents p ON t.prd_id = p.prd_id;

-- ============================================================================
-- MIGRATION COMPLETE
-- ============================================================================
-- Next steps:
-- 1. Run data migration script: py scripts/migrate_prd_schema.py
-- 2. Update hooks/lib/context_handoff.py to write to prd_handoffs
-- 3. Update scripts/resume_from_handoff.py to read from prd_handoffs
