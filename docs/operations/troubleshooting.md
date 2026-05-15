# Troubleshooting

This guide covers installed Dream Studio behavior for local users and adapter
operators. It avoids cleanup instructions that delete unknown files or mutate
live SQLite state.

## Command Cannot Find State

Symptom: `ds router` or `ds adapters` reports that SQLite authority is missing.

Check:

- Confirm `--home` or `DREAM_STUDIO_HOME` points at the intended Dream Studio
  home.
- Run `ds validate` with the same `--source-root` and `--home`.
- For rehearsal use, run `ds install --rehearsal --home <temp-home>` or
  `ds acceptance --home <temp-home>`.

Do not copy files from another runtime home unless a restore plan has been
approved.

## Current Directory Assumptions

Symptom: a command only works from the Dream Studio repo.

Check:

- Use `--source-root <dream-studio-source>` explicitly.
- Use `--home <dream-studio-home>` explicitly for installed or rehearsal state.
- On Windows, prefer the plain-command launcher `ds.cmd`, or run
  `ds install-command --execute` to create user-local `ds.cmd` and `ds.ps1`
  launchers in a PATH directory such as `%USERPROFILE%\.local\bin`.
- For packaged installs, verify `DREAM_STUDIO_SOURCE_ROOT` and
  `DREAM_STUDIO_HOME`.

Commands are expected to work from outside the repo.

## Unknown Module Profile

Symptom: install or acceptance reports an unknown profile.

Check `ds modules` for the supported profile ids:

- `core`
- `analytics_only`
- `security_only`
- `token_only`
- `telemetry_only`
- `dashboard_only`
- `adapter_router_only`
- `shared_intelligence_only`
- `full`

Do not edit runtime config by hand to invent a profile.

If a module exists in Contract Atlas but not in `ds modules`, check
`core.module_contracts`: module contracts describe boundaries, while installed
profiles describe selectable runtime packages.

## Dashboard Is Empty

Symptom: dashboard routes are available but show no facts.

This can be valid. Dream Studio uses honest empty states when selected modules
are installed but no runtime facts, telemetry, or readiness records exist yet.
Run `ds validate`, `ds modules`, and `ds contract-atlas` to confirm the runtime
surface is available. Run `ds contract-atlas-refresh` without `--execute` to
preview sanitized export and docs/PRD/README freshness without writing files.

## Adapter Is Unsupported Or Unproven

Symptom: an AI tool is classified as `context_packet_only` or
`not_proven_in_local_runtime`.

Use `ds context-packet --adapter <adapter>` for fallback context. Do not mark an
adapter as proven until live consumption evidence exists. Private model memory
is never Dream Studio authority.

## Analytics-Only Has No Hooks Or Agents

This is expected. `analytics_only` intentionally works without hooks, agents,
workflows, Claude, Codex, repo mutation, or Docker. If a command asks for those
dependencies in analytics-only mode, treat it as a product boundary bug.

## External Project Stays Paused

This is expected unless the current operator decision explicitly selects a
target and read-only scope. External targets such as DreamySuite, Bill Stack,
and TORII should not be read, scanned, validated, mutated, committed, pushed, or
deployed from stale route state. Use the external project validation pipeline to
plan target selection, dirty-state classification, validation profile, and Work
Order evidence before any target access.

## Docker Profile Is Unavailable

This is expected on local-first installs. Docker is optional and does not block
core, analytics-only, security-only, dashboard-only, shared-intelligence-only,
adapter-router-only, or full local operation. Do not start or build containers
while troubleshooting unless a current operator decision approves Docker
runtime validation.

## Analytics Import Shows No Data

`ds analytics-ingest --file <payload>` is a dry run. Add `--execute` only when
you intend to write normalized records to the selected SQLite authority. Verify
the same `--home` is used for ingest and dashboard/API checks.

If a payload omits a section, Dream Studio should show an honest empty state
for that section. Do not create placeholder projects, fake dependency edges,
fake costs, or synthetic findings to make a dashboard look populated.

## Restore Or Uninstall Requested

Use `ds restore-check` or `ds uninstall-check` first. These commands inspect the
selected local runtime home and do not restore or delete data. Live restore,
update, uninstall, cleanup, or deletion needs a separate approved scope.

## Secrets And Auth Files

Do not inspect or print secrets, auth tokens, cookies, private keys, or provider
credentials while troubleshooting. If a path looks like an auth store, classify
it as sensitive and route to operator review.

## AI Usage Cost Looks Unknown

This can be correct. Dream Studio records tokens and operational outcomes for
AI adapters, but it does not convert subscription-plan usage into API-dollar
costs. Check `ds router`, `ds adapters`, or
`/api/shared-intelligence/ai-usage-accounting` for the adapter billing mode,
token visibility, cost visibility, usage source, cost source, and confidence.

Only token-metered/API-metered/credit-metered usage with source-backed cost
metadata, or an explicit subscription allocation profile, should display a
reportable cost. Otherwise the dashboard should say `unknown`.

## Final Closeout Blocks

Final installed-platform closeout requires release gate evidence, docs drift
evidence, command-surface evidence, adapter status evidence, long-run cycle
evidence, publication-boundary evidence, and a live SQLite hash guard. A missing
evidence ref should remain a blocker instead of being normalized into a pass.
