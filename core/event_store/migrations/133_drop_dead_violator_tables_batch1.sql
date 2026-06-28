-- Migration 133: Drop dead-violator tables — Batch 1 (canonical-first realignment)
--
-- Target architecture: studio.db = canonical EVENTS + non-event-sourced AUTHORITY + pipeline ONLY.
-- No private direct-write tables. Every telemetry/governance signal = a canonical event.
--
-- Tables DROPPED (4 of 7 candidates — the 4 with confirmed DEAD writers):
--
-- compliance_review_flags
--   Writer: core/production_readiness/controls.py::_record_compliance_flags()
--   Called from: record_production_readiness_assessment() → only when persist=True.
--   persist=True production callers: NONE. Every production caller uses persist=False
--   (default): core/release/versioning.py:62, core/shared_intelligence/contract_atlas.py:122,
--   projections/api/routes/shared_intelligence.py:491 (explicit persist=False).
--   Additionally, production_readiness_assessment_runs was dropped in migration 112,
--   so record_production_readiness_assessment() returns early (line 437 guard) before
--   ever reaching _record_compliance_flags(). DEAD — structurally unreachable in production.
--
-- release_readiness_records
--   Writer: core/production_readiness/controls.py::_record_scorecards()
--   Same call chain and same dead gate as compliance_review_flags.
--   DEAD — structurally unreachable in production.
--
-- policy_decision_records
--   Writer: core/shared_intelligence/platform_hardening.py::record_policy_decision()
--   Production callers of record_policy_decision(): NONE.
--   interfaces/cli/commands/system.py:498 and projections/api/routes/shared_intelligence.py:407
--   call evaluate_policy_decision() (read-only, no DB write) — NOT record_policy_decision().
--   The only callers of record_policy_decision() are in tests/unit/test_platform_hardening_sequence.py.
--   DEAD — test-only writer.
--
-- guard_events
--   Writers: guardrails/delta_guard.py:129,191 (_emit_delta_block_event, _emit_delta_advisory_events)
--           guardrails/memory_taint.py:65 (emit_memory_skip_event)
--   These are called from guard_delta_pairs() and emit_memory_skip_event() respectively.
--   guard_delta_pairs(): called from tests/unit/test_guard_phase3.py only — no production caller.
--   emit_memory_skip_event(): called from tests/unit/test_guard_phase2.py only — no production caller.
--   Verified hook trace: runtime/hooks/meta/on-memory-retrieve.py does NOT import memory_taint;
--   runtime/hooks/meta/on-edit-dispatch.py does NOT call guard_delta_pairs.
--   DEAD — all three writers are test-only reachable.
--
-- Tables SKIPPED (3 candidates — live production writers; conservative batch):
--
-- guardrail_decisions — 3 live production paths:
--   (1) guardrails/evaluator.py::check_rubric_write_guardrail() → runtime/hooks/meta/on-edit-dispatch.py
--   (2) guardrails/evaluator.py::log_decision() → hooks/on-commit.py
--   (3) core/gates/rubric_immutability_gate.py::_record_decision() → canonical/workflows/pre-push.yaml
--   Classification: LIVE. Cannot drop without breaking the active guardrail system.
--
-- audit_runs — LIVE writer at projections/api/routes/audits.py:272 (POST /audits/runs route).
--   Architecture violation (projection write) but the feature is live. SKIP.
--
-- research_cache — LIVE writer at control/research/web.py:611 (via POST /api/discovery/research).
--   Architecture violation (projection write) but the route is live. SKIP.
--   (studio_db.py:1556 cache_research() function is dead but the table is live via web.py.)
--
-- Result: 76 - 4 = 72 tables.
-- Reviewed: 2026-06-28 (canonical-first migration, Batch 1)

-- compliance_review_flags — persist=False dead gate; no production writer reaches persist=True
DROP INDEX IF EXISTS idx_compliance_review_flags_project;
DROP TABLE IF EXISTS compliance_review_flags;

-- release_readiness_records — same persist=False dead gate as compliance_review_flags
DROP INDEX IF EXISTS idx_release_readiness_records_project;
DROP TABLE IF EXISTS release_readiness_records;

-- policy_decision_records — test-only writer record_policy_decision(); no production caller
DROP INDEX IF EXISTS idx_policy_decision_records_action;
DROP TABLE IF EXISTS policy_decision_records;

-- guard_events — all three writers (delta_guard.py, memory_taint.py) are test-only reachable;
--   no hook, CLI command, or projection imports or calls the public entry-point functions.
DROP INDEX IF EXISTS idx_guard_events_project;
DROP INDEX IF EXISTS idx_guard_events_type;
DROP INDEX IF EXISTS idx_guard_events_scan;
DROP TABLE IF EXISTS guard_events;
