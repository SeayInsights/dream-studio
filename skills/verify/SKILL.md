---
name: verify
description: Evidence-based verification — run the app, test golden path + edges, capture proof (screenshots, logs, Playwright results), check regressions. Trigger on `verify:`, `prove it:`, or after `review` passes.
---

# Verify — Prove It Works

## Trigger
`verify:`, `prove it:`, or after `review` passes clean

## Purpose
Evidence-based verification. No "should work" — proof.

## Steps
1. **Identify targets** — What needs to be proven? Reference spec acceptance criteria.
2. **Run the app** — Start dev server, build, or launch scene.
3. **Golden path** — Test the primary user flow end-to-end.
4. **Edge cases** — Test boundaries, empty states, error states, invalid input.
5. **Evidence** — Capture proof:
   - UI: screenshots at key states
   - API: request/response logs
   - Game: scene output, QA stdout events
   - CLI: terminal output
6. **Regression** — Does existing functionality still work?

## Verification by domain
- **Web/SaaS** — if `playwright.config.ts` exists in the build, run `npm run test:e2e` first. Playwright results count as evidence. If no Playwright config, open in browser, test forms, check responsive, check a11y manually.
- **API** — hit endpoints, verify response shape and status codes. Playwright API tests (via `request` fixture) cover this for web builds.
- **Game** — run scene via godot-mcp, check QA stdout events
- **Power Platform** — test in preview mode, verify data connections
- **MCP server** — call each tool, verify response format and error handling

## Playwright integration
When a web build has `playwright.config.ts` + `e2e/` directory:
1. Run `npm run test:e2e` from the build root
2. Check exit code: 0 = all tests passed
3. Run `npx playwright show-report` if failures need investigation
4. Test results auto-write to `meta/test-results/latest.json` and `meta/quality-log.md` when the studio reporter is configured
5. Attach pass/fail counts to the verification output below

## Output
```
## Verification: [feature]
Date: YYYY-MM-DD

### Golden path
- [step]: PASS / FAIL — [evidence]

### Edge cases
- [case]: PASS / FAIL — [evidence]

### Regression
- [area]: PASS / FAIL

### Verdict: VERIFIED / FAILED ([details])
```

## Next in pipeline
→ `ship` (via `ship` skill if deploying) or done

## Anti-patterns
- "I tested it mentally" — no evidence
- Only testing the golden path
- Skipping regression checks
- Claiming verification without running the app
