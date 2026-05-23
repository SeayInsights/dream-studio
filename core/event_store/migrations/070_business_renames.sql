-- Migration 070: ds_* → business_* renames — Phase 18.1.7
--
-- Renames the ds_* table family to business_* naming per the v2 architecture
-- Commitment 3 (domain separation). This is the final workstream of Phase 18.1.
--
-- Tables renamed:
--   ds_projects           → business_projects
--   ds_milestones         → business_milestones (+schema enrichment)
--   ds_work_orders        → reconciled into business_work_orders (already exists from 069)
--   ds_tasks              → business_tasks
--   ds_design_briefs      → business_design_briefs
--   ds_work_order_types   → business_work_order_types
--
-- Data preservation: all rows copied. ds_work_orders status mapping:
--   'open' → 'created', 'complete' → 'closed', 'in_progress'/'blocked' unchanged.
--
-- Tables NOT renamed: ds_documents (FKs to reg_projects), ds_technology_signals (telemetry).
--
-- business_work_orders reconciliation:
--   The table was created in migration 069 as the v2 projection-populated table.
--   ds_work_orders was the direct-write operational table. This migration:
--   1. Adds description + work_order_type columns to business_work_orders
--   2. Updates existing rows with data from ds_work_orders
--   3. Inserts any ds_work_orders rows not present in business_work_orders
--   4. Drops ds_work_orders
--
-- business_milestones enrichment:
--   Absorbs stage_gate_json, validation_expectations_json, security_readiness_checks_json
--   from project_milestone_records schema. NULL for existing rows. Phase 18.4 will populate.
--
-- Idempotent: CREATE IF NOT EXISTS, INSERT OR IGNORE, DROP IF EXISTS.
--
-- FK note: temporarily disable FK enforcement during the rename/copy/drop
-- sequence. The bootstrap runner enables PRAGMA foreign_keys = ON before
-- applying migrations, but cross-table copy with in-flight DROP TABLE is
-- safe structurally — we just need FK enforcement off during the transition.

PRAGMA foreign_keys = OFF;

-- ============================================================
-- 1. business_projects (no FK deps)
-- ============================================================

