-- Migration 020: Risk Register (Spoke Tables)
-- Created: 2026-05-06
-- Purpose: Track risks and mitigations, linked to activities, PRDs, tasks, and skills
-- Links: activity_log (hub) → risk_register + risk_mitigations (spokes)
-- Enables: Risk scoring, mitigation tracking, and cross-entity risk analysis

-- ============================================================================
-- RISK REGISTER
-- ============================================================================

-- Central risk register tracking risks across all dream-studio entities
CREATE TABLE IF NOT EXISTS risk_register (
    risk_id TEXT PRIMARY KEY,  -- e.g., 'RISK-001', 'RISK-SEC-042'
    activity_id INTEGER,  -- FK to activity_log (hub) - nullable, ON DELETE SET NULL

    -- Risk classification
    risk_type TEXT NOT NULL CHECK(risk_type IN ('technical', 'security', 'operational', 'compliance')),
    risk_category TEXT NOT NULL CHECK(risk_category IN ('data_loss', 'performance', 'vulnerability', 'dependency', 'scope_creep')),

    -- Risk details
    title TEXT NOT NULL,
    description TEXT,

    -- Risk scoring (1-5 scale)
    likelihood INTEGER NOT NULL CHECK(likelihood BETWEEN 1 AND 5),
    impact INTEGER NOT NULL CHECK(impact BETWEEN 1 AND 5),
    risk_score INTEGER NOT NULL CHECK(risk_score BETWEEN 1 AND 25),  -- calculated as likelihood * impact

    -- Entity linkage (all nullable - risks can be project-level or unattached)
    prd_id TEXT,
    task_id TEXT,
    skill_id TEXT,

    -- Status tracking
    status TEXT NOT NULL CHECK(status IN ('identified', 'assessed', 'mitigating', 'mitigated', 'accepted', 'closed')),
    detected_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- Foreign keys: SET NULL on delete to preserve risk history
    FOREIGN KEY (activity_id) REFERENCES activity_log(activity_id) ON DELETE SET NULL,
    FOREIGN KEY (prd_id) REFERENCES prd_documents(prd_id) ON DELETE SET NULL,
    FOREIGN KEY (task_id) REFERENCES prd_tasks(task_id) ON DELETE SET NULL,
    FOREIGN KEY (skill_id) REFERENCES reg_skills(skill_id) ON DELETE SET NULL
);

-- ============================================================================
-- RISK MITIGATIONS
-- ============================================================================

-- Tracks mitigation actions for risks with effectiveness measurement
CREATE TABLE IF NOT EXISTS risk_mitigations (
    mitigation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    risk_id TEXT NOT NULL,  -- FK to risk_register
    activity_id INTEGER,  -- FK to activity_log (hub) - nullable, ON DELETE SET NULL

    -- Mitigation details
    mitigation_type TEXT NOT NULL CHECK(mitigation_type IN ('process_change', 'technical_fix', 'monitoring', 'acceptance')),
    mitigation_action TEXT NOT NULL,  -- description of the mitigation
    task_id TEXT,  -- FK to prd_tasks (if mitigation is task-based)

    -- Effectiveness tracking
    risk_score_before INTEGER CHECK(risk_score_before BETWEEN 1 AND 25),
    risk_score_after INTEGER CHECK(risk_score_after BETWEEN 1 AND 25),
    effectiveness REAL,  -- % reduction, calculated as (before - after) / before * 100

    -- Status tracking
    status TEXT NOT NULL CHECK(status IN ('planned', 'in_progress', 'implemented', 'verified', 'failed')),
    implemented_at DATETIME,
    verified_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- Foreign keys: CASCADE delete when risk is removed, SET NULL for activity/task
    FOREIGN KEY (risk_id) REFERENCES risk_register(risk_id) ON DELETE CASCADE,
    FOREIGN KEY (activity_id) REFERENCES activity_log(activity_id) ON DELETE SET NULL,
    FOREIGN KEY (task_id) REFERENCES prd_tasks(task_id) ON DELETE SET NULL
);

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

-- Risk Register Indexes

-- Index for finding highest-risk items (sorted by score, descending)
CREATE INDEX IF NOT EXISTS idx_risk_score
ON risk_register(risk_score DESC);

-- Index for queries filtering by status and type (e.g., "show all open security risks")
CREATE INDEX IF NOT EXISTS idx_risk_status_type
ON risk_register(status, risk_type);

-- Index for PRD-based queries (e.g., "show all risks for PRD-001")
CREATE INDEX IF NOT EXISTS idx_risk_prd
ON risk_register(prd_id);

-- Index for task-based queries (e.g., "show all risks for T001")
CREATE INDEX IF NOT EXISTS idx_risk_task
ON risk_register(task_id);

-- Index for skill-based queries (e.g., "show all risks for ds-security")
CREATE INDEX IF NOT EXISTS idx_risk_skill
ON risk_register(skill_id);

-- Risk Mitigations Indexes

-- Index for risk drill-down (e.g., "show all mitigations for RISK-001")
CREATE INDEX IF NOT EXISTS idx_mitigation_risk
ON risk_mitigations(risk_id);

-- Index for task tracking (e.g., "show all mitigations linked to T001")
CREATE INDEX IF NOT EXISTS idx_mitigation_task
ON risk_mitigations(task_id);

-- Index for filtering by status (e.g., "show all in-progress mitigations")
CREATE INDEX IF NOT EXISTS idx_mitigation_status
ON risk_mitigations(status);
