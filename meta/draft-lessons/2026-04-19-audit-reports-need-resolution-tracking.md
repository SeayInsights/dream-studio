# Draft Lesson: Audit reports need resolution tracking
Date: 2026-04-19
Source: dreamysuite ESLint/CI repair session (handoff-lessons-eslint.md)
Status: DRAFT

## What happened
An audit report with no resolution markers caused already-fixed findings to be
treated as live issues. Work was duplicated and time was wasted re-fixing things
already committed.

## Lesson
When a finding is fixed, immediately update the audit report with the commit SHA
and a status marker (e.g., `[FIXED: abc1234]`). A report with no resolution
markers is a liability — it will mislead the next session.

## Evidence
H1, H2, H4, SEC-M3 were already resolved in code but the audit report showed
them as open, causing ~30 min of wasted re-fix work.
Source: handoff-lessons-eslint.md, session 2026-04-19.

## Applies to
Any session that produces or consumes a secure/review/harden audit report.
The secure and review skills should be updated to include a "mark as fixed"
step — after each finding is resolved, annotate the source report before moving on.
