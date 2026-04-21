---
name: review
description: Two-stage quality check — spec compliance first (did we build what was asked?), then code quality (is it well-built?) — with severity-tagged findings. Trigger on `review:`, `review code`, or after `build`.
pack: core
---

# Review — Two-Stage Quality Check

## Trigger
`review:`, `review commits`, `review code`, `review PR:`, or after `build` completes

## Core Principle
Spec compliance BEFORE code quality. Always. Catching "built the wrong thing" matters more than "code smells."

## Stage 1: Spec Compliance Review

**Purpose:** Did we build what was requested — nothing more, nothing less?

1. Re-read the plan/spec
2. Compare implementation to requirements line by line
3. Check for:
   - **Missing requirements** — things requested but not built
   - **Extra work** — things built but not requested (over-engineering)
   - **Misunderstandings** — right feature, wrong interpretation

**Do NOT trust self-reports.** Read the actual code. Compare to the actual spec.

```
✅ Spec compliant — all requirements met, nothing extra
❌ Issues: [list what's missing/extra with file:line references]
```

**Stage 1 must pass before moving to Stage 2.** If spec issues exist, fix them first.

## Stage 2: Code Quality Review

**Purpose:** Is the implementation well-built?

1. **Scope check** — Does the code match the plan/spec? Flag anything extra.
2. **Correctness** — Logic errors, edge cases, race conditions, null handling.
3. **Security** — OWASP Top 10 scan:
   - Injection (SQL, command, XSS)
   - Broken auth / session management
   - Sensitive data exposure
   - Missing access control
   - Security misconfiguration
   - Vulnerable dependencies
4. **Test coverage** — Are critical paths tested? Edge cases covered?
5. **Code quality** — Readability, naming, duplication, complexity.
6. **File responsibility** — Each file has one clear job with a well-defined interface?

## Fast scan mode
When invoked with Haiku for fast scan:
1. Scan for: secrets, debug leftovers, obvious bugs, missing error handling
2. Output: `FAST SCAN: CLEAN` or `FAST SCAN: FINDINGS` with bullet list

## Subagent review (for larger changes)
When reviewing substantial work, dispatch separate reviewer agents:

**Spec reviewer agent:**
- Gets: full task spec + implementer's report
- Job: verify code matches spec (read code, not report)
- Critical rule: "Do not trust the report. The implementer finished suspiciously quickly."
- Returns: ✅ compliant or ❌ issues with file:line references

**Code quality reviewer agent:**
- Gets: diff (BASE_SHA..HEAD_SHA) + task summary
- Job: strengths, issues (critical/important/minor), assessment
- Only dispatched AFTER spec reviewer passes
- Returns: approved or issues to fix

Review loops: if reviewer finds issues → implementer fixes → reviewer reviews again → repeat until approved.

## Findings format
```
## Review: [scope]
Date: YYYY-MM-DD

### Stage 1: Spec Compliance
- [requirement]: MET / MISSING / EXTRA — [detail]
Spec verdict: COMPLIANT / NON-COMPLIANT

### Stage 2: Code Quality

#### Critical (blocks ship)
- [finding]: [file:line] — [description + fix]

#### High (blocks ship)
- [finding]: [file:line] — [description + fix]

#### Medium (fix before next release)
- [finding]: [file:line] — [description + fix]

#### Low (improve when convenient)
- [finding]: [file:line] — [description + fix]

### Summary
Spec: COMPLIANT / NON-COMPLIANT
Critical: N | High: N | Medium: N | Low: N
Ship: YES / BLOCKED ([reason])
```

## Next in pipeline
→ `verify` (if clean) or back to `build` (if findings need fixing)

## Anti-patterns
- Reviewing without reading the spec/plan first
- Skipping Stage 1 (spec compliance) and jumping to code quality
- "Looks good" with no specific findings listed
- Flagging style preferences as High severity
- Skipping security checks because "it's internal"
- Trusting self-reports instead of reading the code
- **Acting on stale findings (L1)** — before fixing any finding from a review report, verify
  it still exists: grep or read the file. Reports go stale within hours of being written.
- **Leaving findings unannotated after fixing (L5)** — after each finding is resolved, add
  `[FIXED: <commit-sha>]` inline in the review report. An unmarked report misleads the next
  session into re-fixing already-resolved issues.
