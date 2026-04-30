---
name: career-apply
description: "Live application assistant (form fill + answer generation) and batch processing. Modes: apply (single), batch (parallel workers). Trigger via /career-ops apply or /career-ops batch."
pack: career
chain_suggests: []
---

# Career-Apply — Application Engine

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Paths
Read `~/.dream-studio/career-ops/config.yml` to get `career_studio_path`.
Read `{career_studio_path}/config/career-ops-paths.yml` to resolve all paths.

## Modes

### apply — Single application
1. Read `modes/_shared.md` + `modes/apply.md`
2. Navigate to application form via Playwright
3. Extract form questions via `browser_snapshot`
4. Generate answers using CV + evaluation report context
5. Fill form fields — **NEVER click Submit**. Always stop and show the user.
6. Runs as subagent (Playwright required)

### batch — Parallel processing
1. Read `modes/_shared.md` + `modes/batch.md`
2. Read `batch/batch-prompt.md` for worker configuration
3. Process URLs from pipeline or specified list
4. Spawn workers — respect Playwright limit (1 concurrent max)
5. Runs as subagent (long-running, spawns sub-workers)

## Batch checkpoint (critical)
Before starting batch, write initial checkpoint:
```json
{
  "last_action": "batch",
  "timestamp": "ISO-8601",
  "status": "in_progress",
  "total": 15,
  "completed": [],
  "pending": ["url1", "url2", "..."],
  "failed": [],
  "current": null
}
```

After EACH offer completes, update checkpoint:
```json
{
  "completed": ["url1", "url2"],
  "pending": ["url3", "..."],
  "current": "url3",
  "last_completed_at": "ISO-8601"
}
```

This enables resume after crash — the next session reads checkpoint, skips completed URLs, resumes from `pending[0]`.

## Batch resume
If `~/.dream-studio/career-ops/checkpoint.json` has `"status": "in_progress"` and `"last_action": "batch"`:
1. Read the checkpoint
2. Show user: "Found incomplete batch: {completed.length}/{total} done. Resume?"
3. If yes, continue from `pending[0]`
4. If no, mark checkpoint as `"status": "abandoned"`

## Feed update
After each application or batch completion, update feed with application counts.

**Feed validation (before writing):**
1. `schema_version` must be `1`
2. `last_updated` must be ISO-8601 string or `null`
3. `pipeline_count` must be integer >= 0
4. `recent_activity` must be an array with <= 10 items — truncate to last 10 before writing
5. If any check fails, log a warning and preserve the existing feed file (do not overwrite with invalid data)

## Feed corruption recovery
If reading the existing feed file fails (corrupted JSON from a previous crash), discard it and start from the default empty feed structure rather than failing.

## Atomic writes (all checkpoint and feed updates)
Never write directly to checkpoint.json or career-ops.json. Instead:
1. Write to `{filename}.tmp` in the same directory
2. Verify the temp file is valid JSON (parse it back)
3. Rename `{filename}.tmp` → `{filename}` (atomic on all OSes)
This prevents partial writes from corrupting state on crash.

## Playwright lock
Before ANY Playwright operation:
1. Check if `~/.dream-studio/career-ops/playwright.lock` exists
2. If it exists AND was modified less than 10 minutes ago → fail with: "Playwright is busy (another career skill is running). Wait or delete ~/.dream-studio/career-ops/playwright.lock"
3. If it doesn't exist or is stale (>10 min old) → create the lock file with `{"pid": <current>, "skill": "career-apply", "started": "ISO-8601"}`
4. After Playwright finishes (success or error), delete the lock file
5. Always delete in a finally block — never leave stale locks

## Activity log

After each application or batch run, append one line to `~/.dream-studio/career-ops/activity.log`:
```
{ISO-8601} | career-apply | {mode} | {summary} | {outcome}
```
Examples:
- `2026-04-18T10:31:00Z | career-apply | apply | Stripe Senior Engineer | form filled | OK`
- `2026-04-18T10:32:00Z | career-apply | batch | 3/10 completed | PARTIAL (context threshold)`

## Safety
- NEVER submit an application without user review
- NEVER run 2+ Playwright instances in parallel — enforced by lock file above
- Quality over quantity — strongly discourage low-fit applications (score < 4.0)
