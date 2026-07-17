-- Migration 147: drop capability_route_records — dead-writer table (WO-SCHEMALEAN, acca5184)
--
-- Vetting (.planning/audits/schema-lean-vetting-2026-07-15.md): 0 rows; the only production
-- caller of recommend_capability_route (GET /capability-routes/recommendation) passes
-- persist=False by design, so record_capability_route's INSERT is never reached in production
-- — the identical dead-writer pattern already dropped for compliance_review_flags. The
-- recommendation PREVIEW (recommend_capability_route(persist=False)) is kept; only the never-used
-- persistence layer and the summary-of-persisted view are removed with this table.
--
-- Removed with the table: record_capability_route (writer), capability_route_summary (reader),
-- GET /api/shared-intelligence/capability-routes (route + surface), the capability_routes section
-- of the installed_adapter_router read model, and capability_route_records from
-- REQUIRED_SHARED_INTELLIGENCE_TABLES / CAPABILITY_SOURCE_TABLES.
--
-- Additive-safe: no other table references it. .released_version NOT bumped — 147 stays
-- unreleased on the live authority DB until `ds migrate activate`; fresh installs and CI apply
-- it immediately.

DROP TABLE IF EXISTS capability_route_records;
