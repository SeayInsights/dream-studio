# AI/Adapter Task Attribution And Outcomes

Lifecycle status: runtime_validated

Dream Studio records meaningful execution units in SQLite so operator views can
answer who did what work, which skills/workflows were involved, what changed,
which validation ran, what outcome occurred, and whether follow-up or rework is
needed.

## Authority Model

`task_attribution_records` is the current SQLite authority for task-level
attribution. It links, when known, to project, milestone, task, Work Order,
process run, execution event, adapter, AI provider/model, agent, skills,
workflows, hooks, tools, files touched, commands run, validations, security
impact, readiness impact, outcome, commit/PR/result refs, rework state, and
evidence refs.

The table is additive and does not replace existing authority:

- `execution_events` and `process_runs` remain the execution spine.
- `skill_invocations`, `workflow_invocations`, `hook_invocations`, and
  `tool_invocations` remain invocation facts.
- `validation_results`, `security_findings`, and production readiness records
  remain their own authority.
- `adapter_result_records` remains normalized adapter-result authority.
- `ai_usage_operational_records` and `token_usage_records` remain usage
  telemetry and do not become cost authority.

Dashboard/API surfaces read attribution as a derived view through
`core.shared_intelligence.task_attribution`.

## Honesty Rules

Attribution must not overclaim:

- unknown model/provider is stored as `unknown`;
- unavailable files or commands are stored as `unavailable` with a reason when
  possible;
- untracked or imported work is marked `untracked`, `imported_manual`, or
  `adapter_reported`;
- uncertain outcomes are marked `manual_review_required`;
- token and cost precision is not inferred from task attribution.

Plan/subscription adapters such as Claude Code subscription or Codex through a
ChatGPT plan can still have operational outcomes, but task attribution never
converts those runs into fake per-run dollar costs.

## Dashboard Surfaces

Task attribution is exposed through:

- `/api/shared-intelligence/task-attribution`;
- `/api/shared-intelligence/task-attribution/work-orders/{work_order_id}`;
- Project Details as `recent_attributed_work`;
- Adapter Usage through the `task_attribution` section of AI usage accounting;
- Capability Center skill/workflow outcome counts;
- Contract Atlas as `task_attribution_model`.

These are all derived views. They do not authorize execution, mutation,
cleanup, release, or adapter routing.

## Example

```json
{
  "task_id": "fix-dashboard-stale-project-rows",
  "adapter_id": "claude",
  "provider": "unknown",
  "model_id": "unknown",
  "skill_ids": ["ds-core", "ds-quality"],
  "workflow_ids": ["intentional_implementation_workflow"],
  "project_id": "dream-studio",
  "milestone_id": "dashboard_data_analytics_and_visual_modernization",
  "work_order_id": "wo-dashboard-modernization-001-data-truth",
  "files_touched": ["projections/api/routes/projects.py"],
  "validation_status": "passed",
  "outcome_status": "committed",
  "commit_refs": ["abc123"],
  "rework_needed": false,
  "security_impact": {"new_findings": 0},
  "readiness_impact": {"dashboard_authority": "improved"}
}
```

## Validation

Required validation proves:

- migration 045 creates `task_attribution_records`;
- attribution records persist to SQLite;
- Work Order and Project Details views expose adapter/skill/workflow/files,
  validations, outcome, rework, and security/readiness impact;
- Adapter Usage and Capability Center consume attributed outcomes without
  inventing token or cost precision;
- Contract Atlas and docs drift recognize the model.
## Platform Hardening Refresh

Platform-hardening policy, connector, privacy, watch, installer, and demo records can link back to task attribution through Work Orders, validation results, evidence refs, and adapter usage records. They do not replace the attribution model: AI/adapter work remains attributed through current SQLite authority, with unknown model, token, cost, files, or outcome fields shown honestly when unavailable.

## PRD Lifecycle Interaction

Project Details may show task attribution beside current PRD version,
milestone, active Work Order, change-order, and route reconciliation authority.
Task attribution does not own or rewrite PRD authority; it links outcomes back
to recorded Work Order or milestone identifiers when those IDs are available.

<!-- reviewed: 2026-05-30, migration 084 (project model unification A2). reg_projects deleted; business_projects is the sole project authority. Session hooks now use marker-based UUID resolution. No semantic changes to this document required. -->
