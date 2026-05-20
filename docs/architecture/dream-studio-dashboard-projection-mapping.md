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

The installed dashboard command surface is part of the projection boundary:
`ds dashboard --status` reports readiness, `--serve` starts the local FastAPI
server, `--open` starts or reuses the server and opens a browser, and `--check`
validates `/dashboard` and `/api/health`. These modes expose derived views and
must not bootstrap SQLite, migrate schemas, backfill facts, or become primary
authority.

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
- AI/adapter task attribution, skill/workflow usage, files touched, validation,
  execution outcome, rework status, and security/readiness impact
- Platform-hardening status for skill evaluation, policy decisions, connectors,
  privacy/redaction, opt-in watchers, team rollups, installer checks, and
  sanitized demo/case-study packets
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

Task attribution cards must distinguish observed facts from unknowns. If
model/provider, files touched, commands, validation, or outcome details are
unavailable, the dashboard must show `unknown`, `unavailable`, or
`manual_review_required` rather than filling placeholders. Attribution cards
read `task_attribution_records` and related current authority tables; they must
not use adapter-private memory or reports as primary truth.

## Operator Story Map

The dashboard should read as an operator story, not as a collection of internal
tables. The first screen should answer: is Dream Studio healthy, what needs
attention, what changed recently, which projects are active, what is blocked or
manual-review, and what is the next safe action. Drilldowns then explain the
evidence, controls, adapters, workflows, and contracts behind those answers.

Recommended top-level structure:

| Area | Operator question | Source routes | Authority | Current decision |
|------|-------------------|---------------|-----------|------------------|
| Overview | Is Dream Studio healthy, what changed, and what needs attention now? | `/api/telemetry/*`, `/api/shared-intelligence/*`, `/api/v1/projects` summaries | SQLite telemetry, project authority, adapter/router profiles, Contract Atlas read models | Keep as home; reduce detail cards and link to focused areas |
| Project Details | What is true for this project, and what is the next safe action? | `/api/v1/projects/{id}/details`, `/health`, `/prds`, `/security`, `/dependencies`, `/activity` | project authority, PRD authority, security/readiness records, dependency evidence, task attribution | Keep as the main operating view |
| Security/Readiness | What controls, findings, blockers, and remediation exist? | `/api/v1/security/*`, `/api/v1/audits/*`, shared-intelligence readiness routes | security findings, 47-control applicability, readiness controls, audit records | Keep; merge overlapping audit/status cards |
| Adapter/AI Usage | Which AI/adapter did what work, with what outcome and evidence? | `/api/shared-intelligence/ai-usage-accounting`, `/task-attribution`, metrics model routes | adapter accounting profiles, task attribution, process/validation records | Promote from scattered model/telemetry cards |
| Capability Center | Which skills, workflows, agents, controls, and evaluations are active? | `/api/shared-intelligence/capability-center`, expert workflow and agent routes | skill/workflow/agent/control authority and evaluation records | Move Skills, Workflows, Learning, and agent details here |
| Contract Atlas | What contracts, docs, exports, and maturity records are current? | `/api/shared-intelligence/contract-atlas`, `/module-contracts`, `/contract-atlas/freshness` | repo contracts, maturity ledger, docs/export freshness records | Keep as system-maturity drilldown |
| Evidence | What proves recent outcomes? | task attribution, validation, artifacts, attention, and evidence routes | evidence refs, validation results, artifacts, process runs | Add as focused drilldown when evidence volume grows |
| Advanced | What low-level telemetry is useful for maintainers? | hooks, anomalies, analytics insights, raw alert routes | hook/tool invocations and advisory analytics records | Hide by default; keep for debugging |

Current area classification:

- `Projects` is current and belongs in Overview summaries plus Project Details.
- `Project Details` is current and should absorb PRD, stack, security,
  readiness, recent activity, task attribution, and next-action explanations.
- `Security` is current but should be framed as Security/Readiness, with audit
  drilldowns kept secondary.
- `Skills`, `Workflows`, and `Learning` are useful but belong in Capability
  Center rather than primary navigation.
- `Models` belongs under Adapter/AI Usage and must preserve honest token/cost
  visibility.
- `Hooks`, `Alerts`, `ML`, `Anomalies`, and `/api/v1/insights/` are advanced
  or advisory surfaces. They should not be required for the operator's first
  dashboard story.
- The standalone `PRD` tab duplicates project authority. Keep PRD status inside
  Project Details; retain a filtered PRD authority list only if it proves useful.
- `Knowledge Graph` should remain hidden or project-scoped until confirmed
  dependency evidence is sufficient. It must not render placeholder graph data.

Immediate safe fixes are reliability and labeling fixes only: dashboard smoke
coverage should include active frontend routes such as `/api/v1/insights/`, and
routes that cannot produce current authority data should return honest empty or
unavailable states instead of 500s. Larger IA changes belong in a separate
bounded dashboard story implementation Work Order.

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
- GitHub CI/CD profile status from the Contract Atlas `github_cicd_profile`
  section, including lightweight PR smoke, manual full CI, manual/tag release
  validation, local heavy-gate authority, and unavailable-Actions manual-review
  policy.
