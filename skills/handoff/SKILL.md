---
name: handoff
description: Session continuity — capture structured state (current task, progress, phase, decisions, active files, next action) to both markdown and JSON. A fresh session resumes from the file alone. Trigger on `handoff:`, at compact threshold, or session end with WIP.
pack: core
---

# Handoff — Session Continuity

## Trigger
`handoff:`, auto-triggered by `on-context-threshold` at compact threshold, or when session is ending with work in progress

## Purpose
Capture the minimum context needed for the next session to continue without re-explanation. Write BOTH human-readable markdown AND machine-parseable JSON for programmatic recovery.

## Steps
1. **Current task** — What plan is being executed? Which task number? What step within that task?
2. **Phase** — Where in the pipeline? (think / plan / build / review / verify / ship)
3. **Progress** — What's done, what's in progress, what's not started?
4. **State** — What's working? What's broken? Any pending Director decisions?
5. **Files** — Which files are actively being touched?
6. **Write both files** — markdown + JSON to `.sessions/YYYY-MM-DD/`
7. **Print** — Print the handoff file path so Director can pass it to the next session

## Markdown output: `.sessions/YYYY-MM-DD/handoff-<topic>.md`
```markdown
# Handoff: [topic]
Date: YYYY-MM-DD

## Resume command
Read [plan path] — resume at Phase [N], Task [N.N]

## Current state
- Plan: [path to plan file]
- Pipeline phase: [think|plan|build|review|verify|ship]
- Current task: [task number + name]
- Progress: [X of Y tasks complete]
- Branch: [git branch name]
- Last commit: [short SHA + message]

## What's working
- [item]

## What's broken / blocked
- [item]: [detail]

## Pending decisions
- [decision needed]: [context]

## Active files
- [file path]: [what's being done to it]

## Next action
[Exact next thing to do — specific enough that a fresh session can start immediately]
```

## JSON output: `.sessions/YYYY-MM-DD/handoff-<topic>.json`
```json
{
  "topic": "feature-name",
  "date": "YYYY-MM-DD",
  "plan_path": "docs/plans/plan-file.md",
  "pipeline_phase": "build",
  "current_task_id": "3.2",
  "current_task_name": "Wire up API endpoint",
  "tasks_completed": 5,
  "tasks_total": 12,
  "branch": "feat/feature-name",
  "last_commit": "abc1234",
  "working": ["auth flow", "database schema"],
  "broken": [{"item": "test suite", "detail": "2 failures in auth.test.ts"}],
  "pending_decisions": [{"decision": "cache strategy", "context": "Redis vs in-memory"}],
  "active_files": ["src/api/auth.ts", "src/lib/cache.ts"],
  "next_action": "Fix auth.test.ts failures, then continue task 3.3"
}
```

## Recovery state machine
The JSON handoff enables programmatic resume:
1. New session reads JSON → knows exact phase, task, branch
2. Checks out correct branch
3. Reads plan file at `plan_path`
4. Skips completed tasks (by `current_task_id`)
5. Resumes at `next_action`

No re-reading conversation history. No orientation. Immediate productive work.

## Context pressure triggers
When context is growing large:
- If in `build` phase with independent remaining tasks → dispatch subagents (they get fresh context)
- If mid-task → complete current task, commit, then handoff
- Never handoff mid-edit — always reach a committed checkpoint first

## Rules
- **Targeted payload, not brain dump** — only what's needed to resume
- Write to `.sessions/YYYY-MM-DD/` — create directory if needed
- Always write BOTH .md and .json files
- The "Resume command" field is the single line the next session needs
- A fresh session should be able to resume using ONLY the handoff file
