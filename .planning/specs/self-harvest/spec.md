---
feature: self-harvest
status: approved
created: 2026-04-29
skill: dream-studio:think
---

# Spec: Self-Harvest — Cross-Project Learning Extraction

## Problem Statement

The `dream-studio:learn` skill captures lessons reactively — you have to invoke it, and it only knows about the current session. Historical sessions (`.sessions/**/*.md`), draft lessons that were never promoted (`meta/draft-lessons/` has 5 from April 19 still sitting there), and feedback embedded in memory files are all silent sources of patterns that never make it back into skill gotchas. Dream-studio gets smarter only when the Director remembers to ask for it.

The goal: make learning passive and continuous — surface patterns from all sources automatically, with Director approval before anything actually changes.

---

## User Stories

### P1 — Batch harvest from historical sessions
**As the Director**, I want to run `learn: harvest` and have it scan all `.sessions/**/*.md` handoffs and recaps, extract recurring blockers/patterns, and write draft lessons — so I don't have to manually reconstruct what went wrong across 20+ sessions.

**Acceptance:** Running `learn: harvest` produces ≥1 draft lesson from session history that is not already in a `gotchas.yml`.

### P1 — Auto-draft at session end
**As the Director**, I want the `recap` and `handoff` skills to automatically create a draft lesson when they detect a notable blocker, correction, or non-obvious success — so learnings are captured at the moment of maximum context.

**Acceptance:** Any session that has a "what broke" or "Director correction" section in its recap automatically generates a `meta/draft-lessons/` entry without the Director having to trigger `learn:`.

### P2 — Promote draft lesson backlog
**As the Director**, I want `learn: harvest` to present the 5+ stale draft lessons and walk me through promotion (→ gotcha entry, → memory update, or reject) — so they don't accumulate forever.

**Acceptance:** After `learn: harvest`, all drafts in `meta/draft-lessons/` are either promoted or explicitly rejected, not left as DRAFT.

### P2 — Cross-project gotcha deduplication
**As the Director**, I want the harvest to check for the same pattern appearing in multiple projects/sessions before drafting a lesson — so we only keep high-confidence, reusable learnings, not one-off noise.

**Acceptance:** No draft lesson is created if the same insight already exists in a `gotchas.yml` entry. If it does, the harvest notes "already captured."

### P3 — Scheduled monthly auto-harvest
**As the Director**, I want a scheduled remote agent to run `learn: harvest` monthly, produce a harvest summary, and surface it without me having to remember to ask — so the system stays self-optimizing even during long quiet periods.

**Acceptance:** A `/schedule` routine exists that produces a harvest report monthly, scoped to sessions since last harvest.

---

## Functional Requirements

**FR-001:** `learn: harvest` MUST scan `.sessions/**/*.md`, `meta/draft-lessons/`, `skills/*/gotchas.yml`, and `~/.claude/projects/.../memory/feedback_*.md`.

**FR-002:** Harvest MUST check for duplicates against all existing `gotchas.yml` entries and memory feedback files before drafting a new lesson.

**FR-003:** Harvest MUST only draft lessons with evidence from ≥2 distinct sources (sessions, memory entries, or gotchas from other skills).

**FR-004:** Harvest MUST NOT write directly to `skills/*/gotchas.yml` or any memory file — all output goes to `meta/draft-lessons/` first.

**FR-005:** Harvest output MUST cap at 5 new draft lessons per run to prevent noise.

**FR-006:** `recap` and `handoff` skills MUST auto-create a draft lesson when a session includes a Director correction or a "what broke" with root cause.

**FR-007:** Draft lessons written by auto-harvest MUST be flagged `Source: auto-harvest` to distinguish from manually captured lessons.

**FR-008:** Promotion of a draft lesson to `gotchas.yml` MUST require explicit Director approval in conversation.

---

## Success Criteria