CREATE TABLE IF NOT EXISTS business_projects (
    project_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

INSERT OR IGNORE INTO business_projects (project_id, name, description, status, created_at, updated_at)
SELECT project_id, name, description, status, created_at, updated_at
FROM ds_projects;

DROP TABLE IF EXISTS ds_projects;

-- ============================================================
-- 2. business_milestones (FK → business_projects, +enrichment)
-- ============================================================

CREATE TABLE IF NOT EXISTS business_milestones (
    milestone_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES business_projects(project_id),
    title TEXT NOT NULL,
    description TEXT,
    due_date TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    order_index INTEGER DEFAULT 0,
    -- Enrichment fields from project_milestone_records (Phase 18.1.6)
    stage_gate_json TEXT,
    validation_expectations_json TEXT,
    security_readiness_checks_json TEXT
);

INSERT OR IGNORE INTO business_milestones (
    milestone_id, project_id, title, description, due_date, status,
    created_at, updated_at, order_index,
    stage_gate_json, validation_expectations_json, security_readiness_checks_json
)
SELECT
    milestone_id, project_id, title, description, due_date, status,
    created_at, updated_at, order_index,
    NULL, NULL, NULL
FROM ds_milestones;

CREATE INDEX IF NOT EXISTS idx_business_milestones_project ON business_milestones(project_id);

DROP TABLE IF EXISTS ds_milestones;

-- ============================================================
-- 3. business_work_order_types (no FK deps)
-- ============================================================

CREATE TABLE IF NOT EXISTS business_work_order_types (
    type_id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    pre_build_gate TEXT,
    build_executor TEXT,
    post_build_gate TEXT,
    workflow_template TEXT,
    precondition_skill TEXT,
    task_generator TEXT,
    resolution_instructions TEXT
);

INSERT OR IGNORE INTO business_work_order_types (
    type_id, label, pre_build_gate, build_executor, post_build_gate,
    workflow_template, precondition_skill, task_generator, resolution_instructions
)
SELECT
    type_id, label, pre_build_gate, build_executor, post_build_gate,
    workflow_template, precondition_skill, task_generator, resolution_instructions
FROM ds_work_order_types;

DROP TABLE IF EXISTS ds_work_order_types;

-- ============================================================
-- 4. business_work_orders reconciliation
--    (table already exists from migration 069)
-- ============================================================

-- Add columns introduced by this migration (nullable, no constraint = safe ALTER)
ALTER TABLE business_work_orders ADD COLUMN description TEXT;
ALTER TABLE business_work_orders ADD COLUMN work_order_type TEXT;
-- updated_at: schema-consistency column matching all other business_* tables.
-- CLI mutators (start, close, block/unblock) write this; projection writes last_updated_at.
ALTER TABLE business_work_orders ADD COLUMN updated_at TEXT;

-- Update existing rows with description and work_order_type from ds_work_orders
UPDATE business_work_orders
SET
    description     = (SELECT dwo.description     FROM ds_work_orders dwo WHERE dwo.work_order_id = business_work_orders.work_order_id),
    work_order_type = (SELECT dwo.work_order_type FROM ds_work_orders dwo WHERE dwo.work_order_id = business_work_orders.work_order_id)
WHERE work_order_id IN (SELECT work_order_id FROM ds_work_orders);

-- Insert ds_work_orders rows that are not already present in business_work_orders,
-- applying status mapping: 'open' → 'created', 'complete' → 'closed', others unchanged.
INSERT OR IGNORE INTO business_work_orders (
    work_order_id, project_id, milestone_id, title, status,
    created_at, description, work_order_type, block_reason
)
SELECT
    work_order_id,
    project_id,
    milestone_id,
    title,
    CASE status
        WHEN 'open'     THEN 'created'
        WHEN 'complete' THEN 'closed'
        ELSE status
    END,
    created_at,
    description,
    work_order_type,
    block_reason
FROM ds_work_orders
WHERE work_order_id NOT IN (SELECT work_order_id FROM business_work_orders);

-- New index for work_order_type lookups (existing 069 indexes are preserved)
CREATE INDEX IF NOT EXISTS idx_bwo_type ON business_work_orders(work_order_type);

DROP TABLE IF EXISTS ds_work_orders;

-- ============================================================
-- 5. business_tasks (FK → business_projects, business_work_orders)
-- ============================================================

CREATE TABLE IF NOT EXISTS business_tasks (
    task_id TEXT PRIMARY KEY,
    work_order_id TEXT NOT NULL REFERENCES business_work_orders(work_order_id),
    project_id TEXT NOT NULL REFERENCES business_projects(project_id),
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

INSERT OR IGNORE INTO business_tasks (
    task_id, work_order_id, project_id, title, description,
    status, created_at, updated_at
)
SELECT
    task_id, work_order_id, project_id, title, description,
    status, created_at, updated_at
FROM ds_tasks;

CREATE INDEX IF NOT EXISTS idx_business_tasks_project    ON business_tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_business_tasks_work_order ON business_tasks(work_order_id);

DROP TABLE IF EXISTS ds_tasks;

-- ============================================================
-- 6. business_design_briefs (FK → business_projects)
-- ============================================================

CREATE TABLE IF NOT EXISTS business_design_briefs (
    brief_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES business_projects(project_id),
    status TEXT NOT NULL DEFAULT 'draft',
    purpose TEXT,
    audience TEXT,
    tone TEXT,
    design_system TEXT,
    font_pairing TEXT,
    brand_tokens TEXT,
    raw_output TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

INSERT OR IGNORE INTO business_design_briefs (
    brief_id, project_id, status, purpose, audience, tone,
    design_system, font_pairing, brand_tokens, raw_output,
    created_at, updated_at
)
SELECT
    brief_id, project_id, status, purpose, audience, tone,
    design_system, font_pairing, brand_tokens, raw_output,
    created_at, updated_at
FROM ds_design_briefs;

CREATE INDEX IF NOT EXISTS idx_business_design_briefs_project ON business_design_briefs(project_id);

DROP TABLE IF EXISTS ds_design_briefs;

-- Re-enable FK enforcement (restored to the bootstrap default)
PRAGMA foreign_keys = ON;
