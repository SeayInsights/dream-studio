# Dream Studio Artifact Requirements

Status: draft_generated
Authority role: artifact requirement and lifecycle policy

## Progressive Artifact Policy

Dream Studio starts each project with compact structured authority instead of a
large document set. Unknown, assumed, deferred, not_applicable,
blocking_unknown, and operator_decision_required are valid states.

Default project authority artifacts:

- project_authority.yaml
- open_questions.yaml
- decisions.yaml
- artifacts_index.yaml

## When Full Documents Are Required

Full documents are generated only when required by phase, risk, release,
portfolio, client work, enterprise audit, regulatory concern, architecture
change, security decision, deployment decision, or operator request.

## Artifact Requirement Matrix

| Work type | Lightweight authority enough | Full artifact required when |
| --- | --- | --- |
| Goal intake | project_authority.yaml | Scope, client, release, or strategic direction must be confirmed |
| Product planning | PRD fields in authority profile | Product goal, non-goal, or success criteria drive implementation |
| SOW/client work | decision refs and assumptions | External commitment, price, deadline, deliverable, or acceptance gate exists |
| Architecture | architecture notes | System boundary, source of truth, data model, or integration changes |
| ERD/data model | relationship refs | Database/schema/projection/migration/dashboard data work is in scope |
| UI/UX | brief and references | User-facing surface, Figma handoff, accessibility, or design system decision |
| Stack | stack labels | New runtime, dependency, tool, provider, or deployment surface is proposed |
| Security | finding refs and gate | Release, secrets, auth, permissions, compliance, or vulnerability work exists |
| Deployment | environment notes | Push/deploy/rollback/hosting/cloud/org/global operation is proposed |

## Unknown And Deferred Answer Policy

Unknown answers do not block the whole project. They block only the milestone or
phase where the answer materially affects outcome, safety, scope, or authority.
Deferred and not_applicable values must carry rationale.

## Draft Generated Policy

Generated documents are draft_generated until reviewed or confirmed. A generated
document may guide planning but cannot override PRD, stage-gate, approval, or
structured state authority.

## Artifact Roles

- canonical_structured_state
- evidence
- rendered_view
- export
- attachment
- retained_raw_evidence
- archive_candidate
- compacted_summary
- generated_prompt
- generated_report

## Lifecycle Statuses

- active
- draft_generated
- user_confirmed
- superseded
- stale
- archived
- compacted
- retained
- not_applicable

## Blocking Rules

Artifacts block a milestone only when they are required by the active stage gate,
stop gate, approval policy, validation requirement, rollback requirement, or
operator decision. Artifact compaction, deletion, or archive execution always
requires separate approval.
