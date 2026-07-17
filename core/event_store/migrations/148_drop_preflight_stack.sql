-- Migration 148: drop the preflight stack — unwired aspirational feature (WO-SCHEMALEAN, acca5184)
--
-- Vetting (.planning/audits/schema-lean-vetting-2026-07-15.md): preflight_events (0 rows) and
-- business_work_order_preflights (0 rows) form a closed, unwired loop:
--   spec_ingestor.ingest_specs (never called from any CLI/route/workflow — test-only)
--     -> mutations.create_preflight/set_preflight_status
--       -> preflight_events (spine)
--         -> PreflightProjection.fold_spine
--           -> business_work_order_preflights (read model)
--             -> start.py::_check_preflight_gate (a live but permanent no-op — the table is
--                always empty, and the gate returns None when the table is absent).
-- Nothing external ever writes a finding, so the whole feature is aspirational. Its "pre-work
-- risk" purpose is already delivered live by the CI blast-radius / hanging-detector gate
-- (WO-BLAST-RADIUS-GATE), so this stack is duplicative + unwired — dropped per the operator's
-- "drop whatever is not critical or is duplicative".
--
-- Removed with the tables: core/preflight/mutations.py, core/preflight/spec_ingestor.py,
-- core/projections/preflight_projection.py (+ its runner registration), and
-- start.py::_check_preflight_gate (+ call site). No live data lost (both tables 0 rows).
--
-- .released_version NOT bumped — 148 stays unreleased until `ds migrate activate`; fresh
-- installs and CI apply it immediately.

DROP TABLE IF EXISTS business_work_order_preflights;
DROP TABLE IF EXISTS preflight_events;
