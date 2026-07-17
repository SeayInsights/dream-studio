-- Migration 149: drop audit_runs — superseded external-write surface (WO-SCHEMALEAN, acca5184)
--
-- Vetting (.planning/audits/schema-lean-vetting-2026-07-15.md): audit_runs (0 rows) has had NO
-- internal writer since the initial commit — it was a designed external-tool write endpoint
-- (POST /api/v1/audits/runs) that nothing in-repo ever calls, and its routes reference security
-- tables dropped long ago (sec_sarif_findings / sec_cve_matches). The live security surface is
-- security_events (17 rows) + scan_runs (8 rows) behind /api/v1/security/*; the audit_runs
-- "Security Audits" dashboard subtab was permanently empty and duplicative of it.
--
-- Removed with the table: projections/api/routes/audits.py (the whole /api/v1/audits/* module:
-- list/get/create/stats/findings + AuditRunCreate) and its main.py registration. The dead
-- dashboard "Security Audits" subtab / audit-history tab degrade gracefully (existing try/catch
-- → empty/error) and are removed in a follow-up dead-UI cleanup WO.
--
-- .released_version NOT bumped — 149 stays unreleased until `ds migrate activate`; fresh
-- installs and CI apply it immediately.

DROP TABLE IF EXISTS audit_runs;
