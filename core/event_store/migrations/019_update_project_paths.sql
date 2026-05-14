-- Migration 019: Update project paths to new structure
-- Adds planning_path and sessions_path columns and updates to use user-local relative project paths
-- Run date: 2026-05-06

-- Add new columns if they don't exist
ALTER TABLE reg_projects ADD COLUMN planning_path TEXT;
ALTER TABLE reg_projects ADD COLUMN sessions_path TEXT;

-- For projects with existing data, set planning and sessions paths to user-local relative structure.
-- Runtime code resolves these under Path.home() / ".dream-studio"; never bake an operator home path into install migrations.
UPDATE reg_projects
SET planning_path = '.dream-studio/projects/' || COALESCE(project_name, project_id) || '/planning',
    sessions_path = '.dream-studio/projects/' || COALESCE(project_name, project_id) || '/sessions'
WHERE planning_path IS NULL;

-- Verify results (for manual checking)
-- SELECT project_id, project_name, planning_path, sessions_path FROM reg_projects LIMIT 10;
