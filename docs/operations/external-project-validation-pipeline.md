# External Project Validation Pipeline

Lifecycle status: runtime_validated

Dream Studio can track external projects, but external targets are paused by
default. The pipeline is reusable and target-scoped: it plans intake,
validation, evidence, dashboard visibility, and commit boundaries without
opening, scanning, mutating, staging, committing, pushing, or deploying a target
repo.

## Default Registry

The default external target registry contains DreamySuite, Bill Stack, TORII,
and future projects as paused external targets. A target is not readable just
because it exists in the registry. Read-only intake requires an explicit current
operator selection for that target and scope.

Default policy:

- external targets start paused
- read access requires explicit current target selection
- mutation requires scoped approval
- commit requires validation evidence and a commit policy
- push and deploy require separate approval
- no stale external route may auto-resume from old state

## Pipeline Steps

The non-executing pipeline records the intended Work Order sequence:

1. capture target boundary
2. verify current target selection
3. classify dirty state
4. detect PRD and project status
5. discover stack/dependency evidence
6. classify security/readiness scope
7. select validation profile
8. verify approval scope
9. run read-only validation
10. record target repo mutation eval
11. record validation evidence
12. route next decision

These steps are planning authority only. The pipeline reports
`external_repo_inspected=false`, `external_repo_mutated=false`, and
`execution_allowed=false` until a later scoped Work Order authorizes real target
access.

## Evidence Separation

Private Dream Studio planning artifacts remain in Dream Studio SQLite or
operator-local `meta/` evidence. Target repos must not receive `.planning`,
Work Orders, handoffs, local evidence, backup dumps, SQLite databases, generated
runtime state, secrets, or private dogfood traces unless a later publication
policy explicitly approves a sanitized artifact.

## Dashboard Behavior

All Projects and Project Details may show a derived external target card with
paused status, dirty-state evidence, validation profile, risks, approval
requirements, and next action. The dashboard remains derived. It does not become
authority for resume, mutation, commit, push, or deploy approval.

## Validation

Static validation checks that:

- external projects default to paused
- read-only intake is gated by current target selection
- mutation, cleanup, push, and deploy are forbidden in the plan
- private target artifacts are excluded from target Git tracking
- Work Order evidence includes a target repo mutation evaluation
- dashboard cards are derived and non-authoritative
