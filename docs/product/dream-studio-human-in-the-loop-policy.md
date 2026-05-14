# Dream Studio Human-In-The-Loop Policy

Status: draft_generated
Authority role: human approval and decision policy

## AI May Continue Internally

AI may continue without a new operator prompt when the work is inside an
approved milestone and limited to:

- approved artifact reads;
- checklist review;
- package review;
- evidence creation or indexing;
- report writing;
- summaries and progress updates;
- already-approved backup, checksum, and restore rehearsal on copied files;
- non-mutating validation inside an approved milestone;
- routine handoff/report rendering that does not cross a stop gate.

## Operator Approval Required

Approval is required for:

- architecture direction changes;
- PRD or stage-gate changes;
- scope expansion;
- source-code mutation outside approved milestone scope;
- database mutation;
- migrations;
- DDL/DML execution;
- commit, push, or deploy;
- package/dependency changes;
- scans or broad validation;
- runtime/browser validation;
- secret/sensitive data access;
- artifact compaction, deletion, or archive;
- external project resume;
- high-risk research interpretation;
- ambiguous business/product requirement.

## Operator Decision Required

Decision is required when multiple viable options materially change product
direction, authority model, safety model, data model, source-of-truth ownership,
research routing, stop-gate policy, milestone semantics, artifact lifecycle, or
external project status.

## Hard Stop Required

Hard stop is required for missing required authority, unsafe repo state, failed
validation with rollback uncertainty, stage-gate-invalid routing, source or DB
mutation without approval, dependency need without approval, sensitive context
risk, or forbidden action evidence.

## Auto-Documentation And Auto-Routing

AI may auto-document routine evidence, compact reports, progress updates, and
non-blocking unknown/deferred answers. AI may auto-route to the next internal
step only when PRD/stage gates permit it and no stop gate is active.

When no operator action is required, Dream Studio may render a continuation
packet for resumability. A continuation packet is not a handoff, must declare
whether auto-resume is allowed, and must not instruct the operator to start a new
phase.

## Cannot Proceed Without User Review

Dream Studio cannot proceed when the next action crosses material risk,
requires unapproved dependencies, resumes paused external implementation,
changes source-of-truth ownership, changes security posture, mutates runtime
data, or treats unverified high-risk research as authority.
