# Dream Studio Definition Of Done

Status: draft_generated
Authority role: completion criteria

## PRD Done

- Product identity, goals, non-goals, active objective, strategic constraints,
  success criteria, and end-to-end loop are explicit.
- Stage gates can route milestones from PRD authority.
- Unknown/deferred/not_applicable items are marked with rationale.

## Milestone Done

- Completion criteria are met.
- Internal steps are complete or explicitly deferred.
- Stop gates encountered are resolved or recorded.
- Evidence, validation, approval, rollback, and artifact refs are linked.
- Handoff is generated only when policy requires it.

## Work Order Done

- Scope stayed within approval mode and approved files.
- Required first action and approval artifact rules were followed.
- Evidence and validation were recorded.
- Boundary confirmation is explicit.
- Final verdict maps to the Work Order decision taxonomy.

## Research Done

- Research decision class is recorded.
- Question, sources, source summaries, confidence, relevance, decision impact,
  operator verification requirement, and evidence refs are captured.
- High-risk or source-uncertain conclusions were routed to the operator.

## Mutation Done

- File-backed approval exists before mutation.
- Changed files are wholly inside approved_files.
- Before/after state, diff-name evidence, and focused validation are captured.
- Rollback strategy is clear for the current slice.

## Database Authority Done

- Runtime SQLite mutation or migration had explicit approval.
- Backup, restore rehearsal, schema fingerprint, validation, and rollback
  evidence exist when mutation risk requires them.
- Sensitive values were not extracted.

## Dashboard Done

- Dashboard consumes structured state or projection data.
- Dashboard does not become primary truth.
- Runtime/browser/API validation is performed only when approved for that
  milestone.

## Handoff Done

- Handoff exists only for an approved handoff reason.
- Routine planning/report/evidence/checklist/package completion or a default
  next Work Order recommendation is not an approved handoff reason.
- Fresh-session rule, prior attempt/outcome, authority refs, stop reason,
  allowed/forbidden actions, evidence requirements, validation requirements,
  and final response requirements are present.
- Route decision, handoff reason, stop gate, why internal continuation is not
  allowed, required operator action, authority refs, evidence refs, validation
  refs, and next allowed action after approval are present.
- Generated handoff self-validation passes before ready.

## Artifact Done

- Artifact role and lifecycle status are explicit.
- Source authority and evidence refs are linked.
- Generated artifacts remain draft_generated until reviewed or confirmed.
- Compaction/deletion/archive is not executed without separate approval.

## Commit Done

- Commit phase is separately approved.
- Exact files are staged.
- Cached diff name-only/stat/check evidence is captured.
- No push occurs unless a later Work Order explicitly approves it.

## End-To-End Dream Studio Done

An operator can provide a goal; Dream Studio can plan milestones, orchestrate AI
work, research when needed, validate outputs, record evidence, stop at human
gates, render compact reports/handoffs, update projections, and resume without
chat memory while preserving local-first authority and auditability.
