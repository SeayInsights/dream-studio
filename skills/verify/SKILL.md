---
name: verify
description: Evidence-based verification — run the app, test golden path + edges, capture proof (screenshots, logs, Playwright results), check regressions. Trigger on `verify:`, `prove it:`, or after `review` passes.
---

# Verify — Prove It Works

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

## Evidence patterns

```
✅ [Run test command] → [See: 34/34 pass] → "All tests pass"
❌ "Should pass now" / "Looks correct"

✅ Write test → Run (pass) → Revert fix → Run (MUST FAIL) → Restore → Run (pass)
❌ "I've written a regression test" (without red-green verification)

✅ [Run build] → [See: exit 0] → "Build passes"
❌ "Linter passed" (linter doesn't check compilation)

✅ Re-read plan → Create checklist → Verify each → Report gaps or completion
❌ "Tests pass, phase complete"

✅ Agent reports success → Check VCS diff → Verify changes → Report actual state
❌ Trust agent report
```

## Verification by domain
- **Web/SaaS** — Run `npm run test:e2e` if Playwright exists. Otherwise open browser, test forms, responsive, a11y.
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

## Next in pipeline
→ `ship` (if deploying) or done

## Anti-patterns
- "I tested it mentally" — no evidence
- Only testing the golden path
- Skipping regression checks
- Claiming verification without running the app
- ANY wording implying success without having run verification
