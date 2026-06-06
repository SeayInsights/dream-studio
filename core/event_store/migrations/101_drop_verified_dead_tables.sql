-- Migration 101: Drop 13 Verified-Dead Tables (Wave 6 Cleanup)
-- Date: 2026-06-06
--
-- Context:
--   Wave 6 of the dead-weight cleanup. Per-table verification on 2026-06-06
--   confirmed all 13 tables below are DROP-SAFE:
--     - 0 rows in the live DB (no data loss)
--     - no live code readers or writers (test-only or fully removed paths)
--     - no view dependencies
--     - FK-safe drop order (child tables before parent tables)
--
--   The audit's original ~38-candidate list was reduced to 13 after per-table
--   verification: 18 candidates were PULLED because per-table verification found
--   live code paths (live readers/writers), and the 7 prd_* cluster tables were
--   DEFERRED because they remain entangled in a view/FK web with kept tables.
--   No career_* re-drops are needed — migration 100 already covers all replay
--   paths for that family.
--
--   The CREATE TABLE migrations that produced these tables remain immutable
--   history and are NOT touched by this migration:
--     - 044 → agent_result_records, capability_center_records,
--             workflow_agent_skill_mappings
--     - 039 → dashboard_authority_reconciliation_records
--     - 027 → guardrail_rules_audit
--     - 007 → reg_repo_research_links
--     - 021 → risk_register, risk_mitigations
--     - 028 → automation_checkpoints
--     - 005 → automation_log
--     - 020 → sec_hook_checks
--     - 037 → telemetry_module_registry, telemetry_entity_registry
--
-- Drop order: child tables before parent tables (FK-safe). IF EXISTS clauses on
-- all DROPs prevent errors on already-clean databases.

DROP TABLE IF EXISTS automation_checkpoints;
DROP TABLE IF EXISTS automation_log;
DROP TABLE IF EXISTS risk_mitigations;
DROP TABLE IF EXISTS risk_register;
DROP TABLE IF EXISTS telemetry_entity_registry;
DROP TABLE IF EXISTS telemetry_module_registry;
DROP TABLE IF EXISTS reg_repo_research_links;
DROP TABLE IF EXISTS agent_result_records;
DROP TABLE IF EXISTS capability_center_records;
DROP TABLE IF EXISTS dashboard_authority_reconciliation_records;
DROP TABLE IF EXISTS guardrail_rules_audit;
DROP TABLE IF EXISTS sec_hook_checks;
DROP TABLE IF EXISTS workflow_agent_skill_mappings;
