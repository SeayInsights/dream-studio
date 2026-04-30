---
name: recap
description: Capture structured build memory — what was built, decisions, risks, stack, remaining work, next step — to `.sessions/YYYY-MM-DD/recap-<topic>.md`. Trigger on `recap:`, `session recap:`, or auto after substantive builds (3+ files, multi-task plans).
pack: core
---

# Recap — Build Memory Capture

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Trigger
`recap:`, `session recap:`, or auto-triggered after substantive builds

## Purpose
Record what happened in a build so future sessions and the Improvement Loop (Engine 2) have context.

## When to trigger
- After any build that created or modified 3+ files
- After any multi-task plan execution completes
- Before ending a session with significant work done
- On Director request

## Steps
1. **Gather** — What was built? Which files changed? What commits were made?
2. **Decisions** — What decisions were made during the build and why?
3. **Risks** — What risk flags were raised? What was deferred?
4. **Stack** — What technologies/patterns were used?
5. **Remaining** — What's left undone? What's the logical next step?
6. **Write** — Output to `.sessions/YYYY-MM-DD/recap-<topic>.md`
7. **Auto-draft** — After writing the recap file, scan what was captured for:
   - Any Director correction or approach override during the session
   - Any "Risk flags" entry that has an identified root cause (not just "risk exists" but "why it happened")
   If found: write a draft lesson to `meta/draft-lessons/YYYY-MM-DD-<topic>.md` using the standard draft lesson format, with:
   - `Source: auto-harvest (recap)`
   - `Confidence: high` (session context is still active — this is the richest capture moment)
   - Pre-fill "What happened", "Lesson", "Evidence", and "Applies to" from the recap content
   If nothing qualifies: skip silently — do not create an empty draft file.

## Output format
```markdown
# Recap: [topic]
Date: YYYY-MM-DD
Session: [session context if available]

## What was built
- [file/feature]: [what changed]
- Commits: [list of commit hashes + messages]

## Decisions
- [decision]: [rationale]

## Risk flags
- [risk]: [status — mitigated / deferred / open]

## Stack / patterns used
- [technology or pattern]: [how it was applied]

## Remaining work
- [task]: [status — not started / partial / blocked on X]

## Next step
[The single most logical next action for the next session]
```

## Rules
- Write to `.sessions/YYYY-MM-DD/` — create directory if needed
- Be specific: file paths, commit hashes, decision rationale
- Keep it concise — this is a structured record, not a narrative
- The "Next step" field is critical — it's what the next session reads first
- Auto-drafts are flagged `Source: auto-harvest (recap)` — Director still decides whether to promote them
- Never create a draft lesson file if no correction or root-cause risk was captured — empty drafts pollute the backlog
