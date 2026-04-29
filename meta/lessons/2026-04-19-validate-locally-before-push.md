# Draft Lesson: Validate locally before pushing to CI
Date: 2026-04-19
Source: dreamysuite ESLint/CI repair session (handoff-lessons-eslint.md)
Status: PROMOTED
Promoted: 2026-04-29
Promoted-to: skills/ship/gotchas.yml

## What happened
6 consecutive CI runs failed during the dreamysuite session. Every failure was
caused by something that would have been caught in under 10 seconds running
`npm run lint && npx tsc --noEmit && npm run build` locally before pushing.

## Lesson
Before any push that touches CI-relevant code (build, lint, deps), run the full
local validation chain first. Never push and wait for CI to report what a local
run would have found immediately.

## Evidence
6 failed CI runs, all avoidable. Local validation chain: `npm run lint &&
npx tsc --noEmit && npm run build`. Source: handoff-lessons-eslint.md, 2026-04-19.

## Applies to
Any ship, hotfix, or build session before a git push. Add this as a pre-push
reminder in the ship skill and any CI-touching workflow node.
