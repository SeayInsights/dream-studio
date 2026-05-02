---
ds:
  pack: core
  mode: ship
  mode_type: review
  inputs: [current_branch, uncommitted_changes, test_results, build_status]
  outputs: [quality_checks, ship_verdict, rollback_plan, monitoring_plan]
  capabilities_required: [Read, Bash, Grep]
  model_preference: sonnet
  estimated_duration: 10-30min
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

## Ship Gate Response Contract {#ship-contract}

Every ship decision MUST include all five sections below. This contract ensures all deployment risks are assessed before the final go/no-go decision.

### Format

```markdown
## Ship Gate Response Contract

### Quality Checks
- [ ] All tests passed (unit, integration, E2E)
- [ ] Lint clean (no errors, warnings documented)
- [ ] TypeScript clean (npx tsc --noEmit exits 0)
- [ ] Build successful (npm run build exits 0)
- [ ] Security scan results: [PASS/FAIL + link to report]
- [ ] Frontend: Core Web Vitals (LCP < 2.5s, INP < 200ms, CLS < 0.1)

### Known Limitations
- **What doesn't work yet:** [List incomplete features, edge cases, deferred work]
- **Acceptable risks:** [List known issues deemed acceptable for this release]
- **Future work:** [List follow-up tasks tracked in issues]

### Rollback Plan
- **Rollback trigger:** [What conditions require rollback?]
- **Rollback steps:** [Numbered list of exact commands to revert]
- **Data impact:** [Any data migrations? How to reverse?]
- **Estimated rollback time:** [X minutes]

### Monitoring Plan
- **Metrics to watch:** [List critical metrics: error rate, latency, user impact]
- **Monitoring tools:** [Where to check: Sentry, CloudWatch, Analytics, etc.]
- **Alert thresholds:** [What values trigger an alert?]
- **Watch duration:** [How long to monitor post-deploy: 1hr, 24hr, 1 week]

### Sign-off
**Decision:** [CLEAR TO SHIP / BLOCKED]

**Rationale:** [1-2 sentence explanation of decision]

**Blocker resolution required:** [If blocked, list what must be fixed before re-evaluation]
```

### Usage Notes

- **Never skip sections.** If a section doesn't apply (e.g., no database changes for rollback), write "N/A - no database changes" — don't omit it.
- **Quality Checks** must be objective pass/fail. "Looks good" is not acceptable — link to CI run, test output, scan report.
- **Known Limitations** separate acceptable risks from blockers. If a limitation is NOT acceptable, it becomes a blocker and decision is BLOCKED.
- **Rollback Plan** is mandatory even for low-risk deploys. "Revert the last commit" is acceptable for simple cases.
- **Monitoring Plan** ensures post-deploy validation. If deployment succeeds but breaks in production, monitoring catches it.
- **Sign-off** must be explicit. "CLEAR TO SHIP" or "BLOCKED" — no ambiguity.

### Director Override

If a FAIL in Quality Checks or an acceptable risk in Known Limitations would normally block ship, the Director (user) can override with explicit approval. Log the override in the Sign-off section:

```markdown
**Decision:** CLEAR TO SHIP (Director override)

**Override reason:** [User's stated reason for accepting the risk]

**Original blocker:** [What failed that was overridden]
```

## Post-ship archive

After a successful deploy, archive the spec to prevent .planning/specs/ from accumulating indefinitely:

1. Copy `templates/archive-stamp-template.md` to `.planning/specs/<topic>/archive-stamp.md`
2. Fill in: status (shipped), shipped_date, merge_sha, pr_url, summary
3. Move the entire `.planning/specs/<topic>/` folder to `.planning/archive/<topic>/`
4. Commit: `chore: archive <topic> spec post-ship`

This keeps .planning/specs/ clean — only in-progress specs live there.
