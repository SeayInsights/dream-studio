---
name: ship
description: Pre-deploy gate — audit (a11y, perf, technical), harden (error/empty/loading states), optimize (bundle/render/animation/images), test (Playwright + regression). Any FAIL blocks deploy. Trigger on `ship:`, `pre-deploy:`, `deploy:`, or before any deployment command.
pack: core
---

# Ship — Pre-Deploy Gate

## Imports
- core/git.md — check for uncommitted changes, pre-push validation
- core/quality.md — quality gate checklist (audit, harden, optimize, test), pre-push local validation
- core/format.md — ship gate format, verdict statement

## Trigger
`ship:`, `pre-deploy:`, `deploy:`, or before any deployment command

## Purpose
Blocks deployment until all checks pass. No exceptions.

## Gate checklist

**See:** core/quality.md — Quality gate checklist

Run all four gates: Audit (a11y, perf, technical), Harden (error/empty/loading states), Optimize (bundle, rendering, animation, images), Test (Playwright, suite, browser, regression)

## Gate result

**See:** core/format.md — Ship gate format

Output gate result with PASS/FAIL for each category and final verdict (CLEAR TO SHIP / BLOCKED)

## Pre-push local validation (L3)

**See:** core/quality.md — Pre-push local validation

Run: `npm run lint && npx tsc --noEmit && npm run build`
```
All three must exit 0. If any fail, fix locally — do not push a broken state.

## Rules
- Any FAIL blocks deployment
- Director can override a FAIL with explicit approval (logged)
- After fix, re-run the failed check — don't skip re-verification
- This gate runs in the main session, not in a sub-agent
- **Never downgrade lint/TS rules to pass CI (L2).** If lint has errors, fix the errors.
  Downgrading `"error"` → `"warn"` is only acceptable with an inline comment explaining why
  and an immediate follow-up task. CI green ≠ code healthy.
- **Verify CI steps exist locally before adding them (L4).** Before adding any step to a
  CI pipeline, run the command locally. If it exits non-zero or finds no files, do not add
  it — create the prerequisite first or omit the step.
