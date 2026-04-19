---
name: ship
description: Pre-deploy gate — audit (a11y, perf, technical), harden (error/empty/loading states), optimize (bundle/render/animation/images), test (Playwright + regression). Any FAIL blocks deploy. Trigger on `ship:`, `pre-deploy:`, `deploy:`, or before any deployment command.
---

# Ship — Pre-Deploy Gate

## Trigger
`ship:`, `pre-deploy:`, `deploy:`, or before any deployment command

## Purpose
Blocks deployment until all checks pass. No exceptions.

## Gate checklist

### 1. Audit
- **Accessibility**: keyboard navigation works, focus visible, alt text on images, ARIA where needed, contrast AA minimum
- **Performance**: Lighthouse score > 80, no layout shifts (CLS < 0.1), largest contentful paint < 2.5s
- **Technical**: no console errors, no unhandled promise rejections, no mixed content warnings

### 2. Harden
- **Error states**: every async operation has error UI (not just console.error)
- **Empty states**: every list/table/feed has empty state messaging
- **Loading states**: skeleton or spinner for every async load
- **i18n edge cases**: long translations don't break layout, RTL doesn't break if applicable
- **Boundary errors**: React error boundaries at route level minimum

### 3. Optimize
- **Bundle size**: no unnecessary dependencies, tree-shaking working, code-split routes
- **Rendering**: no unnecessary re-renders (React Profiler check), virtualize long lists
- **Animation**: 60fps (no jank), GPU-accelerated transforms/opacity only
- **Images**: WebP/AVIF, srcset for responsive, lazy-load below fold

### 4. Test
- **Playwright e2e**: if `playwright.config.ts` exists, run `npm run test:e2e` — exit code 0 required. Check `meta/test-results/latest.json` for details.
- **Test suite**: all tests pass, no skipped tests without documented reason
- **Browser verification**: open in browser, test golden path manually
- **Regression**: previously working features still work

## Gate result
```
## Ship Gate: [project]
Date: YYYY-MM-DD

Audit:    PASS / FAIL ([details])
Harden:   PASS / FAIL ([details])
Optimize: PASS / FAIL ([details])
Test:     PASS / FAIL ([details])

Verdict: CLEAR TO SHIP / BLOCKED ([what must be fixed])
```

## Pre-push local validation (L3)
Before any `git push`, run the full local chain first. Never push and wait for CI:
```bash
npm run lint && npx tsc --noEmit && npm run build
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
