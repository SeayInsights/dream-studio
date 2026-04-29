# Draft Lesson: Never lower ESLint/TS rules to pass CI
Date: 2026-04-19
Source: dreamysuite ESLint/CI repair session (handoff-lessons-eslint.md)
Status: PROMOTED
Promoted: 2026-04-29
Promoted-to: skills/ship/gotchas.yml, skills/build/gotchas.yml

## What happened
To get CI green quickly, `@typescript-eslint/no-explicit-any` and
`@typescript-eslint/ban-ts-comment` were downgraded from `"error"` to `"warn"`
in eslint.config.mjs. CI passed but 89 real type-safety violations were hidden.

## Lesson
If lint has errors, fix the errors. Downgrading rules from error→warn is only
acceptable with an explicit comment explaining why AND a follow-up task created
immediately. CI green does not mean code is healthy.

## Evidence
After the downgrade, `no-explicit-any` produced 89 warnings in non-effects files
that mask real bugs. The revert + proper fix was left as outstanding work.
Source: handoff-lessons-eslint.md, session 2026-04-19.

## Applies to
Any build, ship, or CI repair session where lint/tsc errors appear. Never trade
rule integrity for a green pipeline. If rules must be relaxed, scope them narrowly
with an inline comment and a tracking note.
