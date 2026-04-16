---
name: handoff
description: Session continuity — capture minimum context (current task, progress, broken state, pending decisions, active files, next action) to `.sessions/YYYY-MM-DD/handoff-<topic>.md`. A fresh session resumes from the file alone. Trigger on `handoff:`, at compact threshold, or session end with WIP.
---

# Handoff — Session Continuity

## Trigger
`handoff:`, auto-triggered by `on-context-threshold` at compact threshold, or when session is ending with work in progress

## Purpose
Capture the minimum context needed for the next session to continue without re-explanation.

## Steps
1. **Current task** — What plan is being executed? Which task number? What step within that task?
2. **Progress** — What's done, what's in progress, what's not started?
3. **State** — What's working? What's broken? Any pending Director decisions?
4. **Files** — Which files are actively being touched?
5. **Write** — Output to `.sessions/YYYY-MM-DD/handoff-<topic>.md`
6. **Print** — Print the handoff file path so Director can pass it to the next session

## Output format
```markdown
# Handoff: [topic]
Date: YYYY-MM-DD

## Resume command
Read [plan path] — resume at Phase [N], Task [N.N]

## Current state
- Plan: [path to plan file]
- Current task: [task number + name]
- Progress: [X of Y tasks complete]

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

## Rules
- **Targeted payload, not brain dump** — only what's needed to resume
- Write to `.sessions/YYYY-MM-DD/` — create directory if needed
- The "Resume command" field is the single line the next session needs
- Auto-trigger: `on-context-threshold` fires this at compact threshold automatically
- A fresh session should be able to resume using ONLY the handoff file — no conversation history needed
