# `ds restore` Contract

Status: active
Command: `ds restore <backup>`
Engine: `core.installed_productization.restore_runtime`
Preview (mandatory): `ds restore-check --backup-path <backup>` / `ds restore <backup>` (no `--execute`)

## Purpose

`ds restore <backup>` is the mutating counterpart to `ds restore-check` (which
only validates a backup). It replaces the Dream Studio state-tier databases from
a chosen backup, and is itself reversible: it always takes a pre-restore backup of
the current state before overwriting anything. It is the companion to the
backup-before-mutation pattern used by install / update / `uninstall --purge-state`.

## Flags

| Flag | Effect |
|------|--------|
| `<backup>` (positional) | Path to the backup directory to restore from. |
| _(no `--execute`)_ | Dry-run. Validates the backup and prints the plan. Mutates nothing. |
| `--execute` | Apply the restore: pre-restore backup first, then replace state. |
| `--force` | Restore even when the backup is not restore-ready (missing manifest/dir). |
| `--backup-dir <dir>` | Where the pre-restore backup is written (default: outside the home). |

## Behavior

### Dry-run (default)
- Validates the backup via `restore_runtime_check`.
- Returns `status: planned` with `restorable_files` and `restore_ready`.
- **Removed/changed:** nothing.

### Execute (`--execute`)
1. **Pre-restore safety backup FIRST** — the current state is backed up via
   `backup_runtime` to a directory **outside** the home (default
   `<home>-restore-backups`) so the restore is reversible and the backup cannot be
   clobbered by the restore itself. `pre_restore_backup_path` is returned.
2. **Replace state** — the state-tier databases present in the chosen backup
   (`studio.db`, and `files.db` if present) are copied into `<home>/state/`.
3. Returns `status: restored` with `restored_files` and `pre_restore_backup_path`.

### Refusal
- A backup that is not restore-ready (missing backup dir or `studio.db`) is
  refused with `status: refused` and no mutation, unless `--force` is given.

## Invariants

1. Default invocation mutates nothing (`--execute` required to apply).
2. A restore always takes a pre-restore backup of current state FIRST.
3. The pre-restore backup is written outside the home so it survives the restore.
4. Restore consumes the exact backup directory named on the command line
   (consistent with the `studio-pre-*` / `backup-*` naming install/update create).
5. `ds restore-check` remains the non-destructive validation preview.
