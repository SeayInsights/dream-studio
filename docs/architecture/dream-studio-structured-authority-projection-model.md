# Dream Studio Structured Authority Projection Model

Lifecycle status: draft_generated

Authority role: structured authority projection contract

## Purpose

This model defines how Dream Studio projects authority state into file-backed
records that can later feed reports, continuation packets, dashboards, and
runtime surfaces without treating those surfaces as primary truth.

The projection layer is a derived view. It does not mutate runtime SQLite, run
migrations, execute DDL/DML, implement dashboard/API/runtime behavior, or resume
external projects.

## Source Authority

Primary authority comes from:

- PRD authority documents.
- Stage-gate authority documents.
- Milestone state and evidence artifacts.
- Work Order approval and decision artifacts.
- Validation evidence.
- Research evidence.
- Git metadata for committed work.
- Strategic constraints for paused external validation targets.

Reports, handoffs, continuation packets, and dashboard projections render from
that authority. They are not workflow authority.

## Projection Record Shape

Every projection record must include:

- `projection_id`
- `domain`
- `source_authority`
- `source_refs`
- `lifecycle_status`
- `authority_role`
- `derived_fields`
- `confidence`
- `stale_superseded_detection`
- `stop_gate_implications`
- `validation_requirements`
- `dashboard_readiness`

The required machine-readable contract lives in
`docs/architecture/dream-studio-structured-authority-projection-contract.yaml`.

## Domains

The first projection contract covers:

- PRD authority
- stage gates
- milestones
- Work Orders
- approvals
- operator decisions
- evidence
- validations
- artifacts
- research decisions
- handoffs
- commits
- paused external validation targets

## Lifecycle And Confidence

Projection records use explicit lifecycle states such as `active`,
`draft_generated`, `user_confirmed`, `superseded`, `stale`, `archived`,
`compacted`, `retained`, and `not_applicable`.

Confidence is `high`, `medium`, `low`, or `unknown`. Confidence is about the
projection's fitness as a derived view, not the truth of the underlying source.

## Stale And Superseded Detection

A projection is stale when its source refs, evidence refs, validation refs, or
git refs change after projection generation. It is superseded when a newer
projection record for the same domain and authority scope exists.

Stale or superseded projection records must not be used to route work without
refreshing from primary authority.

## Stop-Gate Implications

The projection contract carries stop-gate implications so downstream surfaces
can display why work can continue or why it must stop.

Examples:

- PRD or stage-gate changes require operator approval.
- Database mutation, migrations, DDL/DML, package operations, runtime/browser
  validation, and external project resume require separate approval.
- Failed validation routes to hard stop or handoff according to policy.
- Artifact compaction, deletion, or archive requires separate approval.
- Handoffs without valid stop/approval/transfer/export reasons fail validation.

## Dashboard Readiness

Dashboard readiness fields must say whether the record can be displayed, what
freshness label to show, whether action is required, and that the dashboard is
not primary truth.

Dashboard projections are derived views. They consume structured state and
evidence summaries; they do not own product, routing, database, or workflow
authority.

## Handoff Policy

Handoffs are rendered views from route decisions, evidence refs, validation
refs, and required operator actions. They are not the workflow engine.

Routine report writing, evidence creation, checklist review, artifact reads,
non-mutating validation, next-step existence, or next-milestone existence are
not valid handoff reasons.

## Validation

This milestone validates that required authority artifacts exist, projection
contracts contain source refs, dashboard projections are marked derived, handoffs
are not treated as workflow authority, and no forbidden runtime/database/source
control boundary was crossed.
