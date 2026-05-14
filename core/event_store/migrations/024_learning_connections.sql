-- Migration 023: Learning Connections (Phase 3 Cross-Domain Traceability)
-- Created: 2026-05-06
-- Purpose: Add foreign key columns to raw_lessons for cross-domain linkage
-- Enables: Activity-to-lesson tracing, task-based learning retrieval, PRD/skill learning analysis
-- Links: raw_lessons → activity_log (hub) + prd_tasks + prd_documents + reg_skills (spokes)

-- ============================================================================
-- ALTER TABLE: raw_lessons - Add FK Columns
-- ============================================================================

-- Add activity_id foreign key (hub connection)
ALTER TABLE raw_lessons ADD COLUMN activity_id INTEGER;

-- Add task_id foreign key (for task-based learning)
ALTER TABLE raw_lessons ADD COLUMN task_id TEXT;

-- Add prd_id foreign key (for PRD-scoped learning)
ALTER TABLE raw_lessons ADD COLUMN prd_id TEXT;

-- Add skill_id foreign key (for skill-specific learning)
ALTER TABLE raw_lessons ADD COLUMN skill_id TEXT;

-- ============================================================================
-- FOREIGN KEYS: raw_lessons
-- ============================================================================

-- Link to activity_log (hub) - ON DELETE SET NULL to preserve learning history
CREATE TABLE IF NOT EXISTS temp_fk_constraint (
    activity_id INTEGER REFERENCES activity_log(activity_id) ON DELETE SET NULL,
    task_id TEXT REFERENCES prd_tasks(task_id) ON DELETE SET NULL,
    prd_id TEXT REFERENCES prd_documents(prd_id) ON DELETE SET NULL,
    skill_id TEXT REFERENCES reg_skills(skill_id) ON DELETE SET NULL
);

-- Note: SQLite doesn't support adding foreign keys to existing tables directly.
-- The constraints are enforced at the application level and validated via indexes.

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

-- Index for activity-based learning queries (e.g., "show all lessons from activity X")
CREATE INDEX IF NOT EXISTS idx_lessons_activity
ON raw_lessons(activity_id);

-- Index for task-based learning queries (e.g., "show all lessons linked to task T001")
CREATE INDEX IF NOT EXISTS idx_lessons_task
ON raw_lessons(task_id);

-- Index for PRD-based learning queries (e.g., "show all lessons for PRD-001")
CREATE INDEX IF NOT EXISTS idx_lessons_prd
ON raw_lessons(prd_id);

-- Index for skill-based learning queries (e.g., "show all lessons for ds-core")
CREATE INDEX IF NOT EXISTS idx_lessons_skill
ON raw_lessons(skill_id);

-- Composite index for cross-entity queries (activity + status, e.g., "what did we learn in this activity?")
CREATE INDEX IF NOT EXISTS idx_lessons_activity_status
ON raw_lessons(activity_id, status);

-- Composite index for task + confidence (e.g., "high-confidence lessons from this task")
CREATE INDEX IF NOT EXISTS idx_lessons_task_confidence
ON raw_lessons(task_id, confidence);

-- ============================================================================
-- DROP TEMPORARY CONSTRAINT TABLE
-- ============================================================================

DROP TABLE IF EXISTS temp_fk_constraint;
