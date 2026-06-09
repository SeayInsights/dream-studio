-- Migration 100: Drop career_* Family (Wave 2 — Career Annihilation)
-- Date: 2026-06-05
--
-- Context:
--   The career module was integrated speculatively and never activated.
--   career_ops_status() has always returned enabled:false (external
--   career_studio_path dependency never configured). All 15 tables confirmed
--   0 rows in the live DB on 2026-06-05 (wave 2 verification script).
--   No views reference career tables. No incoming FK dependencies.
--   Audit trail: .planning/specs/ dead-weight audits + per-file classification.
--   Note: the audits said 14 tables; live-DB verification found 15
--   (career_profile_fields was missed by the audit count).
--
--   The creating migration (044_career_capability_agent_github_authority.sql)
--   remains immutable history. The capability_center, scoped_agents, and
--   github_repo_intake tables created by 044 are NOT touched — those modules
--   stay live.
--
-- Drop order: no inter-table FKs among career_* tables; arbitrary order.

DROP TABLE IF EXISTS career_application_events;
DROP TABLE IF EXISTS career_application_field_mappings;
DROP TABLE IF EXISTS career_applications;
DROP TABLE IF EXISTS career_browser_automation_runs;
DROP TABLE IF EXISTS career_case_studies;
DROP TABLE IF EXISTS career_cover_letter_versions;
DROP TABLE IF EXISTS career_evidence_refs;
DROP TABLE IF EXISTS career_interview_story_bank;
DROP TABLE IF EXISTS career_job_opportunities;
DROP TABLE IF EXISTS career_portfolio_artifacts;
DROP TABLE IF EXISTS career_profile_fields;
DROP TABLE IF EXISTS career_profiles;
DROP TABLE IF EXISTS career_resume_versions;
DROP TABLE IF EXISTS career_role_targets;
DROP TABLE IF EXISTS career_scorecards;
