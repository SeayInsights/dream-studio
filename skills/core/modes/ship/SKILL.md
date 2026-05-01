---
name: ship
model_tier: sonnet
description: Pre-deploy gate — audit (a11y, perf, technical), harden (error/empty/loading states), optimize (bundle/render/animation/images), test (Playwright + regression). Any FAIL blocks deploy. Trigger on `ship:`, `pre-deploy:`, `deploy:`, or before any deployment command.
pack: core
chain_suggests:
  - condition: "always"
    next: "recap"
    prompt: "Shipped — capture recap?"
---

# Ship — Pre-Deploy Gate

## Before you start
Read `gotchas.yml` in this directory before every invocation.

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

## Frontend projects — Core Web Vitals gate

For projects with a frontend, add this check to the Audit gate before shipping:

```bash
next-browser profile
```

Pass thresholds (Google's "Good" tier):
- **LCP** (Largest Contentful Paint) < 2.5s
- **INP** (Interaction to Next Paint) < 200ms  
- **CLS** (Cumulative Layout Shift) < 0.1

Any metric above threshold = BLOCKED. Fix the performance issue and re-run before deploy.
Start daemon first if not running: `next-browser start`

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

## Post-ship archive

After a successful deploy, archive the spec to prevent .planning/specs/ from accumulating indefinitely:

1. Copy `templates/archive-stamp-template.md` to `.planning/specs/<topic>/archive-stamp.md`
2. Fill in: status (shipped), shipped_date, merge_sha, pr_url, summary
3. Move the entire `.planning/specs/<topic>/` folder to `.planning/archive/<topic>/`
4. Commit: `chore: archive <topic> spec post-ship`

This keeps .planning/specs/ clean — only in-progress specs live there.
