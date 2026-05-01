---
name: verify
model_tier: sonnet
description: Evidence-based verification — run the app, test golden path + edges, capture proof (screenshots, logs, Playwright results), check regressions. Trigger on `verify:`, `prove it:`, or after `review` passes.
pack: core
chain_suggests:
  - condition: "always"
    next: "ship"
    prompt: "Verified — ready to ship?"
---

# Verify — Prove It Works

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Imports
- core/git.md — get commit SHA
- core/traceability.md — update TR-ID with test, coverage reporting
- core/quality.md — run build, run tests, evidence patterns
- core/format.md — evidence statement, coverage report, checkbox list

## Trigger
`verify:`, `prove it:`, or after `review` passes clean

## The Iron Law

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

If you haven't run the verification command in THIS message, you cannot claim it passes.

## The Gate (run this every time)

```
BEFORE claiming any status:
1. IDENTIFY — What command proves this claim?
2. RUN — Execute the FULL command (fresh, complete)
3. READ — Full output, check exit code, count failures
4. VERIFY — Does output confirm the claim?
   - NO → State actual status with evidence
   - YES → State claim WITH evidence
5. ONLY THEN — Make the claim
```

## Common Failures

| Claim | Requires | Not Sufficient |
|-------|----------|----------------|
| Tests pass | Test command output: 0 failures | Previous run, "should pass" |
| Linter clean | Linter output: 0 errors | Partial check, extrapolation |
| Build succeeds | Build command: exit 0 | Linter passing, logs look good |
| Bug fixed | Reproduce original symptom: passes | Code changed, assumed fixed |
| Regression test works | Red-green cycle verified | Test passes once |
| Agent completed task | VCS diff shows changes | Agent reports "success" |
| Requirements met | Line-by-line checklist | Tests passing |

## Red Flags — STOP immediately

- Using "should", "probably", "seems to"
- Expressing satisfaction before verification ("Great!", "Done!")
- About to commit/push/PR without running verification
- Trusting agent success reports without independent check
- Relying on partial verification
- Thinking "just this once"

## Rationalization Prevention

| Excuse | Reality |
|--------|---------|
| "Should work now" | RUN the verification |
| "I'm confident" | Confidence ≠ evidence |
| "Just this once" | No exceptions |
| "Linter passed" | Linter ≠ compiler ≠ runtime |
| "Agent said success" | Verify independently |
| "Partial check is enough" | Partial proves nothing |

## Steps
1. **Identify targets** — See: core/traceability.md — Use TR-IDs if exists, else plan acceptance criteria
2. **Run the app** — See: core/quality.md — Run build, start dev server
3. **Golden path** — Test primary user flow end-to-end
4. **Edge cases** — Test boundaries, empty states, error states, invalid input
5. **Evidence** — See: core/format.md — Evidence statement format
   - Capture: screenshots (UI), logs (API), terminal output (CLI)
6. **Regression** — Does existing functionality still work?
7. **Update traceability** — See: core/traceability.md — Update TR-ID with test

## Evidence patterns

**See:** core/quality.md — Evidence patterns

Must follow format: `[Action] → [Observation] → [Conclusion]`

✅ Re-read plan → Create checklist → Verify each → Report gaps or completion
❌ "Tests pass, phase complete"

✅ Agent reports success → Check VCS diff → Verify changes → Report actual state
❌ Trust agent report
```

## Verification by domain
- **Web/SaaS** — Run `npm run test:e2e` if Playwright exists. Otherwise open browser, test forms, responsive, a11y.
   - **Design quality scan:** Run `npx impeccable detect` against the project to check for anti-pattern violations. Reports 24 design issues without requiring AI. Fix any violations before claiming UI is clean.
   - **React/Next.js deep verification** (when project uses React/Next.js and app is running):
     - `next-browser snapshot` — confirm key components rendered, no missing nodes
     - `next-browser accessibility` — surface ARIA violations, missing labels, contrast failures
     - `next-browser profile` — check Core Web Vitals: LCP < 2.5s, CLS < 0.1, INP < 200ms
     - `next-browser click <selector>` / `next-browser fill <selector> <value>` — exercise key user paths interactively
     Start the daemon first if not running: `next-browser start`
- **API** — Hit endpoints, verify response shape and status codes.
- **Game** — Run scene via godot-mcp, check QA stdout events.
- **Power Platform** — Test in preview mode, verify data connections.
- **MCP server** — Call each tool, verify response format and error handling.

## Output
```
## Verification: [feature]
Date: YYYY-MM-DD

### Golden path
- [step]: PASS / FAIL — [evidence: command output or screenshot]

### Edge cases
- [case]: PASS / FAIL — [evidence]

### Regression
- [area]: PASS / FAIL — [evidence]

### Verdict: VERIFIED / FAILED ([details])
```

## Bug Fix Verification (red-green cycle)

When verifying a fix that came through `debug` → `fix-issue` workflow AND debug Step 1.5 produced a test file:

1. **Red** — Run the failing test BEFORE confirming the fix is applied. Confirm it fails (exit non-zero).
2. **Confirm fix applied** — `git diff` shows the fix is present.
3. **Green** — Run the same test. Confirm it passes (exit 0).
4. **Regression** — Run the full test suite. Confirm no new failures introduced.

Evidence format: `[test name] pre-fix → FAIL (exit 1) | post-fix → PASS (exit 0)`

If debug Step 1.5 produced a screenshot/log instead of a test (non-unit-testable bug), use the screenshot/log as reproduction evidence and verify the symptom is gone via golden-path verification instead.

## Next in pipeline
→ `ship` (if deploying) or done

## Anti-patterns
- "I tested it mentally" — no evidence
- Only testing the golden path
- Skipping regression checks
- Claiming verification without running the app
- ANY wording implying success without having run verification
