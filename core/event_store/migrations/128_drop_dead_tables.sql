-- Migration 128: Drop 24 verified-dead tables from studio.db
--
-- These tables are empty and have no live consumer code.  Their only
-- references are the creating migrations and orphaned code paths that
-- are removed in the same PR.  Keeping them means a fresh
-- run_migrations install keeps re-creating them.
--
-- Affected source migrations:
--   001 — raw_pulse_snapshots, raw_planning_specs, sum_analytics_run
--   003 — reg_skills, reg_skill_deps, reg_workflows
--   004 — raw_specs, raw_tasks
--   007 — reg_analyzed_repos, reg_repo_extractions, reg_repo_research_links
--   008 — reg_research_sources
--   030 — adapter_executions
--   041 — legacy_canonical_event_import_map
--   044 — github_repo_attribution_records, github_repo_integration_candidates,
--           github_repo_license_findings, github_repo_pattern_references,
--           github_repo_dependency_findings, github_repo_security_findings
--   046 — privacy_redaction_export_records, local_watch_schedule_records,
--           team_rollup_records, installer_distribution_checks,
--           demo_case_study_packets
--
-- Tables intentionally NOT dropped (live consumers exist):
--   003: reg_gotchas, fts_gotchas (gotcha scanner, hydrate_registry)
--   007: ds_documents cluster already gone (migration 127)
--   008: raw_research, pi_waves, pi_wave_tasks
--   044: github_repo_evaluations, github_repo_adoption_decisions
--   046: skill_evaluation_runs, policy_decision_records,
--         connector_ingestion_runs
--
-- Drop order: indexes first, then FK-child tables before FK-parent tables.
--
-- Reviewed: 2026-06-26 (WO-DEAD-TABLES)

-- ── Indexes: migration 046 dead-table indexes ────────────────────────────────
DROP INDEX IF EXISTS idx_privacy_redaction_export_records_visibility;
DROP INDEX IF EXISTS idx_local_watch_schedule_records_enabled;

-- Note: idx_github_repo_evaluations_repo is on the KEPT table github_repo_evaluations
-- and is NOT dropped here.

-- ── Indexes: migration 041 ───────────────────────────────────────────────────
DROP INDEX IF EXISTS idx_legacy_import_map_event_id;
DROP INDEX IF EXISTS idx_legacy_import_map_target;

-- ── Indexes: migration 007 dead-table indexes ────────────────────────────────
DROP INDEX IF EXISTS idx_repos_framework;
DROP INDEX IF EXISTS idx_repos_trust;
DROP INDEX IF EXISTS idx_repos_language;
DROP INDEX IF EXISTS idx_repos_last_analyzed;
DROP INDEX IF EXISTS idx_repo_extractions_repo;
DROP INDEX IF EXISTS idx_repo_extractions_type;
DROP INDEX IF EXISTS idx_repo_extractions_document;
DROP INDEX IF EXISTS idx_repo_extractions_effectiveness;
DROP INDEX IF EXISTS idx_repo_research_repo;
DROP INDEX IF EXISTS idx_repo_research_research;
DROP INDEX IF EXISTS idx_repo_research_relevance;

-- ── migration 046: dead platform-hardening tables ───────────────────────────
DROP TABLE IF EXISTS privacy_redaction_export_records;
DROP TABLE IF EXISTS local_watch_schedule_records;
DROP TABLE IF EXISTS team_rollup_records;
DROP TABLE IF EXISTS installer_distribution_checks;
DROP TABLE IF EXISTS demo_case_study_packets;

-- ── migration 044: dead github_repo sub-tables ───────────────────────────────
-- Drop FK-children of github_repo_evaluations first.
-- github_repo_evaluations and github_repo_adoption_decisions are KEPT.
DROP TABLE IF EXISTS github_repo_attribution_records;
DROP TABLE IF EXISTS github_repo_integration_candidates;
DROP TABLE IF EXISTS github_repo_pattern_references;
DROP TABLE IF EXISTS github_repo_dependency_findings;
DROP TABLE IF EXISTS github_repo_security_findings;
DROP TABLE IF EXISTS github_repo_license_findings;

-- ── migration 041 ────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS legacy_canonical_event_import_map;

-- ── migration 030 ────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS adapter_executions;

-- ── migration 008: dead registry table ──────────────────────────────────────
DROP TABLE IF EXISTS reg_research_sources;

-- ── migration 007: dead repo-registry tables ────────────────────────────────
-- Drop FK-children before FK-parent.
DROP TABLE IF EXISTS reg_repo_extractions;
DROP TABLE IF EXISTS reg_repo_research_links;
DROP TABLE IF EXISTS reg_analyzed_repos;

-- ── migration 004: dead operational tables ───────────────────────────────────
-- raw_specs parent of raw_tasks via spec_id (soft ref, no enforced FK).
-- Drop child first anyway for clarity.
DROP TABLE IF EXISTS raw_tasks;
DROP TABLE IF EXISTS raw_specs;

-- ── migration 003: dead registry tables ─────────────────────────────────────
-- reg_gotchas, fts_gotchas, and the three fts triggers are NOT dropped.
-- reg_skill_deps references reg_skills — drop child first.
DROP TABLE IF EXISTS reg_skill_deps;
DROP TABLE IF EXISTS reg_workflows;
DROP TABLE IF EXISTS reg_skills;

-- ── migration 001: dead analytics tables ────────────────────────────────────
DROP TABLE IF EXISTS sum_analytics_run;
DROP TABLE IF EXISTS raw_planning_specs;
DROP TABLE IF EXISTS raw_pulse_snapshots;
