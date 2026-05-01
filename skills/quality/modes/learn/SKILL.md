---
name: learn
model_tier: haiku
description: "Capture and promote lessons from builds — draft to `meta/draft-lessons/`, Director review, promote to memory / skill / agent updates, archive to `meta/lessons/`. Trigger on `learn:`, `capture lesson:`, or `learn: harvest` for cross-project batch extraction."
pack: quality
chain_suggests: []
---

# Learn — Pattern Capture and Promotion

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Trigger
`learn:`, `capture lesson:`, or when something notably works or breaks during a build. Use `learn: harvest` for cross-project batch extraction from session history.

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
1. **Capture** — Write to DB via `insert_lesson()` from `hooks/lib/studio_db.py` as primary store, then write draft lesson to `meta/draft-lessons/`
2. **Accumulate** — Drafts sit until Director reviews (via `on-meta-review` or manual check)
3. **Review** — Director approves, edits, or rejects each draft
4. **Promote** — Approved lessons become:
   - Memory entries (if long-term knowledge)
   - Skill updates (if pattern should change a skill's instructions)
   - Agent updates (if behavior should change an agent's config)
5. **Archive** — Promoted drafts move to `meta/lessons/` with status: PROMOTED

## Harvest Mode

### Trigger
`learn: harvest`

### Purpose
Batch-scan all historical sources for reusable patterns. Surface the draft backlog for promotion. No skill files are modified until Director explicitly approves each change.

### Config check
Before running any scan, verify `~/.dream-studio/config.json` exists and `harvest.projects_root` is non-empty.
If missing or empty: stop and output — "Harvest not configured. Run `workflow: run studio-onboard` to set your projects root, then retry."

### Scan protocol (run in this order)

**Step 1 — Backlog first**
Scan `meta/draft-lessons/`. For each file, present inline:
```
Draft: [title]
File: meta/draft-lessons/[filename]
Lesson: [one-line summary]
Target: skills/[skill]/gotchas.yml → [avoid|best_practices|edge_cases]
Action? [promote / reject / defer]
```
Wait for Director response before writing anything. On "promote" → write entry to target gotchas.yml. On "reject" → move file to `meta/lessons/` with `Status: REJECTED`. On "defer" → leave as-is.

**Step 2 — Session history**
Determine scan scope from `config.yml`:
1. **Auto-discover**: scan every subdirectory of `harvest.projects_root` that contains a `.sessions/` folder — each qualifies as a harvest target automatically. No registration needed; new projects are picked up the moment they have a `.sessions/` dir.
2. **Extra paths**: also scan any paths listed in `harvest.extra_paths` for one-offs outside `projects_root`.
3. **Local**: always include the dream-studio repo's own `.sessions/` regardless of config.

For each discovered project, scan `<project>/.sessions/**/*.md` (handoffs and recaps). Extract:
- "What's broken / blocked" sections with identified root causes
- "Director correction" mentions
- Patterns that appear in 2+ different session files (across any projects)

Tag each extracted pattern with its source project path so domain-specific lessons stay scoped correctly.

**Step 3 — Dedup check**
Scan `skills/*/gotchas.yml`. For each candidate pattern from Step 2, grep existing entries. If the insight already exists → log "already captured in skills/[skill]/gotchas.yml" and skip.

**Step 4 — Memory cross-reference**
Read `claude_memory_path` from `~/.dream-studio/config.json`. Scan `<claude_memory_path>/feedback_*.md` for feedback entries that have no corresponding gotchas.yml entry and could be generalized into a reusable skill rule.
If `claude_memory_path` is not set in config.json, skip this step and note "memory scan skipped — run `workflow: run studio-onboard` to configure."

### Anti-bloat rules (enforced — see gotchas.yml)
- **Dedup first**: never draft a lesson that already exists in any gotchas.yml
- **≥2 sources**: only draft lessons with evidence from ≥2 distinct sources
- **≤5 cap**: draft at most 5 new lessons per run — rank by evidence count, take top 5
- **Domain tagging**: domain-specific lessons (Kroger, Power BI client-specific, etc.) must be tagged with the target skill and never promoted to core skill gotchas

### Auto-harvest draft format
Auto-harvested drafts use an extended format with two additional fields:
```
Source: auto-harvest
Confidence: [low|medium|high]  # based on number of distinct sources found
```
- high = 3+ distinct source confirmations
- medium = 2 distinct sources
- low = 1 source (these should rarely be drafted — requires strong evidence)

### No-harvest conditions
If harvest finds nothing new: output "No new patterns found. [N] drafts reviewed." Do not create empty draft files. Do not re-draft lessons already in a gotchas.yml.

## Daily Harvest Mode

### Trigger
`learn: daily` — auto-triggered by daily-close workflow or manual invocation

### Purpose
Lightweight end-of-day learning capture. Scoped to today only — no cross-project scanning.

### Sources (in order)
1. **Micro-captures** — read `~/.dream-studio/meta/today.md` (written by `hooks/lib/micro_capture.py` throughout the day)
2. **Today's sessions** — scan `.sessions/YYYY-MM-DD/` for today's date only (handoffs and recaps)
3. **Git log** — `git log --since="today" --oneline` for commits made today

### Protocol
1. Read all three sources above
2. Extract candidate patterns:
   - Any micro-capture with `outcome:correction` — something went wrong and was fixed
   - Any handoff `lessons_this_session` entry
   - Any recap `Risk flags` with identified root causes
   - Any commit that was a fix for something that broke during the build
3. Apply anti-bloat rules from Harvest Mode:
   - Dedup against existing `meta/draft-lessons/` and `skills/*/gotchas.yml`
   - Only draft lessons with evidence from the day's work
   - ≤5 new drafts per daily run — rank by significance
4. Write drafts to `meta/draft-lessons/YYYY-MM-DD-<topic>.md` with:
   - `Source: daily-harvest`
   - `Confidence: medium` (single-day evidence)
5. Output summary: "Daily harvest: N candidates found, M drafts written, K skipped (already captured)"

### No-harvest conditions
If no corrections, risk flags, or notable patterns found today: output "Clean day — no new patterns." Do not create empty drafts.

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
