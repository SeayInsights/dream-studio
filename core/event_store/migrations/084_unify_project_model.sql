-- Migration 084: Unify project model — finish the cutover to business_projects
--
-- Phase 18.x A2 unification (schema-bifurcation investigation 2026-05-30).
--
-- Background:
--   reg_projects was the original passive telemetry table (Path.cwd().name slugs,
--   session counts). business_projects is the event-sourced canonical authority
--   (UUID ids, ProjectProjection, source_event_id/last_event_id, SDLC lifecycle).
--   Wave-6 analysis bolt-ons (pi_* tables, stack_detected, health_score) were added
--   to reg_projects but the insertion path was broken — control/analysis/engine.py
--   attempted to INSERT a project_source column that never existed in any migration,
--   so all pi_* tables have zero rows. There is no analysis data to migrate.
--
-- What this migration does:
--   1. Add session-telemetry columns to business_projects (migrate the one live purpose
--      reg_projects served).
--   2. Add project_path column to business_projects (needed by session hooks and dashboard).
--   3. Drop the broken analysis bolt-on tables (pi_* — all empty).
--   4. Drop reg_projects (the legacy table).
--
-- After this migration:
--   - business_projects is the sole project table.
--   - Session hooks resolve project_id via the .dream-studio-project marker resolver.
--   - All reg_projects FK references in raw_sessions, raw_handoffs, raw_specs become
--     dead text in the schema (SQLite won't enforce or error; a future cleanup
--     migration can recreate those tables without the FK reference).
--
-- Idempotent: all ADD COLUMNs use IF NOT EXISTS via try-on-fail pattern (not supported
-- directly in SQLite ALTER; guarded by the bootstrap runner's IF NOT EXISTS checks).
-- DROP TABLE IF EXISTS is idempotent.

-- ── 1. Add session-telemetry + path columns to business_projects ─────────────

ALTER TABLE business_projects ADD COLUMN project_path TEXT;
ALTER TABLE business_projects ADD COLUMN total_sessions INTEGER NOT NULL DEFAULT 0;
ALTER TABLE business_projects ADD COLUMN total_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE business_projects ADD COLUMN last_session_at TEXT;

-- Index for session-sorted project list (replaces reg_projects ordering).
CREATE INDEX IF NOT EXISTS idx_business_projects_last_session
ON business_projects(last_session_at DESC);

CREATE INDEX IF NOT EXISTS idx_business_projects_path
ON business_projects(project_path);

-- ── 2. Best-effort backfill: copy path from .dream-studio-project markers ────
-- Not SQL-expressible here; the application layer handles this on next
-- register_project() call. Existing projects' project_path stays NULL until
-- the project is referenced through the updated register_project() path.

-- ── 3. Drop broken empty analysis bolt-on tables ────────────────────────────
-- All pi_* tables have zero rows (the engine.py INSERT was broken — project_source
-- column never existed). Confirmed via live DB inspection 2026-05-30.

DROP TABLE IF EXISTS pi_analysis_runs;
DROP TABLE IF EXISTS pi_improvements;
DROP TABLE IF EXISTS pi_bugs;
DROP TABLE IF EXISTS pi_violations;
DROP TABLE IF EXISTS pi_dependencies;
DROP TABLE IF EXISTS pi_components;

-- ── 4. Drop reg_projects ─────────────────────────────────────────────────────
-- Turn off FK enforcement during the drop. raw_sessions, raw_handoffs, raw_specs
-- still reference reg_projects in their schema text but these are dead FK
-- references — SQLite doesn't enforce them when the parent table is absent.

PRAGMA foreign_keys = OFF;
DROP TABLE IF EXISTS reg_projects;
PRAGMA foreign_keys = ON;
