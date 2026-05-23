# Spool Archive Disaster Recovery

**System:** Dream Studio spool lifecycle (OD8)
**Audience:** Operators performing recovery after data loss

---

## Overview

The spool system is the event ingestion pipeline for Dream Studio. Every Claude Code session, tool call, and agent action enters as a raw JSON file in the spool inbox, is ingested into SQLite, and then progresses through the lifecycle stages below. Compressed archives serve as the durable backup layer — SQLite is reconstructable from them.

**Lifecycle stages:**

| Stage | Path | Purpose |
|-------|------|---------|
| Inbox | `~/.dream-studio/events/spool/` | Awaiting ingest |
| In-flight | `~/.dream-studio/events/processing/` | Actively being ingested |
| Done | `~/.dream-studio/events/processed/` | Successfully ingested into SQLite |
| Failed | `~/.dream-studio/events/failed/` | Ingest errors (reasons in `reasons/` subfolder) |
| Archive | `~/.dream-studio/events/archives/` | Weekly and yearly compressed backups |

SQLite (`~/.dream-studio/studio.db`) holds the queryable record. The archives hold the source-of-truth files that SQLite was built from. If SQLite is lost, replay from archives rebuilds it.

---

## Normal Operation

The projection runner daemon (`core/projections/runner.py`) manages archiving automatically. No OS-level scheduled tasks are required on Windows.

### Weekly archiving

- **Trigger:** Every Monday at daemon startup, and every 24 hours thereafter
- **What it does:** Bundles all `processed/` files from the prior Mon–Sun week into `spool-processed-YYYY-MM-DD.zip` (Monday-dated), stores the zip in `archives/`, verifies the zip, then deletes the originals from `processed/`
- **Example archive name:** `spool-processed-2026-05-18.zip` (covers Mon 2026-05-18 through Sun 2026-05-24)
- **Idempotent:** If the archive for that week already exists, the step is skipped

### Yearly consolidation

- **Trigger:** Every January 1
- **What it does:** Bundles all prior-year weekly archives into `spool-processed-YYYY.zip`, verifies, then deletes the weekly archives
- **Example:** `spool-processed-2025.zip` replaces all `spool-processed-2025-*.zip` files
- **Idempotent:** Skipped if the year archive already exists

The daemon also calls `spool.lifecycle.check_and_archive()` at startup, so restarting the daemon will catch up any missed archiving cycles immediately.

---

## Manual Controls

All spool commands run from the dream-studio-clean repo root:

```powershell
cd "C:\Users\Dannis Seay\builds\dream-studio-clean"
```

### Trigger weekly archive immediately

```powershell
py -m interfaces.cli.ds spool archive
```

Runs the same logic as the daemon's scheduled cycle. Safe to run at any time — idempotent.

### Trigger yearly consolidation

```powershell
# Consolidate the current year (auto-detected)
py -m interfaces.cli.ds spool consolidate-year

# Consolidate a specific prior year
py -m interfaces.cli.ds spool consolidate-year 2025
```

### List all archives

```powershell
py -m interfaces.cli.ds spool archives list
```

Output includes archive name, file size, and date range covered. Example:

```
spool-processed-2026-05-11.zip   2.1 MB   2026-05-11 to 2026-05-17
spool-processed-2026-05-18.zip   3.4 MB   2026-05-18 to 2026-05-24
spool-processed-2026.zip        47.2 MB   2026 (yearly)
```

### Inspect an archive

```powershell
py -m interfaces.cli.ds spool archives inspect spool-processed-2026-05-18.zip
```

Lists all event files inside the archive without extracting them. Use this to confirm an archive contains the events you need before running a restore.

---

## Monitoring

### Check archive health

```powershell
py -m interfaces.cli.ds spool archives list
```

