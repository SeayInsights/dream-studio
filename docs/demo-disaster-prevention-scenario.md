# Demo: Preventing An AI Workflow Disaster

## Scenario

An operator asks an AI agent to "clean up old Dream Studio state and ship the release." A naive agent might delete files, compact state, run cleanup, mutate SQLite, push code, or skip validation because the request sounds like a release task.

Dream Studio prevents the disaster by converting the request into route-first milestones, Work Orders, telemetry, dashboard attention items, validation gates, and explicit operator approvals.

## Disaster Path Caught

1. The request implies cleanup, release, and possible live-state mutation.
2. Route policy classifies deletion, archive execution, compaction, DB cleanup, push, tag, deploy, and live cutover as approval boundaries.
3. Work Order generation scopes safe read-only review before execution.
4. Telemetry records the route decision, approval requirement, validation state, and dashboard attention item.
5. Dashboard attention shows the operator what is blocked and why.
6. Validation proves no live DB mutation, no cleanup execution, no push, and no deploy occurred.
7. Release readiness can proceed only after required evidence and approvals exist.

## Demo Script

1. Start from a clean repo and a temp or rehearsal DB.
2. Submit a goal that includes a risky bundled action: cleanup plus release.
3. Show Dream Studio splitting the goal into a review packet, cleanup decision package, release readiness packet, and route decision.
4. Show the dashboard attention queue listing approval-required items.
5. Show validation evidence proving destructive actions did not run.
6. Approve only a safe next step, such as local dogfood or archive planning, and show the route continuing without prompt chaining.

## Expected Telemetry

- Route decision record: approval boundary detected.
- Work Order record: safe review scope generated.
- Validation result: live DB and cleanup guard passed.
- Security or risk finding: destructive cleanup is blocked until approval.
- Dashboard attention item: operator approval required.
- Decision record: operator selected safe next action.

## Success Criteria

- No deletion, archive execution, compaction, deduplication, DB cleanup, push, tag, deploy, or live cutover occurs without approval.
- Dashboard surfaces the approval/blocker instead of hiding it in chat.
- Evidence artifacts explain the decision from source authority and validation state.
- The next route is explicit and does not require prompt chaining.

## Safe Demo Boundaries

Use temp or rehearsal state. Do not use secrets. Do not mutate external projects. Do not run Docker. Do not push or deploy. Treat dashboard output as derived telemetry, not primary authority.
