# Local Runtime Operations

Dream Studio is local-first. The runtime database under the user data directory is the local canonical state for runtime activity. Dashboards, preflight checks, telemetry, adapter metadata, backups, and exported files can describe or copy that state, but they do not become the authority.

## Runtime DB Authority

The expected runtime database path is:

```text
~/.dream-studio/state/studio.db
```

The local DB remains authoritative unless an operator explicitly chooses a recovery action. Preflight and recovery dry-run commands inspect state only. They do not initialize, migrate, restore, downgrade, or repair the DB.

## Schema Version Skew

Schema version skew means the runtime DB and the current checkout do not agree on the latest applied migration.

- Compatible: DB version equals the latest migration file in the checkout.
- Migration available: DB version is older than the latest migration file. A future mutating setup/bootstrap can apply migrations after the operator verifies backups.
- DB newer than code: DB version is higher than the latest migration file in the checkout. Runtime bootstrap should stay blocked until the operator uses a checkout containing migrations greater than or equal to the DB version, or chooses an explicit backup restore path.
- Unknown: `_schema_version` is missing or unreadable. Inspect backups before running mutating commands.

Do not manually edit `_schema_version`. Changing that row does not change the actual schema and can make the runtime misinterpret local canonical state.

## Read-Only Checks

Run the local runtime preflight:

```powershell
python interfaces/cli/runtime_preflight.py --json
```

Run the recovery dry-run diagnostic:

```powershell
python interfaces/cli/runtime_recovery.py --dry-run --json
```

The recovery dry-run reports:

- current runtime DB path, existence, schema version, and compatibility
- latest migration version in the checkout
- local backup candidates such as `studio.db.bak`, timestamped `studio-*.db.bak` files, `studio-cloud-pull.db.bak`, and `studio.db.pre-restore.bak`
- backup sizes and modified timestamps
- backup schema compatibility
- recommended next operator action

The dry-run does not call backup, restore, migration, dashboard launch, external provider, or cloud commands.

Read-only DB access policy:

- Read-only native DB access must not create `~/.dream-studio`, `state`, or `studio.db`.
- Read-only native DB access must open existing DB files with SQLite URI `mode=ro`.
- Read-only native DB access must not configure WAL or other write-oriented pragmas on the native DB.
- Missing read-only DB access must fail or report missing state clearly instead of initializing local state.
- Code that needs a path for inspection should compute the canonical path without calling mutating path helpers.

## Native Readiness Gate Policy

Dream Studio uses one policy for DB-newer-than-code readiness:

- `runtime_preflight.py --json` is read-only and exits nonzero when the current runtime DB is `blocked_newer_than_code`.
- `runtime_recovery.py --dry-run --json` is read-only and exits zero while reporting `action_required`; it is diagnostic, not a bootstrap gate.
- `setup.py --check` is an advisory doctor check. It exits zero when its basic prerequisites pass, but it must print `blocked_newer_than_code` as a readiness blocker. Treat that output as a stop sign before running mutating setup.
- `ds_dashboard.py --check` is a readiness gate. It exits nonzero when the runtime DB is newer than the checkout.
- Dashboard bootstrap fails before opening a mutating DB connection when the runtime DB is newer than the checkout.
- `check_migrations.py` exits nonzero before opening the normal migration connection when the runtime DB is newer than the checkout.
- `verify_migrations.py` exits nonzero after read-only inspection and does not attempt migration when the runtime DB is newer than the checkout.

All DB-newer-than-code messages should include the current DB schema version, the checkout's latest migration version, and these operator actions:

- run `python interfaces/cli/runtime_preflight.py --json`
- run `python interfaces/cli/runtime_recovery.py --dry-run --json`
- use a checkout with migrations greater than or equal to the DB version
- inspect backups before restore decisions
- do not manually edit `_schema_version`

On Windows, use the PowerShell command surface for local verification:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 verify
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 verify-guarded
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 setup-check
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 dashboard-check
```

GNU make is not required on Windows. The guarded targets wrap normal validation in
`scripts/runtime_state_hash_guard.py` and fail if `studio.db`, `studio.db.bak`, or
`studio.db.pre-restore.bak` change during validation. They are an operator safety
guard, not a replacement authority layer.

## Restore-Plan Preview

Use restore-plan preview only after choosing a specific local backup candidate to inspect:

```powershell
python interfaces/cli/runtime_recovery.py --plan-restore --source "<backup-path>" --json
```

The preview is still read-only. It requires `--source` so an operator must name the exact backup under consideration. It reports:

- current runtime DB schema version and status
- source backup schema version and status
- whether the source is older, equal to, or newer than the current runtime DB
- whether the source is compatible with this checkout
- the exact files a future restore would read
- the exact files a future restore would write
- the planned pre-restore safety copy path
- hashes before and after plan inspection
- warnings for data loss or checkout incompatibility

An older backup is risky even when it is compatible with the checkout. Restoring it can discard local runtime state that was written after the backup was created. Treat that as a data-loss decision, not as a routine repair.

The restore-plan preview does not restore anything. It also does not create the safety copy it describes. A future mutating restore command must capture proof before it writes:

- current DB hash and schema version
- source backup hash and schema version
- pre-restore safety copy path
- safety copy hash after creation
- restored DB hash and schema version after copy
- read-only preflight result after restore

## Backup Inspection

Treat backups as candidate copies, not automatic authority. A backup is useful only after confirming:

- the file is readable as SQLite
- its schema version is compatible with the checkout or can be migrated by that checkout
- its modified time and file size make sense for the intended recovery point
- the operator has explicitly decided to restore it

The default local backup is:

```text
~/.dream-studio/state/studio.db.bak
```

Other local candidates may exist if export, cloud-pull, or pre-restore tooling has been used.

Full DB backups, backup exports, restores, and optional cloud backup transfers are not redacted exports. They copy private local runtime state and require explicit operator intent. Cloud backup is transport only; it is not cloud, org, or global runtime authority.

## Decision Tree

1. If the current DB is compatible, no recovery action is needed.
2. If the current DB is older than code, verify or create a backup before running any mutating setup or bootstrap command.
3. If the current DB is newer than code, prefer switching to a checkout with migrations greater than or equal to the DB version.
4. If a compatible backup exists, inspect it with the dry-run and restore only after an explicit operator decision.
5. If no compatible checkout or backup exists, stop and preserve the current DB and backups for manual analysis.

Never treat dashboard output, preflight output, telemetry, adapter metadata, or backup metadata as canonical runtime state. They are diagnostic evidence about the local DB.

## Intentionally Not Automated

Dream Studio does not automatically:

- downgrade the runtime DB
- edit `_schema_version`
- restore a backup
- overwrite `studio.db`
- delete or rewrite backup files
- run migrations from read-only checks
- use cloud or organization sync as runtime authority

Any future recovery command that mutates state must require explicit operator intent, preserve a safety copy, and keep local canonical runtime state as the authority.

## Docker Clean-Room Relationship

Docker clean-room validation is an optional harness for proving fresh-install behavior from disposable isolated state. It must not mount or hide the native local runtime state while the DB version-skew condition is unresolved. A passing Docker clean-room check does not resolve native DB version skew and does not replace read-only inspection of the local DB.
