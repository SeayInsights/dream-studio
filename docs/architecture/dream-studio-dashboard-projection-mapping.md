# Dream Studio Dashboard Projection Mapping

Lifecycle status: draft_generated

Authority role: dashboard projection mapping

## Purpose

This document defines dashboard-ready projections for Dream Studio's structured
authority state. It is a file-backed mapping contract, not dashboard/API/runtime
implementation.

Dashboard projections are derived views and are not primary truth. They display
state from PRD authority, stage gates, milestone state, Work Orders, approvals,
operator decisions, evidence, validations, artifact lifecycle records, research
decisions, route decisions, commits, and paused external validation targets.

Handoffs and continuation packets are rendered views from route decisions and
evidence references. They are not workflow authority.

The machine-readable mapping lives in
`docs/architecture/dream-studio-dashboard-projection-mapping.yaml`.

## Projection Domains

The dashboard mapping covers:

- Current product authority
- Current stage gate
- Current milestone
- Milestone sequence
- Work Order status
- Approvals
- Operator decisions
- Evidence coverage
- Validation status
- Artifact lifecycle status
- Research decision status
- Handoff and continuation status
- Commit status
- Paused external validation targets
- Contract Atlas status and boundary violations
- Installed adapter router status and module/profile health
- Security lifecycle gate status and 47-control applicability

## Required Mapping Fields

Each dashboard projection mapping includes:

- projection name
- source authority
- source refs
- derived fields
- display fields
- freshness and staleness logic
- lifecycle status
- confidence
- action required flag
- operator action required flag
- stop gate active flag
- handoff required flag
- continuation packet allowed flag
- dashboard readiness
- validation requirements
- explicit primary-truth warning

## Dashboard Readiness

Dashboard readiness tells a future dashboard whether a projection is visible,
which status to display, what freshness label to show, whether action is
required, and how to warn that the dashboard is a derived view.

The dashboard must not use a projection as primary truth for routing, database
authority, approvals, or source-control decisions. It must route operators back
to the source authority refs when a decision matters.

## Contract Atlas Projection

The Contract Atlas projection is exposed through
`/api/shared-intelligence/contract-atlas`. It is a dashboard-consumable derived
view over repo-backed contract declarations, module declarations, runtime
profiles, adapter projection state, and SQLite shared-intelligence authority.

The projection may display:

- whole-system, layer, module, interface, runtime profile, and adapter
  projection contracts;
- docs freshness tracking and the release-gate drift policy;
- maturity scorecard;
- confirmed dependency graph;
- boundary violation report;
- current maturity ledger;
- contract/docs drift status;
- sanitized public export status.

It must not authorize adapter execution, policy mutation, cleanup, database
writes, release actions, or public export of private local state.

## Installed Adapter Router Projection

The installed adapter router projection is exposed through
`/api/shared-intelligence/adapter-router`. It is a dashboard-consumable derived
view over installed runtime paths, adapter access modes, adapter projection
health, module profiles, and shared-intelligence capabilities.

The projection may display route state, skills/workflow/hook availability,
telemetry/evidence/context-packet capability status, Contract Atlas query
availability, dashboard attention, and current module/profile health. It must
show unsupported or context-packet-only adapters honestly and preserve the
Claude/Codex live-consumption caveats recorded by validation evidence.

It must not start services, execute hooks, mutate adapter configs, write live
SQLite, clean worktrees, inspect secrets, or treat the dashboard as primary
authority.

## Security Lifecycle Projection

The security lifecycle projection is exposed through
`/api/shared-intelligence/security-lifecycle`. It is a dashboard-consumable
derived view over the 47 enterprise security controls, the security review
crosswalk, the structured scan catalog, open security findings, and the current
lifecycle event or changed-file signal.

The projection may display applicable controls, not-applicable reasons,
manual-review controls, unknown controls, required finding fields, security
skill/control mapping, project health effect, and release-readiness effect. It
must not run scans, inspect secrets, mutate repositories, write SQLite, or show
synthetic/demo findings in live operator views.

## Freshness And Staleness

Projection records are stale when their source refs, evidence refs, validation
refs, milestone state, route decision, or git state change after projection
generation.

Projection records are superseded when a newer projection exists for the same
domain and authority scope.

Stale or superseded records may be displayed with warnings, but they must not be
used to continue work without refreshing from primary authority.

## Stop-Gate Fields

Every mapping includes:

- `action_required`
- `operator_action_required`
- `stop_gate_active`
- `handoff_required`
- `continuation_packet_allowed`

These fields make stop gates visible without making the dashboard the stop-gate
authority. The milestone router remains the transition authority.

## Handoff And Continuation Status

The handoff/continuation projection displays route decisions and whether a
handoff or continuation packet exists. It must never treat a handoff as the
workflow engine.

Routine report writing, evidence creation, checklist review, artifact reads,
package review, non-mutating validation, next-step existence, and next-milestone
existence are not valid handoff reasons.

## Boundary

This milestone creates mapping contracts only. It does not implement dashboard,
API, runtime, database, migration, package, external project, staging, commit,
push, deploy, archive, compaction, or cloud/org/global behavior.

## Next Route On Success

```yaml
route_decision: start_next_milestone
handoff_required: false
operator_action_required: false
next_stage_gate: structured_authority_projection
next_milestone: runtime_projection_update
recommended_next_work_order: none
```
