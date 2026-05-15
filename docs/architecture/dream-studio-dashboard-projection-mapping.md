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
- Module boundary contracts, install profile membership, disabled-module
  behavior, and empty-state policy
- AI adapter usage accounting, billing mode, token visibility, cost visibility,
  source confidence, and operational value telemetry
- Security lifecycle gate status and 47-control applicability
- Production readiness status, controls, scorecards, findings, and remediation Work Orders
- Project portfolio authority, PRD authority, security posture, readiness posture,
  health, blockers, remediation, and evidence refs for All Projects and Project
  Details
- Analytics-only profile status and normalized ingestion contract status

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

AI usage cards must distinguish token usage from reportable cost. If the source
records do not provide exact, provider-reported, explicitly estimated, or
allocated subscription cost evidence, dashboard cards must render `unknown` and
show operational value signals instead of fabricated dollar precision.

## Contract Atlas Projection

The Contract Atlas projection is exposed through
`/api/shared-intelligence/contract-atlas`; the major module contract subset is
also exposed through `/api/shared-intelligence/module-contracts`. Both are
dashboard-consumable derived views over repo-backed contract declarations,
major module contracts, telemetry module declarations, runtime profiles,
adapter projection state, and SQLite shared-intelligence authority.

The projection may display:

- whole-system, layer, module, interface, runtime profile, and adapter
  projection contracts;
- major module contract fields such as owned tables, read/write dependencies,
  profile membership, disabled-module behavior, and validation tests;
- docs freshness tracking and the release-gate drift policy;
- maturity scorecard;
- confirmed dependency graph;
- boundary violation report;
- current maturity ledger;
- contract/docs drift status;
- sanitized public export status.
- Contract Atlas lifecycle freshness status from
  `/api/shared-intelligence/contract-atlas/freshness`, including PRD/README
  impact detection and public-export leakage validation.

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

## Production Readiness Projection

The production readiness projection is exposed through
`/api/shared-intelligence/production-readiness`, the project detail route, and
SQLite-backed dashboard summaries. It displays secure production readiness
control coverage, project readiness score, separate project health score
inputs, findings, manual-review controls, not-applicable controls with reasons,
remediation Work Order candidates, release blockers, and compliance/legal review
flags when evidence supports them.

The dashboard must label partial or unavailable scores honestly. Missing
evidence is shown as missing evidence, not as a zero score. The projection may
read SQLite authority records but must not create fake findings or claim legal
or regulatory compliance.

## Project Portfolio Projection

All Projects and Project Details are the canonical operator-facing project
intelligence surfaces. They are still derived views: project authority remains
in SQLite/project records, PRD authority records, source repos, Contract Atlas
records, security/readiness authority, and evidence refs.

The default All Projects view includes only current legitimate projects. It
excludes temp, pytest, demo, placeholder, inactive/quarantined, adapter
scratch/worktree, missing-path, and legacy fallback rows. Excluded rows remain
retained or manual-review authority when the data cannot be safely removed, but
they must not contaminate normal operator views.

Project Details displays project identity/status, PRD status and summary,
stack/dependency evidence, security findings, 47-control coverage, production
readiness coverage, validation state, remediation Work Orders, health,
readiness, blockers, attention, evidence refs, manual-review items, known gaps,
and the current next action. Missing evidence must render as unavailable,
partial, manual-review, or honest empty state with a reason.

Project Details is also the main architecture and stack operating view. The
`/api/v1/projects/{project_id}/details` response includes safe read-only stack
evidence for package manifests, config files, API route files, frontend
surfaces, CI workflows, migrations, skills, hooks, and adapter projections. It
records source refs and manifest dependency names, but it does not inspect
secrets, mutate repos, or promote manifest-derived dependencies to confirmed
graph edges.

PRD dashboard data is not a disconnected primary tab. PRD status is part of the
project authority surface. Existing PRD files may be read and summarized when
safe; missing PRDs become draft-generated authority status with explicit
unknowns and manual-review flags rather than invented claims.

Security findings may use narrow high-confidence alias mapping, such as
`project_<project_id_with_underscores>` for legacy migrated rows. Findings that
cannot be mapped to a current project remain retention-only or manual-review
items outside default cards. Synthetic, test, temp, and demo findings must not
appear in live operator views.

Knowledge Graph and stack/dependency displays must use confirmed evidence from
current dependency records, repo/config files, routes, migrations, APIs,
workflows, hooks, skills, adapters, CI/CD files, telemetry, or artifact refs. If
confirmed evidence is absent, the projection reports unavailable and must not
draw placeholder nodes or inferred edges.

Dependency visualization separates confirmed edges from `pi_dependencies`,
inferred or unverified manifest-derived dependencies, and unavailable states.
Only confirmed persisted edges are rendered by default. Inferred/unverified
dependencies are labeled separately and hidden by default. The drilldown path is
project -> stack component -> dependency edge -> source/evidence refs.

## Analytics-Only Projection

The analytics-only projection is exposed through
`/api/shared-intelligence/analytics-only`, All Projects, Project Details,
metrics routes, security routes, token/model analytics, and production
readiness summaries.

It may display normalized imported facts from current SQLite authority tables:
projects, CI/validation results, security findings, token usage, AI operational
usage, components, dependencies, PRD authority, and readiness scorecards.

The dashboard must distinguish dry-run ingestion planning from executed imports.
Missing sections stay honest empty states. It must not require hooks, agents,
workflows, Claude, Codex, Docker, repo mutation, or full orchestration to render
analytics-only views.

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
