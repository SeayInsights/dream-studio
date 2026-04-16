---
name: review
description: Quality check on completed work — scope, correctness, security (OWASP Top 10), test coverage — with severity-tagged findings. Trigger on `review:`, `review code`, or after `build`.
---

# Review — Quality Check

## Trigger
`review:`, `review commits`, `review code`, `review PR:`, or after `build` completes

## Purpose
Quality check on completed work. Security, correctness, scope creep, test coverage.

## Fast scan mode (two-tier protocol)
When invoked with Haiku for fast scan:
1. Scan for: secrets, debug leftovers, obvious bugs, missing error handling
2. Output: `FAST SCAN: CLEAN` or `FAST SCAN: FINDINGS` with bullet list

## Full review mode
1. **Scope check** — Does the code match the plan/spec? Flag anything extra.
2. **Correctness** — Logic errors, edge cases, race conditions, null handling.
3. **Security** — OWASP Top 10 scan:
   - Injection (SQL, command, XSS)
   - Broken auth / session management
   - Sensitive data exposure
   - Missing access control
   - Security misconfiguration
   - Vulnerable dependencies
4. **Test coverage** — Are critical paths tested? Are edge cases covered?
5. **Code quality** — Readability, naming, duplication, complexity.

## Findings format
```
## Review: [scope]
Date: YYYY-MM-DD

### Critical (blocks ship)
- [finding]: [file:line] — [description + fix]

### High (blocks ship)
- [finding]: [file:line] — [description + fix]

### Medium (fix before next release)
- [finding]: [file:line] — [description + fix]

### Low (improve when convenient)
- [finding]: [file:line] — [description + fix]

### Summary
Critical: N | High: N | Medium: N | Low: N
Ship: YES / BLOCKED ([reason])
```

## Output
Review report in conversation. BLOCKED if Critical or High findings exist.

## Next in pipeline
→ `verify` (if clean) or back to `build` (if findings need fixing)

## Anti-patterns
- Reviewing without reading the spec/plan first
- "Looks good" with no specific findings listed
- Flagging style preferences as High severity
- Skipping security checks because "it's internal"