**SC-001:** After `learn: harvest`, zero draft lessons older than 7 days remain in DRAFT status (they're either promoted or rejected).

**SC-002:** At least 3 of the 5 existing `meta/draft-lessons/` entries from April 19 are promoted to the correct `skills/<skill>/gotchas.yml` within the first harvest run.

**SC-003:** Harvest produces no duplicate entries — any lesson already in a `gotchas.yml` is reported as "already captured," not re-drafted.

**SC-004:** `learn: harvest` runs end-to-end in under 10 minutes on the current session count (~25 session files).

---

## Edge Cases

**EC-001 — No new patterns found:** Harvest scans all sources, finds nothing new. Output: "No new patterns found. X drafts reviewed, all already captured." Do not create empty draft files.

**EC-002 — Session file has no structured sections:** Some older handoffs may lack "what broke" markers. Harvest skips these rather than guessing; logs "skipped: no extractable patterns."

**EC-003 — Pattern is domain-specific, not generalizable:** A lesson about Kroger's Power BI schema shouldn't go into the core `think` gotchas. Harvest MUST tag domain-specific lessons with the relevant skill and only propose them for that skill's gotchas.

**EC-004 — Draft lesson conflicts with an existing gotcha:** E.g., a new pattern says "always X" but an existing gotcha says "never X." Harvest flags the conflict explicitly in the draft and asks Director to resolve before promoting either.

**EC-005 — Memory files have been updated since the session that generated the lesson:** Before promoting a memory-based lesson to a `gotchas.yml`, verify the underlying behavior is still current (not already fixed or superseded).

---

## Assumptions

- Session files follow the existing format (date-prefixed directories, handoff/recap suffixes).
- Memory files follow the existing frontmatter format (`type: feedback`, `type: user`, etc.).
- `skills/*/gotchas.yml` follow the existing `avoid`/`best_practices`/`edge_cases` schema.
- The scheduled variant (P3) uses the `/schedule` skill and runs as a remote agent.
- Director approval means explicit "promote this" in conversation — not passive inaction.

---

## Approaches Considered

### Option A: Extend `learn` with `harvest` mode + recap auto-draft (recommended)
Add `learn: harvest` trigger to the existing `learn` skill. Add auto-draft hook to `recap`/`handoff` skills. No new skill files; no new scheduled agents by default.

**Pros:** Uses existing infrastructure. Director-in-the-loop for all skill file changes. Auto-draft at session end is zero-friction. Low blast radius — only writes to `meta/draft-lessons/`.

**Cons:** Harvest is still on-demand for cross-historical scanning (not fully autonomous). Recap hook adds a small processing step to every session end.

### Option B: New `dream-studio:evolve` skill (standalone)
Dedicated skill that owns all learning extraction logic. Runs as a standalone scan.

**Pros:** Clean separation of concerns. Evolve could eventually be fully autonomous.

**Cons:** Another skill to maintain. Duplicates learn infrastructure. "Evolve" as a top-level concept is vague — it's really just a bigger learn. Adds routing complexity.

### Option C: Scheduled remote agent only (fully autonomous)
Monthly cron agent that scans and writes draft lessons autonomously, Director reviews on their own timeline.

**Pros:** Truly autonomous. No trigger needed.

**Cons:** Remote agents run outside conversation context — they miss the "why" behind patterns. High risk of low-quality, decontextualized drafts. Harvest quality is highest immediately after a session, not a month later.

**Recommended:** Option A. Harvest mode handles the cross-historical scanning. Auto-draft in recap catches fresh learnings at the right moment. P3 adds optional scheduling for the Director if they want it later.

---

## Implementation Notes (for plan phase)

1. **`learn/SKILL.md`** — add `learn: harvest` as a trigger, document the scan sources and anti-bloat rules, document the draft lesson backlog promotion flow.

2. **`recap/SKILL.md`** and **`handoff/SKILL.md`** — add a step: after writing the recap/handoff file, scan the session for corrections and blockers; if found, call `learn:` internally to draft a lesson.

3. **`learn/gotchas.yml`** — populate with the lessons learned from building this feature (currently empty).

4. **Scan scope:** `.sessions/` in dream-studio repo + `.sessions/` in any project that uses dream-studio (via standard path convention).

5. **Existing draft promotion:** First harvest run should batch-present the 5 April 19 drafts before scanning for new ones.

---

## Next Step

Waiting for Director approval before moving to `dream-studio:plan`.
