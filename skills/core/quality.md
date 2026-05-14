# Quality Gates — Core Module

Reusable quality check patterns for builds, tests, linting, and validation.

## Usage

When a skill needs quality gates, reference this module:
```
## Imports
- core/quality.md — quality gates
```

## Patterns

### Run build
```bash
npm run build
```
**Success:** Exit code 0
**Failure:** Non-zero exit code or error output

Check exit code with `$?` or `echo $?` immediately after.

### Run tests
```bash
npm test
# or
npm run test:unit
npm run test:e2e
```

**Evidence required:** Full output showing pass/fail counts
```
✅ "34 tests passed, 0 failed" → tests pass
❌ "Should pass" / "Looks good" → not evidence
```

### Run linter
```bash
npm run lint
# or
npx eslint .
```

**Clean:** Exit 0, no errors in output
**Issues:** Non-zero exit, errors/warnings listed

### Type checking
```bash
npx tsc --noEmit
```

**Pass:** Exit 0, no type errors
**Fail:** Non-zero exit, type errors listed

### Pre-push local validation (L3)
Before any `git push`, run the full local chain:
```bash
npm run lint && npx tsc --noEmit && npm run build
```

All three MUST exit 0. If any fail, fix locally — never push broken state.

**Rule:** CI green ≠ code healthy. Fix errors, don't downgrade rules.

### Accessibility checks
```bash
# Lighthouse (if config exists)
npx lighthouse <url> --output=json --quiet

# Or manual checks:
# - Keyboard navigation works
# - Focus visible
# - Alt text on images
# - ARIA where needed
# - Contrast AA minimum
```

**Threshold:** Lighthouse accessibility score > 90

### Performance checks
```bash
npx lighthouse <url> --output=json --quiet
```

**Thresholds:**
- Performance score > 80
- Largest Contentful Paint (LCP) < 2.5s
- Cumulative Layout Shift (CLS) < 0.1
- First Input Delay (FID) < 100ms

### Bundle size check
```bash
# Build and check output
npm run build

# Analyze (if webpack/vite analyzer configured)
npm run analyze
```

**Red flags:**
- Unnecessary dependencies in bundle
- Tree-shaking not working
- Routes not code-split
- Large images not optimized

### Playwright e2e tests
```bash
npm run test:e2e
```

Check for `playwright.config.ts` first. If it exists, run e2e tests.

**Evidence:** Exit code 0 + output showing all tests passed
**Results:** Check `meta/test-results/latest.json` for details

### Verify CI steps exist locally (L4)
Before adding any step to CI pipeline, run the command locally:

```bash
# Example: before adding `npm run test:e2e` to CI
npm run test:e2e
```

If command:
- Exits non-zero → fix first
- Finds no files → create tests first or omit step
- Doesn't exist → add to package.json first

**Rule:** Never add a CI step that doesn't work locally.

## Quality gate checklist (ship skill)

### Audit
- ✅ Accessibility: keyboard nav, focus, alt text, ARIA, contrast AA
- ✅ Performance: Lighthouse > 80, CLS < 0.1, LCP < 2.5s
- ✅ Technical: no console errors, no unhandled rejections, no mixed content

### Harden
- ✅ Error states: every async op has error UI (not just console.error)
- ✅ Empty states: every list/table/feed has empty state messaging
- ✅ Loading states: skeleton or spinner for every async load
- ✅ Boundary errors: React error boundaries at route level minimum

### Optimize
- ✅ Bundle size: no unnecessary deps, tree-shaking working, code-split routes
- ✅ Rendering: no unnecessary re-renders, virtualize long lists
- ✅ Animation: 60fps (no jank), GPU-accelerated transforms/opacity only
- ✅ Images: WebP/AVIF, srcset, lazy-load below fold

### Test
- ✅ Playwright e2e: if config exists, run and verify exit 0
- ✅ Test suite: all tests pass, no skipped tests without reason
- ✅ Browser verification: open in browser, test golden path manually
- ✅ Regression: previously working features still work

## Evidence patterns

**Valid:**
```
✅ [Run test command] → [See: 34/34 pass] → "All tests pass"
✅ [Run build] → [See: exit 0] → "Build passes"
✅ Write test → Run (pass) → Revert fix → Run (FAIL) → Restore → Run (pass)
```

**Invalid:**
```
❌ "Should pass now" / "Looks correct"
❌ "Linter passed" (linter ≠ compiler ≠ runtime)
❌ "I've written a test" (without red-green verification)
❌ Trust agent report (verify independently)
```

## Rules

- **No completion claims without fresh verification evidence** — If you haven't run the command in THIS message, you cannot claim it passes
- **Never downgrade lint/TS rules to pass CI** — Fix errors, don't silence them
- **Pre-push validation always** — lint && tsc && build before every push
- **Any FAIL blocks deployment** — No exceptions (except Director override with logged reason)

## Used by
review, ship, verify, build
