-- Migration 115: Vestigial table sweep (WO-DEBT-F)
--
-- Drops 11 vestigial tables and truncates 1 test-contaminated table.
-- Pre-push gate failure on first attempt revealed that the original
-- "Audit-1 stale" and "raw_*" sets had live code consumers (row-count
-- pre-flight was insufficient — code-reference sweep required).
-- This migration drops only the tables confirmed safe after full sweep:
--
--   prd_* cluster (7): never created in live DB — DROP TABLE IF EXISTS is a
--     no-op on both live and fresh installs.
--
--   pi_wave_tasks, pi_waves (2): no SQL consumers found outside a dev
--     inspection script and a docstring comment. Dropped child-before-parent.
--
--   agent_context_scope_policies (1): no SQL SELECT/INSERT/UPDATE found;
--     only appears in source_tables metadata lists.
--
--   agent_registry_records (1): _recorded_agents() in scoped_agents.py guards
--     all queries with _table_exists() and returns [] if absent — safe to drop.
--
--   Truncate target: research_evidence_records (9 test-contamination rows,
--     real write path is live — schema kept, data cleared).
--
-- The following tables from the original task scope were found to have live
-- consumers and are NOT dropped here; they require a dedicated WO:
--   capability_route_records, artifact_records, raw_research, hook_findings,
--   github_repo_attribution_records, team_rollup_records,
--   installer_distribution_checks, demo_case_study_packets,
--   raw_lessons, raw_workflow_runs, raw_workflow_nodes, raw_pulse_snapshots,
--   raw_planning_specs, reg_analyzed_repos, reg_skills, raw_token_usage,
--   raw_specs, raw_tasks, ds_technology_signals, raw_skill_telemetry.

PRAGMA foreign_keys = OFF;

-- ── prd_* cluster (7) — not present in live DB; no-op on fresh installs ─────────
DROP TABLE IF EXISTS prd_assumptions;
DROP TABLE IF EXISTS prd_change_orders;
DROP TABLE IF EXISTS prd_intake_questions;
DROP TABLE IF EXISTS prd_intakes;
DROP TABLE IF EXISTS prd_notes;
DROP TABLE IF EXISTS prd_requirements;
DROP TABLE IF EXISTS prd_specs;

-- ── pi_wave_tasks before pi_waves (FK-safe child-before-parent order) ────────────
DROP TABLE IF EXISTS pi_wave_tasks;
DROP TABLE IF EXISTS pi_waves;

-- ── Agent scaffolding — no SQL consumers confirmed ──────────────────────────────
DROP TABLE IF EXISTS agent_context_scope_policies;
DROP TABLE IF EXISTS agent_registry_records;

-- ── Truncate: test-contamination rows, real write path — keep schema ─────────────
DELETE FROM research_evidence_records;

PRAGMA foreign_keys = ON;
