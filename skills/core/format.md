# Output Formatting — Core Module

Reusable formatting patterns for consistent, structured output across all skills.

## Usage

When a skill needs formatted output, reference this module:
```
## Imports
- core/format.md — output formatting
```

## Patterns

### Markdown table
```
| Header 1 | Header 2 | Header 3 |
|----------|----------|----------|
| Value 1  | Value 2  | Value 3  |
| Value 4  | Value 5  | Value 6  |
```

**Use for:** Task summaries, requirement matrices, comparison tables

### Checkbox list
```
- [x] Completed item
- [ ] Pending item
- [ ] Another pending item
```

**Use for:** Task progress, verification checklists, acceptance criteria

### Severity-tagged findings
```
#### Critical (blocks ship)
- [finding]: [file:line] — [description + fix]

#### High (blocks ship)
- [finding]: [file:line] — [description + fix]

#### Medium (fix before next release)
- [finding]: [file:line] — [description + fix]

#### Low (improve when convenient)
- [finding]: [file:line] — [description + fix]
```

**Use for:** Review findings, security issues, quality problems

### Verdict statement
```
Verdict: PASS / FAIL / BLOCKED ([reason])
```

**Variants:**
- `CLEAR TO SHIP / BLOCKED ([what must be fixed])`
- `COMPLIANT / NON-COMPLIANT`
- `✅ / ❌`

**Use for:** Gate results, compliance checks, approval decisions

### Numbered task list
```
### 1. [Task name]
- Implements: TR-001, TR-002
- Files: [what's touched]
- Depends on: [task numbers or "none"]
- Acceptance: [how to verify]

### 2. [Task name]
- Implements: TR-003
- Files: [what's touched]
- Depends on: 1
- Acceptance: [how to verify]
```

**Use for:** Plan output, work breakdown

### Summary section
```
## Summary
Tasks: 5 total (3 completed, 2 pending)
Critical: 2 | High: 1 | Medium: 3 | Low: 0
Verdict: BLOCKED (2 critical issues must be fixed)
```

**Use for:** Executive summary at end of output

### Requirements matrix
```
| TR-ID | Description | Priority | Status | Tasks | Commits | Tests |
|-------|-------------|----------|--------|-------|---------|-------|
| TR-001 | Login works | must | verified | 1,2 | abc123 | auth.test.ts |
| TR-002 | Session persists | should | implemented | 3 | def456 | |
```

**Use for:** Traceability tracking, requirement status

### File reference with line number
```
src/components/Button.tsx:42
```

**Format:** `<file-path>:<line-number>`

**Use for:** Pointing to specific code locations in findings

### Code block with language
````
```typescript
function example() {
  return true
}
```
````

**Use for:** Including code snippets in output

### Diff-style comparison
```
- Old approach (removed)
+ New approach (added)
```

**Use for:** Before/after comparisons, migration guides

### Status badges
```
✅ PASS
❌ FAIL
⚠️ WARNING
🔄 IN_PROGRESS
⏸️ BLOCKED
```

**Use for:** Quick status indication

### Coverage report
```
Traceability: 5 of 8 requirements verified (62.5%)
- TR-001 ✅ verified
- TR-002 ✅ verified
- TR-003 ✅ verified
- TR-004 ✅ verified
- TR-005 ✅ verified
- TR-006 ❌ implemented (needs tests)
- TR-007 ❌ in_progress
- TR-008 ❌ planned
```

**Use for:** Verification status, test coverage, requirement progress

### Checkpoint format (wave-level)
```
## Checkpoint (after task 3/10)
- Completed: 3 tasks
- Remaining: 7 tasks
- Drift: None (on track with plan)
- Blockers: None
- Context: 45% used
```

**Use for:** Multi-task wave summaries

### Checkpoint format (task-level)
```
## Task Checkpoint — Task N: [task name]
Status: COMPLETE
Commit: [short SHA] — [one-line commit message]
Next: Task N+1 — [next task name]
Context: ~X% used
```

**Use for:** Per-task checkpoints when `max_tasks_before_checkpoint: 1` (default). Write to `.sessions/YYYY-MM-DD/checkpoint-<topic>.md` in append mode. Use wave-level format for multi-task summaries.

### Ship gate format
```
## Ship Gate: [project]
Date: YYYY-MM-DD

Audit:    PASS / FAIL ([details])
Harden:   PASS / FAIL ([details])
Optimize: PASS / FAIL ([details])
Test:     PASS / FAIL ([details])

Verdict: CLEAR TO SHIP / BLOCKED ([what must be fixed])
```

**Use for:** Pre-deploy gate results

### Review findings format
```
## Review: [scope]
Date: YYYY-MM-DD

### Stage 1: Spec Compliance
- [requirement]: MET / MISSING / EXTRA — [detail]
Spec verdict: COMPLIANT / NON-COMPLIANT

### Stage 2: Code Quality

#### Critical (blocks ship)
- [finding]: [file:line] — [description + fix]

### Summary
Spec: COMPLIANT / NON-COMPLIANT
Critical: N | High: N | Medium: N | Low: N
Ship: YES / BLOCKED ([reason])
```

**Use for:** Code review output

### Evidence statement
```
[Run test command] → [See: 34/34 pass] → "All tests pass"
```

**Format:** `[Action] → [Observation] → [Conclusion]`

**Use for:** Verification evidence, proof of claims

## Rules

- **Always include file:line references** for findings
- **Severity tags required** for all issues (Critical/High/Medium/Low)
- **Verdict always at the end** of gate/review output
- **Evidence before claims** — show the command output, then state the conclusion
- **Tables for structured data** — use markdown tables for multi-field records
- **Checkboxes for progress** — use `- [x]` / `- [ ]` for completion tracking

## Anti-patterns

❌ Verbose prose paragraphs
❌ Claims without evidence
❌ Findings without severity
❌ File references without line numbers
❌ Tables without headers
❌ Mixed formatting styles in same section

## Used by
All skills
