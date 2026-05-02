---
ds:
  pack: core
  mode: verify
  mode_type: verification
  inputs: [implementation, acceptance_criteria, test_plan]
  outputs: [test_results, verification_evidence, regression_check, pass_fail_verdict]
  capabilities_required: [Read, Bash, Grep, LSP]
  model_preference: sonnet
  estimated_duration: 10-30min
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

## Red Flags — STOP immediately

- Using "should", "probably", "seems to"
- Expressing satisfaction before verification ("Great!", "Done!")
- About to commit/push/PR without running verification
- Trusting agent reports without independent check
- "Should work now" / "I'm confident" / "Just this once"

## Steps
1. **Identify targets** — See: core/traceability.md — Use TR-IDs if exists, else plan acceptance criteria
2. **Run the app** — See: core/quality.md — Run build, start dev server
3. **Golden path** — Test primary user flow end-to-end
4. **Edge cases** — Test boundaries, empty states, error states, invalid input
5. **Evidence** — See: core/format.md — Evidence statement format
   - Capture: screenshots (UI), logs (API), terminal output (CLI)
6. **Regression** — Does existing functionality still work?
7. **Update traceability** — See: core/traceability.md — Update TR-ID with test

## Browser Testing

**When to use:** UI verification, interactive workflows, visual regression, screenshot evidence

**Workflow:** Create session → navigate → screenshot → interact → cleanup

**Documentation:** [agent-browser.md](../../../../shared/mcp-integrations/agent-browser.md) — detailed examples, MCP tool reference, troubleshooting

## Evidence patterns

Format: `[Action] → [Observation] → [Conclusion]`

✅ Re-read plan → Create checklist → Verify each → Report gaps or completion
✅ Agent reports success → Check VCS diff → Verify changes → Report actual state

## Verification by domain
- **Web/SaaS** — Run `npm run test:e2e` if Playwright exists. Otherwise open browser, test forms, responsive, a11y. Design quality: `npx impeccable detect`. React/Next.js: `next-browser` commands. Browser automation: see [agent-browser.md](../../../../shared/mcp-integrations/agent-browser.md).
- **API** — Hit endpoints, verify response shape and status codes.
- **Game** — Run scene via godot-mcp, check QA stdout events.
- **Power Platform** — Test in preview mode, verify data connections.
- **MCP server** — Call each tool, verify response format and error handling.

## Example: UI Feature Verification

```
User: "verify the new dashboard filters work"

1. npm run build → exit 0
2. npm run dev → localhost:3000
3. Create browser session → navigate → screenshot initial
4. Snapshot → find filter elements (@e1, @e2)
5. Click date filter → screenshot filter open
6. Select "Last 7 days" → screenshot filtered state
7. Clear filters → verify returns to initial
8. Delete session

Evidence:
- Build: exit 0
- Golden path: Screenshots show filter workflow
- Edge case: Clear filters works
- Regression: Dashboard tabs still work
```

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

1. **Red** — Run failing test before fix applied. Confirm fails (exit 1).
2. **Confirm fix** — `git diff` shows fix present.
3. **Green** — Run same test. Confirm passes (exit 0).
4. **Regression** — Run full suite. Confirm no new failures.

Evidence: `[test name] pre-fix → FAIL (exit 1) | post-fix → PASS (exit 0)`

## Next in pipeline
→ `ship` (if deploying) or done

## Anti-patterns
- "I tested it mentally" — no evidence
- Only testing the golden path
- Skipping regression checks
- Claiming verification without running the app
- ANY wording implying success without having run verification
