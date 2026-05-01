---
name: review
model_tier: sonnet
description: Two-stage quality check — spec compliance first (did we build what was asked?), then code quality (is it well-built?) — with severity-tagged findings. Trigger on `review:`, `review code`, or after `build`.
pack: core
chain_suggests:
  - condition: "findings_found"
    next: "build"
    prompt: "Findings to fix — re-enter build?"
  - condition: "clean"
    next: "verify"
    prompt: "Review clean — verify it works?"
---

# Review — Two-Stage Quality Check

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Imports
- core/git.md — read git diff, get commit SHA
- core/quality.md — OWASP security checks, test coverage
- core/orchestration.md — subagent review pattern, reviewer prompt template
- core/format.md — severity-tagged findings, review findings format, verdict statement

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

**See:** core/orchestration.md — Review loop pattern, reviewer prompt template

Dispatch spec reviewer first, then code quality reviewer after spec passes. Review loops continue until all issues resolved.

Each reviewer returns a JSON object matching the schema in core/orchestration.md:
```json
{
  "signal": "compliant | non_compliant",
  "confidence": 0.0-1.0,
  "summary": "One sentence verdict",
  "issues": [
    {
      "requirement": "the requirement from spec",
      "issue": "what is wrong",
      "location": "file:line",
      "fix": "specific, actionable fix"
    }
  ]
}
```
Parse `result.signal`: `compliant` → next stage. `non_compliant` → re-dispatch implementer with `result.issues`.

## Findings format

**See:** core/format.md — Review findings format

Use two-stage format: Stage 1 (spec compliance) → Stage 2 (code quality with severity tags) → Summary with verdict
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
