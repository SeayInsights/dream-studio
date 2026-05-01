---
name: build
description: Execute a plan with subagent-driven development — fresh agent per task, two-stage review, isolated context, parallel wave execution. Trigger on `build:`, `execute plan:`, or after `plan`.
pack: core
chain_suggests:
  - condition: "ui_build"
    next: "polish"
    prompt: "UI changes detected — run polish?"
  - condition: "always"
    next: "review"
    prompt: "Build complete — review the code?"
---

# Build — Execute With Discipline

## Before you start
Read `gotchas.yml` in this directory before every invocation.
If the project has `.planning/GOTCHAS.md` — read it before starting.
If the project has `.planning/CONSTITUTION.md` — read it before starting.

## Pre-flight Intelligence
Before dispatching any task, query the registry for relevant context:
1. **Gotcha check** — `get_gotchas_for_skill('core:build')` from `hooks/lib/studio_db.py` (falls back to file-walk via `gotcha_scanner.py` if registry not populated). Show top 3 most recent gotchas as "Pre-flight: 3 recent gotchas for [skill]" — informational only, doesn't block.
2. **Approach history** — `get_best_approaches('core:build')` from `hooks/lib/studio_db.py`. Surface proven approaches: "Prior sessions show [approach] worked [N]% of the time." Use this to inform dispatch strategy (parallel vs sequential, model choice).

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

### Step 0: Load plan and project context

**Pre-flight Gotcha Briefing** — Before loading the plan, surface the 3 most recently added gotchas relevant to this build:
1. Run `hooks/lib/gotcha_scanner.py` → `get_recent_gotchas(limit=3)` for the skills involved in this plan
2. Display each gotcha as: `[severity] gotcha-id — title`
3. This is informational only — does not block the build
4. Purpose: recently-added gotchas reflect the latest lessons learned; surfacing them here prevents repeating recent mistakes

If `.planning/GOTCHAS.md` exists, read it now. If `.planning/CONSTITUTION.md` exists, read it now. These contain known failure patterns and architectural decisions that must constrain every task in the build.
Read the plan file ONCE. Extract ALL tasks with full text. Don't re-read the plan per task.

**⛔ STOP gate:** If the project has 5+ files AND `.planning/CONSTITUTION.md` or `.planning/GOTCHAS.md` are missing — STOP. Run `dream-studio:harden` first to scaffold these files. A build without a constitution is building blind.

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

## Compiled Prompt Pattern (preferred when available)

Before spawning implementer agents, use the compiled prompt pipeline if scripts exist:

1. **Generate static context:** `py hooks/lib/context_compiler.py --skill=build --pack=core [--repo-context=<path>]`
2. **Assemble prompt:** `py hooks/lib/prompt_assembler.py --template=implementer --static-context=<compiled.md> --task-text="<task>"`
3. Use the assembled output as the agent's prompt

The compiled prompt produces a byte-identical static prefix across all tasks in a wave, enabling Claude prompt cache hits. If either script is unavailable or errors, fall back to the standard template below.

For reviewers: use `--template=reviewer`. For exploration: use `--template=explorer`.

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

| ❌ Wrong | ✅ Correct |
|---|---|
| Skipping spec compliance ("it compiles, ship it") | Always run spec compliance review before code quality review |
| Committing multiple tasks in one commit | One task = one commit with task ID in message |
| Continuing past major drift without approval | STOP and surface drift: "Drift detected: [what/why]. Adjust or revert?" |
| Giving subagents a file path to read | Paste full text inline in the dispatch prompt |
| Dispatching parallel agents that touch the same file | Check file ownership — shared files require sequential tasks |
| Ignoring subagent escalations or concerns | Read every `done_with_concerns` — address correctness issues before review |
| Skipping spec compliance and jumping to code quality | Spec compliance must pass first — in that order, always |
| Accepting "close enough" on spec compliance | Either it meets the acceptance criterion or it doesn't — no partial credit |
| Starting a build without CONSTITUTION.md on a 5+ file project | Run dream-studio:harden first to scaffold project constitution |
