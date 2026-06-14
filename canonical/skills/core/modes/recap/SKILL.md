---
dream_studio:
  skill_id: ds-core
  pack: core
  mode: recap
  mode_type: report
  inputs: [session_history, commits, decisions, key_findings]
  outputs: [session_summary, accomplishments, next_actions]
  capabilities_required: [Read, Bash]
  model_preference: haiku
  estimated_duration: 5-10min
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
6. **Write to DB (when supported)** — If a maintained Dream Studio persistence interface is available, update the session record and capture notable approaches through it. If unavailable, write the recap file and state that DB persistence was skipped.
6a. **Write file** — Output to `.sessions/YYYY-MM-DD/recap-<topic>.md`
6b. **Micro-capture** — Append a summary line to the daily capture file using the maintained micro-capture interface if available:
   - Call: `append_capture(skill='recap', outcome='<pass|correction>', note='<one-line summary of what was built>')`
   - Use `outcome: correction` if any Director corrections or approach overrides were noted in the Decisions section
   - Use `outcome: pass` otherwise
   - The note should be a single sentence capturing the most important thing from this session
   - This feeds the daily learning pipeline — daily harvest reads these micro-captures
7. **Auto-draft** — After writing the recap file, scan what was captured for:
   - Any Director correction or approach override during the session
   - Any "Risk flags" entry that has an identified root cause (not just "risk exists" but "why it happened")
   If found: record a draft lesson via `insert_lesson()` (DB, NOT a file) with:
   - `source: auto-harvest (recap)`
   - `confidence: high` (session context is still active — this is the richest capture moment)
   - Pre-fill `what_happened`, `lesson`, `evidence` from the recap content
   If nothing qualifies: skip silently — do not write lesson files.

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

## Approach Capture
After writing the recap (step 6) and before auto-draft (step 7):

1. **Query prior approaches** — Use the maintained approach-history interface if available for each skill used this session. Surface patterns when present.
2. **Capture this session's approaches** — For each skill invoked this session, record approach, outcome, context, and rationale in the recap and in the maintained persistence interface if available. Focus on:
   - Corrections (Director overrode your approach)
   - Surprising outcomes (unexpected success or failure)
   - Notable approaches (parallel dispatch, specific debug strategy, etc.)
   Skip routine successes unless the approach itself was notable or new.

## Rules
- Write to `.sessions/YYYY-MM-DD/` — create directory if needed
- Be specific: file paths, commit hashes, decision rationale
- Keep it concise — this is a structured record, not a narrative
- The "Next step" field is critical — it's what the next session reads first
- Auto-drafts are flagged `Source: auto-harvest (recap)` — Director still decides whether to promote them
- Never create a draft lesson file if no correction or root-cause risk was captured — empty drafts pollute the backlog
