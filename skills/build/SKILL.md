---
name: build
description: Execute a plan with subagent-driven development — fresh agent per task, two-stage review, isolated context, parallel wave execution. Trigger on `build:`, `execute plan:`, or after `plan`.
pack: core
---

# Build — Execute With Discipline

## Imports
- core/git.md — commit formatting, diff reading, branch operations
- core/traceability.md — TR-ID validation and updates
- core/quality.md — build commands, test execution
- core/orchestration.md — subagent spawning, model selection, review loops
- core/format.md — checkpoint format, task progress

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
**See:** core/orchestration.md — Dependency analysis for parallel execution

Group tasks into waves based on dependencies. Independent tasks within a wave MAY run as parallel subagents IF they touch different files.

### Step 2: Execute each task

**For each task (subagent mode):**

1. **Dispatch implementer** — Use prompt template below. Provide:
   - Full task text (pasted, not a file path)
   - Scene-setting context (where task fits, dependencies, architecture)
   - Working directory
   - Any decisions made so far

2. **Handle implementer response** — See: core/orchestration.md — Handling agent responses
   - `DONE` → proceed to review
   - `DONE_WITH_CONCERNS` → read concerns, address if correctness/scope, then review
   - `NEEDS_CONTEXT` → provide missing info, re-dispatch
   - `BLOCKED` → assess and re-dispatch or escalate

3. **Spec compliance review** — See: core/orchestration.md — Review loop pattern
   - Dispatch reviewer with task spec + implementer report
   - Must pass before code quality review
   - If issues: implementer fixes → re-review → repeat until ✅

4. **Code quality review** — See: core/orchestration.md — Review loop pattern
   - Dispatch reviewer with diff (base..head SHA) + task summary
   - Only after spec compliance passes
   - If issues: implementer fixes → re-review → repeat until ✅

5. **Commit** — See: core/git.md — Commit referencing plan task
   - With TR-IDs: `feat(task-3): implement login form [TR-001, TR-002]`
   - Without TR-IDs: `feat(task-3): implement login form`

6. **Update traceability** (conditional) — See: core/traceability.md — Update TR-ID with commit
   - Check if `.planning/traceability.yaml` exists
   - If exists: validate → update commits + status → re-validate
   - If doesn't exist or invalid: skip

7. **Mark complete** — Write proof to disk (task status in plan file or state file)

### Step 3: Checkpoint
**See:** core/format.md — Checkpoint format

After every 3 tasks or 30 minutes (whichever first), output checkpoint with:
- Tasks completed / total
- Any drift from plan
- Blockers or concerns
- Context usage (if growing, consider handoff)

## Model Selection for Subagents

**See:** core/orchestration.md — Model Selection

Use Haiku for mechanical tasks, Sonnet for integration, Opus for architecture/design/review.

## Implementer Prompt Template

**See:** core/orchestration.md — Implementer prompt template

Use the standard template with:
- Full task text (pasted, never a file path)
- Scene-setting context
- Expected output format (DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT)

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
