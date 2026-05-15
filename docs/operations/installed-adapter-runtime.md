# Installed Adapter Runtime

Dream Studio should behave as an installed local orchestration layer. Normal
adapter and operator workflows should not require manually opening a shell in
the Dream Studio source checkout.

## Runtime Model

The installed runtime keeps source and state separate:

| Area | Location | Authority |
| --- | --- | --- |
| Source/build | Dream Studio checkout or installed source root | repo source |
| User-local state | `~/.dream-studio` or explicit `DREAM_STUDIO_HOME` | local runtime state |
| SQLite authority | `~/.dream-studio/state/studio.db` | canonical local SQLite |
| Adapter runtime | `~/.dream-studio/adapters` | user-local adapter state |
| Router runtime | `~/.dream-studio/router` | user-local router state |
| Context packets | `~/.dream-studio/context-packets` | user-local packet exports |
| Evidence | `~/.dream-studio/meta` | file-backed private evidence |

The source root can be supplied with `--source-root` or
`DREAM_STUDIO_SOURCE_ROOT`. The runtime home can be supplied with `--home` or
`DREAM_STUDIO_HOME`. Commands must not assume the current working directory is
the Dream Studio repo.

Runtime helpers that need the user-local Dream Studio home must honor
`DREAM_STUDIO_HOME` before falling back to `~/.dream-studio`. This keeps
rehearsals, CI gates, and installed adapter launches from touching the
operator's live runtime state unless a live update scope has been approved.

## Global Command Surface

The installed command surface is `ds`:

```text
ds status
ds dashboard
ds validate
ds contract-atlas
ds adapters
ds context-packet --adapter codex
ds modules
ds router
```

When running directly from a checkout before packaging, use:

```powershell
python C:\path\to\dream-studio\interfaces\cli\ds.py --source-root C:\path\to\dream-studio status
```

The command surface resolves source/state from explicit configuration, opens
SQLite authority through Dream Studio's existing bootstrap/access layer, and
prints JSON so shells, adapters, MCP clients, and dashboard tools can consume it.

## Adapter Router

The adapter router is a local read model exposed by:

- `ds router`
- `ds adapters`
- `/api/shared-intelligence/adapter-router`

It reports current route state, adapter health, context-packet availability,
Contract Atlas availability, module profile status, telemetry/evidence capture
capabilities, and adapter workspace hygiene. It does not execute adapters,
mutate routing policy, write adapter configs, or write live SQLite by default.

The shared-intelligence route surface also exposes
`/api/shared-intelligence/security-lifecycle`. That surface is a read-only
installed runtime capability for security classification and release-readiness
status; it does not run scans, inspect secrets, or write runtime state.

Supported adapter access modes:

| Mode | Meaning |
| --- | --- |
| `repo_attached` | Adapter reads repo-root projection files in an open checkout. |
| `cli_with_workdir` | Adapter invokes `ds` or tools with an explicit source root/workdir. |
| `app_workspace` | App has a configured workspace/source root. |
| `cloud_repo_environment` | Cloud environment can read repo files but local runtime is not proven. |
| `mcp_capable` | Client can call a local/MCP bridge when configured. |
| `context_packet_only` | Tool can consume exported packets but not local router APIs. |
| `unsupported` | No supported access path is currently proven. |

Current baseline:

- Claude Code CLI: `live_consumption_proven`
- Claude Code app/workspace:
  `live_consumption_proven_with_workspace_head_check`
- Codex CLI: `live_consumption_proven`
- Codex app configured environment: `live_consumption_proven`
- Codex cloud/GitHub environment: `not_proven_in_local_runtime`
- MCP-capable clients: `router_contract_available`
- shell tools: `supported_via_global_ds_command`
- plain web/chat tools: `context_packet_only`

## Module Profiles

Installed profiles are declared in `core.module_profiles`:

- `core`
- `analytics_only`
- `security_only`
- `telemetry_only`
- `dashboard_only`
- `adapter_router_only`
- `shared_intelligence_only`
- `full`

Each profile declares includes, excludes, dependencies, commands/routes, hook
requirements, agent/workflow requirements, Claude/Codex requirements, Docker
requirements, expected dashboard/API behavior, and honest empty states.

`analytics_only` must work without hooks, agents, workflows, Claude, Codex, repo
mutation, or Docker. It exposes read-only telemetry/shared-intelligence surfaces
and uses honest empty states when no facts exist.

## Rehearsal Install

Rehearsal installs must use a temporary Dream Studio home:

```powershell
python interfaces\cli\ds.py --source-root C:\path\to\dream-studio rehearsal-install --rehearsal-home C:\temp\dream-studio-home
```

This creates temp state, bootstraps SQLite, writes rehearsal runtime config,
creates adapter/router/context packet directories, registers default adapter
profiles, and previews a context packet. It does not mutate live installed
state.

## Live Update Readiness

After rehearsal passes, a live update may be planned, but it requires a separate
operator-approved scope before mutating `~/.dream-studio`. The live update plan
should copy or refresh only installed runtime/router config needed to point
adapters at the validated source root and local SQLite authority. It must not
delete, archive, compact, deduplicate, inspect secrets, run Docker, deploy, or
destructively migrate SQLite.
