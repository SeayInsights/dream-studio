-- Migration 135: backfill eval + decision history into business_canonical_events
-- (WO-DBA-EVAL-DECISION T3)
--
-- Target architecture: studio.db = canonical EVENTS + non-event-sourced AUTHORITY
-- + pipeline ONLY. Eval runs and decisions are events, attached to business
-- entities where the source rows allow it. This migration copies history from
-- ds_eval_runs / hook_eval_runs / decision_log (+ decision_event_link) into the
-- canonical stream so those tables can be dropped once their writers and readers
-- are repointed (T4). Live emission starts in the same change set
-- (core/work_orders/verify.py, core/eval/runner.py, guardrails/evaluator.py,
-- core/decisions/emitter.py emit through the spool → ingestor path).
--
-- Idempotent: deterministic backfill event_ids + INSERT OR IGNORE.
-- work_order_id resolution: ds_eval_runs carries only the 8-char short id inside
-- eval_id ('work_order_verify:<short>' / 'outcome:<short>'); resolved by prefix
-- join against business_work_orders. Unresolvable rows keep work_order_id NULL.

-- ── ds_eval_runs: work-order verification verdicts ──────────────────────────
INSERT OR IGNORE INTO business_canonical_events
    (event_id, received_at, event_type, event_timestamp, schema_version,
     trace, payload, correlation_id, project_id, milestone_id, work_order_id,
     task_id, severity, source)
SELECT
    'backfill-135-evalrun-' || r.run_id,
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
    'work_order.verified',
    COALESCE(r.completed_at, r.started_at, r.created_at),
    1,
    json_object('domain', 'sdlc', 'backfill', 'migration-135',
                'work_order_id', wo.work_order_id, 'project_id', wo.project_id,
                'milestone_id', wo.milestone_id),
    json_object('run_id', r.run_id, 'eval_id', r.eval_id,
                'completion_score', r.event_score, 'correctness_score', r.behavior_score,
                'composite_score', r.total_score, 'passed', r.passed,
                'failure_reasons', r.failure_reasons, 'run_mode', r.run_mode,
                'started_at', r.started_at, 'completed_at', r.completed_at),
    NULL,
    wo.project_id,
    wo.milestone_id,
    wo.work_order_id,
    NULL,
    'info',
    'migration-135-backfill'
FROM ds_eval_runs r
LEFT JOIN business_work_orders wo
    ON substr(wo.work_order_id, 1, 8) = substr(r.eval_id, instr(r.eval_id, ':') + 1, 8)
WHERE r.eval_id LIKE 'work_order_verify:%';

-- ── ds_eval_runs: harness + outcome eval runs ───────────────────────────────
INSERT OR IGNORE INTO business_canonical_events
    (event_id, received_at, event_type, event_timestamp, schema_version,
     trace, payload, correlation_id, project_id, milestone_id, work_order_id,
     task_id, severity, source)
SELECT
    'backfill-135-evalrun-' || r.run_id,
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
    'eval.run.completed',
    COALESCE(r.completed_at, r.started_at, r.created_at),
    1,
    json_object('domain', 'telemetry', 'backfill', 'migration-135',
                'work_order_id', wo.work_order_id),
    json_object('run_id', r.run_id, 'eval_id', r.eval_id, 'eval_version', r.eval_version,
                'model_tested', r.model_tested, 'event_score', r.event_score,
                'behavior_score', r.behavior_score, 'total_score', r.total_score,
                'passed', r.passed, 'failure_reasons', r.failure_reasons,
                'run_mode', r.run_mode, 'baseline_run_id', r.baseline_run_id,
                'started_at', r.started_at, 'completed_at', r.completed_at),
    NULL,
    wo.project_id,
    wo.milestone_id,
    wo.work_order_id,
    NULL,
    'info',
    'migration-135-backfill'
FROM ds_eval_runs r
LEFT JOIN business_work_orders wo
    ON r.eval_id LIKE 'outcome:%'
   AND substr(wo.work_order_id, 1, 8) = substr(r.eval_id, instr(r.eval_id, ':') + 1, 8)
WHERE r.eval_id NOT LIKE 'work_order_verify:%';

-- ── hook_eval_runs: guardrail hook evals ────────────────────────────────────
INSERT OR IGNORE INTO business_canonical_events
    (event_id, received_at, event_type, event_timestamp, schema_version,
     trace, payload, correlation_id, project_id, milestone_id, work_order_id,
     task_id, severity, source)
SELECT
    'backfill-135-hookrun-' || h.run_id,
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
    'eval.run.completed',
    h.created_at,
    1,
    json_object('domain', 'telemetry', 'backfill', 'migration-135', 'hook_id', h.hook_id),
    json_object('run_id', h.run_id, 'eval_id', 'hook:' || h.hook_id,
                'eval_type', h.eval_type, 'score', h.score, 'passed', h.passed,
                'failure_reasons', h.failure_reasons),
    NULL, NULL, NULL, NULL, NULL,
    'info',
    'migration-135-backfill'
FROM hook_eval_runs h;

-- ── decision_log (+ event links): decision transparency records ─────────────
INSERT OR IGNORE INTO business_canonical_events
    (event_id, received_at, event_type, event_timestamp, schema_version,
     trace, payload, correlation_id, project_id, milestone_id, work_order_id,
     task_id, severity, source)
SELECT
    'backfill-135-decision-' || d.decision_id,
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
    'decision.recorded',
    d.timestamp,
    1,
    json_object('domain', 'sdlc', 'backfill', 'migration-135',
                'source_subsystem', d.source_subsystem),
    json_object('decision_id', d.decision_id, 'decision_type', d.decision_type,
                'context', d.context, 'outcome', d.outcome, 'reasoning', d.reasoning,
                'confidence', d.confidence, 'policy_applied', d.policy_applied,
                'source_subsystem', d.source_subsystem,
                'triggered_event_id', l.event_id),
    NULL, NULL, NULL, NULL, NULL,
    'info',
    'migration-135-backfill'
FROM decision_log d
LEFT JOIN decision_event_link l ON l.decision_id = d.decision_id;
