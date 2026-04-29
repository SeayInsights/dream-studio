# Draft Lesson: Verify current state before acting on audit findings
Date: 2026-04-19
Source: dreamysuite ESLint/CI repair session (handoff-lessons-eslint.md)
Status: PROMOTED
Promoted: 2026-04-29
Promoted-to: skills/secure/gotchas.yml

## What happened
During a dreamysuite audit remediation session, ~30 minutes were spent attempting
to fix findings H1, H2, H4, and SEC-M3 that had already been resolved in code.
The audit report had no resolution markers, so stale findings were treated as live.

## Lesson
Before fixing any finding from an audit report, grep or read the actual file to
confirm the issue still exists. Audit reports go stale within hours of being written.

## Evidence
Session wasted ~30 min on already-resolved findings because the report had no
"fixed in commit X" annotations. Source: handoff-lessons-eslint.md, session 2026-04-19.

## Applies to
Any session that resumes from a secure/review/harden audit output. Before touching
a file listed in an audit, always verify the finding is still present in the current
codebase state.
