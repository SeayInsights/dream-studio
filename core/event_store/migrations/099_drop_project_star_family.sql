-- Migration 099: Drop project_* Legacy Family (Phase 18.6.2 Cleanup)
-- Date: 2026-06-05
--
-- Context:
--   Phase 18.1.6 (2026-05-22) committed to retiring all project_* tables after
--   Phase 18.4 builds business_* replacements. The harvest pre-flight
--   (.planning/specs/prd-authority-harvest-preflight.md, 2026-06-05) confirmed:
--   - All 8 tables have 0 rows (no data loss)
--   - No incoming FK dependencies from any other table
--   - Writers in prd_authority.py were never invoked in production (test-only)
--   - Readers in prd_authority.py are guarded (B1+B2) as of migration 099
--   - All other code references guarded or removed (B3-B6) in same PR
--
--   The corresponding CREATE TABLE migrations (040 and 047) are immutable
--   history and are NOT touched by this migration.
--
-- Drop order:
--   vw_project_readiness_latest depends on project_readiness_scorecards.
--   View must be dropped before the table.

DROP VIEW IF EXISTS vw_project_readiness_latest;

DROP TABLE IF EXISTS project_readiness_scorecards;
DROP TABLE IF EXISTS project_health_scorecards;
DROP TABLE IF EXISTS project_intake_records;
DROP TABLE IF EXISTS project_intake_questions;
DROP TABLE IF EXISTS project_assumption_records;
DROP TABLE IF EXISTS project_milestone_records;
DROP TABLE IF EXISTS project_work_order_authority_records;
DROP TABLE IF EXISTS project_change_order_records;
