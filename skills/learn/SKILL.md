---
name: learn
description: Capture and promote lessons from builds — draft to `meta/draft-lessons/`, Director review, promote to memory / skill / agent updates, archive to `meta/lessons/`. Trigger on `learn:`, `capture lesson:`, or when something notably works or breaks.
pack: quality
---

# Learn — Pattern Capture and Promotion

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Trigger
`learn:`, `capture lesson:`, or when something notably works or breaks during a build

## Purpose
Extract lessons from builds and promote them to studio knowledge.

## Draft lesson format
Write to `meta/draft-lessons/YYYY-MM-DD-<topic>.md`:
```markdown
# Draft Lesson: [topic]
Date: YYYY-MM-DD
Source: [what build/session this came from]
Status: DRAFT

## What happened
[Concrete description — what worked or what broke]

## Lesson
[The reusable insight — stated as a rule or pattern]

## Evidence
[Specific files, commits, errors, or outcomes that support this]

## Applies to
[When should this lesson be applied? Which domains/tools/patterns?]
```

## Promotion flow
1. **Capture** — Write draft lesson to `meta/draft-lessons/`
2. **Accumulate** — Drafts sit until Director reviews (via `on-meta-review` or manual check)
3. **Review** — Director approves, edits, or rejects each draft
4. **Promote** — Approved lessons become:
   - Memory entries (if long-term knowledge)
   - Skill updates (if pattern should change a skill's instructions)
   - Agent updates (if behavior should change an agent's config)
5. **Archive** — Promoted drafts move to `meta/lessons/` with status: PROMOTED

## When to capture
- A debugging session reveals a non-obvious root cause
- A build approach succeeds that contradicts initial expectations
- A tool/MCP behaves differently than documented
- A pattern from one domain transfers to another
- Director explicitly corrects an approach (capture why)

## Rules
- Draft lessons are proposals — Director decides what gets promoted
- One lesson per file — don't combine unrelated insights
- Be specific: "D1 doesn't enforce foreign keys" not "databases are tricky"
- Include evidence — lessons without evidence are opinions
- Create `meta/draft-lessons/` directory if it doesn't exist
