# Career-Scan — Portal Discovery

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Paths
Read `~/.dream-studio/career-ops/config.yml` to get `career_studio_path`.
Read `{career_studio_path}/config/career-ops-paths.yml` to resolve all paths.

## Resume check

Before starting a new scan, check `~/.dream-studio/career-ops/checkpoint.json`:
- If `status` is `"partial"` and `last_action` is `"scan"`:
  1. Read `portals_completed` from the checkpoint
  2. Show user: "Found incomplete scan ({portals_completed} portals done, {portals_remaining} remaining). Resume?"
  3. If user confirms: skip completed portals, resume from next portal in the list
  4. If user declines: set checkpoint `status` to `"abandoned"` and start a fresh full scan

## Context loading
1. Read `modes/_shared.md` + `modes/scan.md` for execution instructions
2. Read `portals.yml` for company list and search config
3. Read `data/scan-history.tsv` for dedup

## Execution
Follow `modes/scan.md` exactly. Key behaviors:
- Scan configured portals for new job postings
- Deduplicate against `data/scan-history.tsv`
- Add new findings to `data/pipeline.md`
- Log scan to `data/scan-history.tsv`

## Subagent requirement
This skill MUST run as a subagent — it is long-running and may use Playwright.

**Playwright safety:** NEVER run 2+ Playwright instances in parallel. If another career skill is using Playwright (apply, batch), wait or fail fast with a message.

## Checkpoint
After scan completes, write checkpoint:
```json
{
  "last_action": "scan",
  "timestamp": "ISO-8601",
  "status": "idle",
  "portals_scanned": 45,
  "new_offers_found": 7,
  "duplicates_skipped": 12,
  "pipeline_count": 19
}
```

If context pressure forces an early stop mid-scan:
- Finish the current portal (don't stop mid-portal)
- Write checkpoint with `"status": "partial"`, `"portals_completed": [list]`, and `"portals_remaining": [list]`
- The resume check (above) will offer to continue from where it left off

## Feed update
Update `~/.dream-studio/feeds/career-ops.json` with:
- `last_scan` timestamp
- `pipeline_count` (total pending URLs)
- `new_offers_found` from this scan

**Feed validation (before writing):**
1. `schema_version` must be `1`
2. `last_updated` must be ISO-8601 string or `null`
3. `pipeline_count` must be integer >= 0
4. `recent_activity` must be an array with <= 10 items — truncate to last 10 before writing
5. If any check fails, log a warning and preserve the existing feed file (do not overwrite with invalid data)

## Activity log

After scan completes, append one line to `~/.dream-studio/career-ops/activity.log`:
```
{ISO-8601} | career-scan | scan | {portals_scanned} portals | {new_offers_found} new offers | {outcome}
```
Outcome: `OK`, `PARTIAL ({portals_completed} done)`, or `ERROR (reason)`.

## Feed corruption recovery
If reading the existing feed file fails (corrupted JSON from a previous crash), discard it and start from the default empty feed structure rather than failing.

## Atomic writes
Never write directly to checkpoint.json or career-ops.json. Instead:
1. Write to `{filename}.tmp` in the same directory
2. Verify the temp file is valid JSON
3. Rename `{filename}.tmp` → `{filename}` (atomic)

## Playwright lock
Before ANY Playwright operation:
1. Check `~/.dream-studio/career-ops/playwright.lock`
2. If exists and <10 min old → fail: "Playwright is busy"
3. If absent or stale → create lock with `{"skill": "career-scan", "started": "ISO-8601"}`
4. Delete lock in finally block after Playwright finishes

## Error handling
- If a portal times out or returns 403, log it and continue to next portal
- After scan, report which portals succeeded and which failed
- Never silently drop failed portals — the user needs to know
- If ALL portals fail, warn: "All portals failed. Check network connection or portals.yml config."