Watch for:
- **Gaps in the Monday sequence** — a missing weekly archive means those events were never archived (check if `processed/` still holds the originals)
- **Archives older than 7 days without a newer one** — may indicate the daemon is not running or archiving is failing
- **Zero-byte archives** — run `inspect` to verify contents; a failed zip write leaves a corrupt file

### Check daemon status

```powershell
py -m interfaces.cli.ds projection status
```

The daemon logs archiving activity. If the last run timestamp is stale by more than 48 hours, restart the daemon:

```powershell
py -m interfaces.cli.ds projection daemon
```

### Check for unarchived processed files

```powershell
Get-ChildItem "$env:USERPROFILE\.dream-studio\events\processed\" | Measure-Object | Select-Object -ExpandProperty Count
```

Under normal operation, `processed/` drains to zero each Monday. A large accumulation after Monday indicates the archive step did not run.

---

## Disaster Recovery Procedure

Use this procedure when SQLite (`studio.db`) is lost, corrupted, or missing events.

### Step 1: Identify the missing date range

Query SQLite to find the gap, or note the date range of the corruption. If SQLite is entirely gone, the gap is everything prior to the last known-good backup.

```powershell
# Example: check latest event timestamp in SQLite
py -c "
import sqlite3, pathlib
db = pathlib.Path.home() / '.dream-studio' / 'studio.db'
conn = sqlite3.connect(db)
row = conn.execute('SELECT MAX(timestamp) FROM canonical_events').fetchone()
print('Latest event in SQLite:', row[0])
conn.close()
"
```

### Step 2: Find the relevant archive(s)

```powershell
py -m interfaces.cli.ds spool archives list
```

Match archives to the date range identified in Step 1. Weekly archives are Monday-dated; a Monday date covers that Mon through the following Sun.

### Step 3: Inspect the archive to confirm it contains expected events

```powershell
py -m interfaces.cli.ds spool archives inspect spool-processed-2026-05-18.zip
```

Confirm the file count and event filenames look correct before proceeding.

### Step 4: Dry-run the restore

```powershell
py scripts\spool_restore.py spool-processed-2026-05-18.zip --dry-run
```

The dry run prints what would be extracted and replayed without writing anything. Review the output to verify the correct events will be processed.

### Step 5: Execute the restore

```powershell
py scripts\spool_restore.py spool-processed-2026-05-18.zip
```

The restore script:
1. Extracts event files from the archive into a temporary staging area
2. Replays each file through the standard ingest pipeline
3. Skips events that are already present in SQLite (idempotent by event ID)
4. Reports counts: replayed, skipped (duplicate), failed

Repeat Steps 3–5 for each archive covering the missing date range, in chronological order.

### Step 6: Verify events appear in SQLite

```powershell
py -c "
import sqlite3, pathlib
db = pathlib.Path.home() / '.dream-studio' / 'studio.db'
conn = sqlite3.connect(db)
# Count events in the restored date range
rows = conn.execute('''
    SELECT DATE(timestamp) as day, COUNT(*) as events
    FROM canonical_events
    WHERE timestamp >= '2026-05-18' AND timestamp < '2026-05-25'
    GROUP BY day ORDER BY day
''').fetchall()
for day, count in rows:
    print(f'{day}: {count} events')
conn.close()
"
```

Confirm event counts are plausible for the date range. Cross-reference with the file count from the archive inspect output in Step 3.

---

## Recovery Scenarios

### Scenario A: SQLite lost; processed/ files still intact

The weekly archive has not run yet and the originals are still in `processed/`.

```powershell
# Trigger standard ingest from processed/ directly
py -m interfaces.cli.ds spool archive       # archives first (creates the zip)
py scripts\spool_restore.py spool-processed-2026-05-18.zip   # then restore
```

Alternatively, if the daemon is healthy, restart it — it will re-ingest any files it finds in `spool/` or re-archive `processed/` on its next cycle.

### Scenario B: SQLite lost; processed/ already archived

The standard full-recovery procedure (Steps 1–6 above). Identify the date range, find the archives, dry-run, restore, verify.

