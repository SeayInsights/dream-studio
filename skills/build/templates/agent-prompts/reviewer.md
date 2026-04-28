# Reviewer Agent Prompt Template

Use this template when spawning a reviewer agent for two-stage review.

## Stage 1: Spec Compliance Review

```
Review this implementation for spec compliance.

## Task Specification
[Full task spec from plan]

## Acceptance Criteria
[Checklist from plan]

## Implementation Summary
[What the implementer did — paste their DONE response]

## Git Diff
[Paste git diff output OR commit SHA range]

## Review Focus
Check ONLY spec compliance:
- Did implementation meet all acceptance criteria?
- Is functionality as specified?
- Are all required files created/modified?

DO NOT review code quality yet (that's stage 2).

## Output Format

**PASS** — All acceptance criteria met
- Verification: [how you verified each criterion]

**FAIL** — Missing acceptance criteria
- Missing: [specific criteria not met]
- Evidence: [what's missing from the diff]
- Fix needed: [specific changes required]
```

## Stage 2: Code Quality Review

```
Review this implementation for code quality.

(Only runs AFTER spec compliance passes)

## Implementation Summary
[What was implemented]

## Git Diff
[Paste git diff output OR commit SHA range]

## Review Focus
Code quality only:
- TypeScript types complete and correct?
- Error handling present?
- No console.log statements?
- Follows project conventions?
- Security issues (XSS, SQL injection, etc.)?
- Performance concerns?

## Output Format

**PASS** — Code quality acceptable
- Notes: [any minor suggestions, non-blocking]

**FAIL** — Code quality issues found
Findings:
- [CRITICAL/HIGH/MEDIUM] [Issue description]
  - Location: [file:line]
  - Fix: [specific fix needed]
  - Blocking: [Yes/No]
```
