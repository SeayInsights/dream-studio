# Installed Platform Productization

Dream Studio is productized as a local installed platform: users select the
modules they need, keep source/build files separate from user-local state, and
interact through the global `ds` command surface instead of manually working
inside the source checkout.

## Install Model

| Area | Purpose |
| --- | --- |
| Source root | Installed Dream Studio source/build files and product code. |
| Dream Studio home | User-local runtime state, normally `~/.dream-studio`. |
| SQLite authority | `state/studio.db` inside the selected Dream Studio home. |
| Runtime config | `config/runtime.json` inside the selected Dream Studio home. |
| Adapter runtime | User-local adapter/router state under `adapters/` and `router/`. |
| Context packets | Fallback packets under `context-packets/` for unsupported tools. |
| Evidence and backups | Private local files under `meta/` and `backups/`. |

The installer and acceptance commands take `--source-root` and `--home` so
rehearsal installs, CI gates, and adapter launchers do not depend on the
current working directory.

## First-Run Setup

From any directory:

```powershell
python C:\path\to\dream-studio\interfaces\cli\ds.py `
  --source-root C:\path\to\dream-studio `
  --home C:\Users\you\.dream-studio `
  install --profile analytics_only
```

For rehearsal validation, include `--rehearsal` and point `--home` at a
temporary directory. Rehearsal setup creates fresh state, bootstraps SQLite,
writes runtime config, creates adapter/router/context-packet directories,
registers default adapter authority profiles, and previews context-packet
fallback without mutating the live installed state.

## Module Profiles

Supported installed profiles:

- `core`
- `analytics_only`
- `security_only`
- `telemetry_only`
- `dashboard_only`
- `adapter_router_only`
- `shared_intelligence_only`
- `full`

Unselected modules are disabled cleanly and should report honest empty states.
`analytics_only` works without hooks, agents, workflows, Claude, Codex, repo
mutation, or Docker. `security_only` works independently of Claude, Codex, and
Docker. `full` enables the complete local surface but still respects adapter
and live-state guardrails.

## Global Commands

The productized command surface includes:

```text
ds status
ds install
ds dashboard
ds validate
ds contract-atlas
ds adapters
ds context-packet
ds modules
ds router
ds acceptance
ds backup
ds restore-check
ds update-check
ds uninstall-check
```

On Windows, `ds.ps1` is a repo-owned launcher that can be placed on PATH or
invoked directly from any directory. It delegates to the canonical Python CLI
with an explicit source root:

```powershell
C:\path\to\dream-studio\ds.ps1 --home C:\temp\dream-studio status
```

The same commands are available through `python interfaces\cli\ds.py` for
portable scripting and tests.

## Adapter Setup

Supported AI tools should connect through Dream Studio adapter/router surfaces
where possible:

- CLI and app surfaces with a configured source/home use `ds adapters`,
  `ds router`, and shared-intelligence API routes.
- MCP-capable clients can use the router contract when configured.
- Unsupported plain web/chat tools use context-packet fallback.
- Unproven cloud or app environments must remain classified as unproven until
  evidence proves live consumption.

Adapter setup never treats private model memory as authority.

## Dashboard Onboarding

`ds dashboard` reports dashboard readiness and the derived API routes. It does
not start a server by itself. Dashboard-enabled profiles show derived empty
states when no runtime facts exist. Disabled profiles report that dashboard
routes are disabled by the selected module profile.

## Backup, Restore, Update, And Uninstall

`ds backup` plans a backup by default. `ds backup --execute` creates a
non-destructive backup in the selected Dream Studio home or explicit
`--backup-dir`.

`ds restore-check` validates a backup but does not restore it.

`ds update-check` compares installed SQLite state with the current migration
level without mutating the database.

`ds uninstall-check` inventories local files without deleting anything.

Live restore, update, or uninstall execution requires a separate
operator-approved scope.

## Acceptance Tests

Fresh-environment acceptance is exercised by:

```powershell
python interfaces\cli\ds.py `
  --source-root C:\path\to\dream-studio `
  --home C:\temp\dream-studio-productization `
  acceptance --profile analytics_only --profile security_only --profile full
```

The acceptance report validates fresh state creation, selected/unselected
profile behavior, dashboard status, adapter status, analytics-only independence,
security-only independence, full profile availability, backup/restore/update
checks, and uninstall dry-run behavior.
