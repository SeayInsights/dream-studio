# Draft Lesson: Check that CI steps exist before adding them
Date: 2026-04-19
Source: dreamysuite ESLint/CI repair session (handoff-lessons-eslint.md)
Status: PROMOTED
Promoted: 2026-04-29
Promoted-to: skills/ship/gotchas.yml

## What happened
A `npm test` (vitest) step was added to the CI pipeline when zero test files
existed in the project. The step failed immediately on every run.

## Lesson
Before adding any step to a CI pipeline, run the command locally first.
If it exits non-zero or reports "no files found", do not add it to CI.
A step that can never pass is worse than no step.

## Evidence
Added vitest to pipeline → immediate failure every run because no test files
existed. Had to remove the step. Source: handoff-lessons-eslint.md, 2026-04-19.

## Applies to
Any session that edits a CI pipeline (GitHub Actions, etc.). Applies to test,
lint, build, and any other step. Run it locally first — if it fails or finds
nothing, either create the prerequisite first or skip the step.
