# PRD Authority Lifecycle

Dream Studio treats PRD authority as the starting point and continuing product
authority for every legitimate project. A project should not drift forward only
through chat context. Current PRD version, milestones, Work Orders, change
orders, route decisions, evidence, validation, and reconciliation records must
be enough for a supported adapter to continue safely from Dream Studio
authority.

## Authority Boundary

SQLite is the durable authority for PRD lifecycle state. Files are optional
exports.

Primary tables:

- `project_intake_records`
- `project_intake_questions`
- `project_assumption_records`
- `prd_version_records`
- `project_milestone_records`
- `project_work_order_authority_records`
- `project_change_order_records`
- `prd_amendment_records`
- `prd_route_reconciliation_records`

Legacy `prd_documents` remains a compatibility list surface. It is not enough
by itself to express version lineage, change orders, milestone impact, or route
reconciliation.

## Project Intake

New project work starts with a structured intake plan, not immediate code.
Question modes are:

- `quick_start`: ask only critical blockers not already answered.
- `standard_discovery`: ask important product, architecture, security, and
  release questions that are still missing.
- `full_discovery`: ask deeper planning questions.
- `import_existing_project`: inspect approved existing evidence first, then ask
  only gaps.

Questions are grouped by product purpose, target users, core use cases, goals,
non-goals, MVP scope, data/storage needs, security/privacy sensitivity,
integrations, AI/tool/model needs, frontend/backend/database needs,
deployment/release expectations, timeline/priority, success criteria,
constraints, risks, and desired autonomy level.

Answered groups become explicit assumptions. Missing groups become explicit
unknowns or operator-confirmation items. Dream Studio may infer safe
non-critical assumptions, but unsupported PRD claims must stay marked as
unknown, assumption, needs-evidence, or operator-confirmation-required.

## PRD Lifecycle

Lifecycle states are:

- `draft_generated`
- `in_flight_formalization`
- `user_review_required`
- `user_confirmed`
- `current`
- `needs_update`
- `superseded`
- `manual_review_required`
- `closed_reconciled`

For in-flight projects, Dream Studio formalizes PRD authority from current
evidence such as the project registry, existing PRD rows, approved repo/docs
metadata, route decisions, validation evidence, security/readiness records,
stack/dependency evidence, and Contract Atlas state. External project PRD files
are never written without scoped approval; Dream Studio stores authority in
SQLite first.

## Milestones And Work Orders

After PRD creation or formalization, Dream Studio creates ordered milestone
authority:

1. Intake / formalization
2. Architecture / data model
3. Core implementation
4. UI / UX / design
5. Security / readiness
6. Validation
7. Release / demo / deployment
8. Documentation / cleanup
9. Closeout / reconciliation

Milestones declare stage gates, validation expectations, security/readiness
checks, rollback strategy, evidence requirements, and adapter context
requirements. Work Order authority records are generated from milestones and
include purpose, scope, approved surfaces, dependencies, validation, evidence,
stop gates, final verdict taxonomy, route-decision expectations, and rollback.

## Change Orders

Material changes to project authority create `project_change_order_records`
instead of silently overwriting PRD, milestone, Work Order, security/readiness,
architecture, or release assumptions.

Change types include scope additions/reductions, requirement changes,
architecture changes, data model changes, security/privacy changes,
integration changes, UI/design changes, release target changes, priority
changes, assumption changes, non-goal changes, milestone replans, and
manual-review items.

Material changes require operator approval when they affect security/privacy,
database/schema, integrations, release/deployment, major architecture,
cost/usage, scope/timeline, public/private boundaries, legal/compliance
assumptions, milestone sequence, or destructive/risky work. Small
non-material edits may be auto-approved by policy, but they still produce
lightweight PRD amendment or change-order authority.

## Route Reconciliation

At milestone, release, or project closeout, Dream Studio records planned vs
actual route reconciliation. The reconciliation links intended route, actual
route, completed milestones, completed Work Orders, approved change orders,
validation results, security/readiness outcomes, accepted deviations,
unresolved deviations, final/current product state, and next action.

The PRD can be updated to reflect current product authority while detailed
route history stays linked through change-order, reconciliation, and evidence
records.

## Dashboard And Context Packets

Project Details exposes PRD status, version, confidence, formalization status,
pending questions, assumptions, milestones, active Work Orders, change-order
history, pending change orders, route reconciliation status, planned-vs-actual
summary, and next safe action.

Context packets include current PRD version, current milestone, active Work
Order, assumptions, known unknowns, relevant change orders,
security/readiness constraints, evidence refs, allowed scope, validation
expectations, and stop gates. Packets must not include unrelated project
history, full private operational history, career data, secrets, or raw local
evidence unless explicitly scoped.

## Autonomous Continuation

Dream Studio may continue through safe milestones when the operator asks it to
continue, go, build, or use reasonable assumptions. It must stop for destructive
data changes, external project mutation, push/tag/merge/deploy, secret or
sensitive access, unclear critical product direction, high-risk
security/compliance uncertainty, dependency/package changes without approval,
legal/regulatory uncertainty, user identity/private data risks, major
architecture changes, public/private boundary changes, and policy-defined
approval boundaries.
