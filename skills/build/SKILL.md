---
name: build
description: Execute a plan with subagent-driven development — fresh agent per task, two-stage review, isolated context, parallel wave execution. Trigger on `build:`, `execute plan:`, or after `plan`.
---

# Build — Execute With Discipline

## Trigger
`build:`, `execute plan:`, or after `plan` is complete

## Core Principles
- Fresh subagent per task — never inherit session history
- Controller stays lean — delegates heavy lifting, preserves own context
- Two-stage review after each task (spec then quality)
- Pre-inline context — don't make agents Read files, provide full text

## Execution Modes

### Simple mode (≤3 tasks, tightly coupled)
Execute directly in the current session. One task at a time, commit after each.

### Subagent mode (≥4 tasks or independent tasks)
Dispatch fresh subagent per task with isolated context.

**Why subagents:** They get only task-specific state — no session history, no conversation baggage. This preserves your own context for coordination while ensuring each agent stays focused.

## The Process

### Step 0: Load plan
Read the plan file ONCE. Extract ALL tasks with full text. Don't re-read the plan per task.

### Step 1: Dependency analysis
Group tasks into waves:
- **Wave 1:** Tasks with no dependencies (can run in parallel if independent files)
- **Wave 2:** Tasks that depend on Wave 1 outputs
- **Wave N:** Continue until all tasks ordered

Independent tasks within a wave MAY run as parallel subagents IF they touch different files. Never dispatch parallel agents that modify the same files.

### Step 2: Execute each task

**For each task (subagent mode):**

1. **Dispatch implementer** — Use prompt template below. Provide:
   - Full task text (pasted, not a file path)
   - Scene-setting context (where task fits, dependencies, architecture)
   - Working directory
   - Any decisions made so far

2. **Handle implementer response:**
   - `DONE` → proceed to review
   - `DONE_WITH_CONCERNS` → read concerns, address if correctness/scope, then review
   - `NEEDS_CONTEXT` → provide missing info, re-dispatch
   - `BLOCKED` → assess: context problem (re-dispatch with more info), capability problem (re-dispatch with more capable model), task too large (break it up), plan is wrong (escalate to Director)

3. **Spec compliance review** — Dispatch reviewer agent:
   - Gets: task spec + implementer report
   - Job: verify code matches spec (read code, not report)
   - Must pass before code quality review
   - If issues: implementer fixes → re-review → repeat until ✅

4. **Code quality review** — Dispatch reviewer agent:
   - Gets: diff (base..head SHA) + task summary
   - Only after spec compliance passes
   - If issues: implementer fixes → re-review → repeat until ✅

5. **Commit** — Atomic commit referencing plan task number

6. **Mark complete** — Write proof to disk (task status in plan file or state file)

### Step 3: Checkpoint
After every 3 tasks or 30 minutes (whichever first):
- Tasks completed / total
- Any drift from plan
- Blockers or concerns
- Context usage (if growing, consider handoff)

## Model Selection for Subagents

| Task type | Model | Signal |
|-----------|-------|--------|
| Mechanical (1-2 files, clear spec) | Haiku | Isolated function, straightforward |
| Integration (multi-file, patterns) | Sonnet | Coordination, debugging |
| Architecture, design, review | Opus | Judgment calls, broad understanding |

## Implementer Prompt Template

```
You are implementing Task N: [task name]

## Task Description
[FULL TEXT of task from plan — pasted here, never make agent read file]

## Context
[Where this fits, dependencies, architectural context]

## Before You Begin
If you have questions about requirements, approach, dependencies, or anything unclear — ask now. Don't guess.

## Your Job
1. Implement exactly what the task specifies
2. Write tests
3. Verify implementation works
4. Commit your work
5. Self-review: completeness, quality, discipline, testing
6. Report back

## Report Format
- Status: DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- What you implemented
- What you tested and results
- Files changed
- Self-review findings
- Any concerns

It's always OK to stop and say "this is too hard for me." Bad work is worse than no work.
```

## Drift detection
- **Minor drift** (variable name, slight approach change) → note it, continue
- **Major drift** (new dependency, scope change, architecture change) → STOP. "Drift detected: [what and why]. Adjust plan or revert?"

## Phase-locked transitions
Each task only advances after writing proof to disk. If context fills mid-task, the handler can checkpoint state and the next session resumes from the last proven task.

## Next in pipeline
→ `review` (quality check the completed work)

## Anti-patterns
- Skipping evaluation ("it compiles, ship it")
- Committing multiple tasks in one commit
- Continuing past major drift without Director approval
- Making subagents read plan files (provide full text)
- Dispatching parallel agents that touch the same files
- Ignoring subagent questions or escalations
- Skipping spec compliance review and jumping to code quality
- Accepting "close enough" on spec compliance
