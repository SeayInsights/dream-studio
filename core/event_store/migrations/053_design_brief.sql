-- Migration 053: Design brief persistence for UI work orders (Slice 7a).
-- status values: 'draft' (editable) | 'locked' (immutable — human approval gate).
-- A locked brief is required before ui_component and ui_page work orders can start.

CREATE TABLE IF NOT EXISTS ds_design_briefs (
    brief_id      TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL
                  REFERENCES ds_projects(project_id),
    status        TEXT NOT NULL DEFAULT 'draft'
                  CHECK(status IN ('draft', 'locked')),
    purpose       TEXT,
    audience      TEXT,
    tone          TEXT,
    design_system TEXT,
    font_pairing  TEXT,
    brand_tokens  TEXT,
    raw_output    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ds_design_briefs_project
    ON ds_design_briefs(project_id);
