---
name: career-track
description: "Pipeline management, application tracking, pattern analysis, and follow-up cadence. Modes: tracker, pipeline, patterns, followup. Trigger via /career-ops tracker|pipeline|patterns|followup."
---

# Career-Track — Pipeline Intelligence

## Paths
Read `~/.dream-studio/career-ops/config.yml` to get `career_studio_path`.
Read `{career_studio_path}/config/career-ops-paths.yml` to resolve all paths.

## Modes

### tracker — Application status overview
1. Read `modes/tracker.md` (standalone, no _shared.md needed)
2. Read `data/applications.md`
3. Show summary: total applications, by status, by score range, recent activity
4. Canonical statuses from `templates/states.yml`: Evaluated, Applied, Responded, Interview, Offer, Rejected, Discarded, SKIP

### pipeline — Process pending URLs
1. Read `modes/_shared.md` + `modes/pipeline.md`
2. Read `data/pipeline.md` for pending URLs
3. For each URL: extract JD → evaluate → report → tracker
4. If 3+ URLs: run as subagent to preserve controller context
5. After processing, run `node merge-tracker.mjs`

### patterns — Rejection pattern analysis
1. Read `modes/patterns.md` (standalone)
2. Run: `node analyze-patterns.mjs` — produces JSON output
3. Analyze: which archetypes get rejected, which companies ghost, score vs outcome correlation
4. Produce actionable recommendations

### followup — Follow-up cadence
1. Read `modes/followup.md` (standalone)
2. Run: `node followup-cadence.mjs` — produces JSON output
3. Flag overdue follow-ups
4. Generate draft follow-up messages
5. Update `data/follow-ups.md`

## Data integrity rules
- NEVER edit `applications.md` to ADD new entries — write TSV to `batch/tracker-additions/`
- YES you can edit `applications.md` to UPDATE status/notes of existing entries
- After any batch of changes, run `node merge-tracker.mjs`
- Health check available: `node verify-pipeline.mjs`
- Dedup available: `node dedup-tracker.mjs`
- Normalize statuses: `node normalize-statuses.mjs`

## Atomic writes
Never write directly to checkpoint.json or career-ops.json. Instead:
1. Write to `{filename}.tmp` in the same directory
2. Verify the temp file is valid JSON (parse it back)
3. Rename `{filename}.tmp` → `{filename}` (atomic)

## Feed corruption recovery
If reading the existing feed file fails (corrupted JSON from a previous crash), discard it and start from the default empty feed structure rather than failing.

## Feed update
After any tracking operation, update `~/.dream-studio/feeds/career-ops.json`:
```json
{
  "total_applications": 42,
  "by_status": { "Evaluated": 15, "Applied": 12, "Interview": 5, "Offer": 2, "Rejected": 8 },
  "pipeline_count": 7,
  "overdue_followups": 3,
  "last_updated": "ISO-8601"
}
```

**Feed validation (before writing):**
1. `schema_version` must be `1`
2. `last_updated` must be ISO-8601 string or `null`
3. `pipeline_count` must be integer >= 0
4. `recent_activity` must be an array with <= 10 items — truncate to last 10 before writing
5. If any check fails, log a warning and preserve the existing feed file (do not overwrite with invalid data)

## Activity log

After any tracking operation, append one line to `~/.dream-studio/career-ops/activity.log`:
```
{ISO-8601} | career-track | {mode} | {summary} | {outcome}
```
Examples:
- `2026-04-18T10:33:00Z | career-track | tracker | 42 total, 3 overdue | OK`
- `2026-04-18T10:34:00Z | career-track | pipeline | 5 URLs processed | OK`
- `2026-04-18T10:35:00Z | career-track | patterns | 8 rejections analyzed | OK`