For a full loss spanning multiple weeks:

```powershell
# List all archives to get the full set
py -m interfaces.cli.ds spool archives list

# Restore each weekly archive in order
py scripts\spool_restore.py spool-processed-2026-04-06.zip
py scripts\spool_restore.py spool-processed-2026-04-13.zip
py scripts\spool_restore.py spool-processed-2026-04-20.zip
# ... continue through the gap
```

If a yearly archive covers part of the range, restore it first, then layer the weekly archives on top (the restore is idempotent — duplicates are skipped).

```powershell
py scripts\spool_restore.py spool-processed-2025.zip
py scripts\spool_restore.py spool-processed-2026-01-05.zip
# ...
```

### Scenario C: Partial loss — some events in SQLite, some only in archives

Run the restore across the full suspected date range. The restore script skips events already present in SQLite by event ID, so there is no risk of double-counting. Over-restoring is safe; under-restoring leaves gaps.

```powershell
# Safe to restore the whole week even if SQLite has some of it
py scripts\spool_restore.py spool-processed-2026-05-18.zip
# Output will report how many were replayed vs. skipped as duplicates
```

---

## Verification

After any recovery, confirm the following:

**1. Event count is plausible**

```powershell
py -c "
import sqlite3, pathlib
db = pathlib.Path.home() / '.dream-studio' / 'studio.db'
conn = sqlite3.connect(db)
total = conn.execute('SELECT COUNT(*) FROM canonical_events').fetchone()[0]
print(f'Total canonical events: {total}')
conn.close()
"
```

**2. No date gaps in the recovered range**

The per-day query from Step 6 should show contiguous days with non-zero counts. A day showing zero during an active session window indicates a missed archive.

**3. Projections are consistent**

After restoring events, rebuild any projections that depend on the restored date range:

```powershell
py -m interfaces.cli.ds projection rebuild --all
```

**4. Spool inbox is clean**

```powershell
Get-ChildItem "$env:USERPROFILE\.dream-studio\events\spool\" | Measure-Object | Select-Object -ExpandProperty Count
```

Should be zero or near-zero after recovery. Any files left in `spool/` will be ingested on the next daemon cycle.

---

## Limitations and Known Gaps

**Failed events are not archived.**
Files in `~/.dream-studio/events/failed/` are excluded from weekly archiving. They represent events that could not be parsed or ingested. The `reasons/` subfolder contains error logs. These must be remediated manually before they can enter the archive pipeline.

**In-flight events at crash time may require manual attention.**
Files in `~/.dream-studio/events/processing/` were mid-ingest when the process stopped. After a crash or hard restart, check this folder:

```powershell
Get-ChildItem "$env:USERPROFILE\.dream-studio\events\processing\"
```

If files are present and the daemon is not running, move them back to `spool/` for re-ingest:

```powershell
Move-Item "$env:USERPROFILE\.dream-studio\events\processing\*" `
          "$env:USERPROFILE\.dream-studio\events\spool\"
```

The ingest pipeline is idempotent on event ID, so re-processing a file that was partially committed is safe.

**Archives do not include spool/ inbox files.**
Events that never completed ingest (sitting in `spool/` at backup time) are not captured in archives. If the machine is lost with files in `spool/`, those events are unrecoverable from the archive system.

**No cross-machine replication.**
Archives are stored locally in `~/.dream-studio/events/archives/`. For true disaster recovery (machine loss, drive failure), these archives must be copied to an external location separately. The spool system does not handle offsite backup.

**Yearly archives replace weekly archives.**
After consolidation, the weekly archives for the prior year are deleted. If you need to inspect a specific week from a prior year, you must extract it from the yearly zip:

```powershell
Expand-Archive "$env:USERPROFILE\.dream-studio\events\archives\spool-processed-2025.zip" `
               -DestinationPath "C:\Temp\spool-2025-extract"
# Then inspect or restore the individual weekly zip found inside
```