- Expert workflow status from the Contract Atlas `expert_workflow_system`
  section and the full `/api/shared-intelligence/expert-workflows` catalog,
  including overlap decisions, evidence-backed scoring rubrics, career privacy
  boundaries, application automation rules, and existing skill/workflow owners.
- PRD lifecycle status from the Contract Atlas `prd_authority_lifecycle`
  section and `/api/shared-intelligence/prd-authority`, including current PRD
  version, lifecycle status, confidence, milestone authority, Work Order
  authority, change-order state, route reconciliation, and next safe action.

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

Project Details also exposes the structured PRD lifecycle read model:
`prd_lifecycle_authority`, `prd_version`, `prd_confidence`,
`in_flight_formalization_status`, `pending_prd_questions`,
`prd_assumptions`, `current_milestones`, `active_work_orders`,
`change_order_history`, `pending_change_orders`,
`route_reconciliation_status`, and `planned_vs_actual_route_summary`. These
fields are derived from SQLite lifecycle tables and are meant to help an
operator or adapter continue from current authority instead of prior chat
memory.

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

Installer, update, and legacy migration state is shown only as derived status.
Dashboard/API surfaces may summarize that a legacy install was detected, that a
dry-run migration plan exists, or that rollback/adapter repair checks are
available, but they must not become the authority for executing migration,
repair, cleanup, restore, or deletion. Raw backup paths, old launcher contents,
Claude/Codex config values, and legacy file-sprawl inventories stay private.

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

## Capability And Career Projections

`/api/shared-intelligence/career-ops` is a private dashboard module. It shows
whether Career Ops is enabled, profile/application/evidence/scorecard counts,
application automation boundaries, and evidence-backed or unavailable
scorecards. It does not expose career records in public exports.

`/api/shared-intelligence/capability-center` displays skills, workflows,
agents, controls, evaluations, and hardening candidates from authority-backed
records. If invocation or evaluation evidence is missing, sections report
unavailable or empty states with reasons.

`/api/shared-intelligence/agents/registry` and
`/api/shared-intelligence/agents/context-packet` expose scoped worker-agent
contracts and context previews. They do not authorize agent execution and they
exclude full conversation history, secrets, unrelated project data, and private
career data unless explicitly scoped.

`/api/shared-intelligence/github-repo-intake` exposes the repo intake workflow
and recorded evaluation summaries. It is a read model over SQLite authority and
does not fetch, copy, fork, vendor, mutate, or adopt external repositories.

`/api/shared-intelligence/platform-hardening` exposes the next product-hardening
sequence. It is a read model over SQLite authority and repo declarations for
skill evaluations, policy decisions, engineering connectors, privacy/redaction,
local watchers, team rollups, installer/distribution checks, and demo packets.
It does not authorize execution, cleanup, live SQLite mutation, external
project mutation, Docker execution, push/deploy, secret inspection, or public
publication.

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

<!-- Last reviewed 2026-05-20 — repo-wide `py -m black .` formatting applied; no behavior or policy change required here. -->

<!-- Last reviewed 2026-05-20 — pipeline optimization landed (migration 057 extends ds_work_order_types with workflow_template, precondition_skill, task_generator, resolution_instructions; CLI gains `ds project state` single-query, auto-advance, gotcha injection, brief mode); doc policy unchanged here. -->

<!-- Last reviewed 2026-05-20 — A1 extraction: 22 CLI handlers refactored into importable functions under core/projects, core/work_orders, core/design_briefs, core/milestones, core/skills, core/health. ds.py wrappers are now thin (call function, print result, return exit code). No policy or contract change in this doc. -->

<!-- Last reviewed 2026-05-20 — A2.1: `_work_order_start` decomposed into `read_work_order_brief`, `write_work_order_context`, `start_work_order` under `core/work_orders/start.py`. Stdin y/N prompt removed from the pure path; CLI wrapper preserves the legacy stderr warning + non-TTY auto-accept for operator terminals. No policy or contract change here. -->

<!-- Last reviewed 2026-05-20 — A2.2: `_work_order_close` decomposed into `run_gate_check`, `check_close_gates`, `close_work_order` under `core/work_orders/close.py`. `_run_gate_check` lifted out of `interfaces/cli/ds.py`; `core/projects/queries.py` now imports the predicate directly. CLI wrapper re-emits `[gate.bypassed] WARNING:` to stderr from the returned `bypassed_gates` list for operator-terminal parity. No policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — A2.3: `_project_start` decomposed into the `start_project` composer under `core/projects/start.py`, which orchestrates `set_active_project` (mutations) + `get_next_work_order` (queries) + `start_work_order` (work_orders/start). CLI wrapper converts the compound result dict into the legacy operator-facing summary; no policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — A2.4: `_skill_invoke` (heaviest CLI handler) decomposed into `load_skill_content` + `record_skill_invocation` + `seed_gate_artifact_files` under `core/skills/invocation.py`. Duplicate `_load_packs` / `_SKILL_SPECIFIER_RE` / `_SKILL_FM_RE` removed from `interfaces/cli/ds.py`; the canonical `_load_packs` lives in `core/skills/queries.py`. Phase A3 workflow runner can now compose these three functions directly. No policy or contract change here. -->