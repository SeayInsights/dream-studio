# Dream Studio CLI Reference

Complete reference for all `ds` CLI commands.

**Entry point:** `py -m interfaces.cli.ds <command> [options]`  
**Global flags:** `--source-root PATH` (DS repo root), `--home PATH` (DS state root)

---

## Core System

| Command | Description |
|---------|-------------|
| `ds status` | Show installed runtime status |
| `ds version` | Show source and runtime version |
| `ds doctor [--fix]` | Verify Claude Code integration health (skills, agents, hooks, routing, schema) |
| `ds repair` | Plan repair actions without mutating state |
| `ds validate` | Verify DB health (schema version, migrations, module profiles) |
| `ds adapters` | Show adapter status |
| `ds modules` | Show module profile status |
| `ds router` | Show adapter router status |
| `ds platform-hardening` | Show platform hardening status |

---

## Dashboard

| Command | Description |
|---------|-------------|
| `ds dashboard` | Show dashboard status |
| `ds dashboard --serve [--host HOST] [--port PORT]` | Serve the local dashboard |
| `ds dashboard --open` | Open dashboard in browser |
| `ds dashboard --check [--timeout-seconds N]` | Probe readiness without opening |

---

## Installation & Updates

| Command | Description |
|---------|-------------|
| `ds update [--dry-run]` | Update Dream Studio integration pack |
| `ds update-check` | Check update readiness without mutation |
| `ds install [--profile NAME] [--rehearsal] [--check-legacy]` | Run first-run setup for selected profiles |
| `ds install-command [--command-dir DIR] [--execute]` | Install user-local launcher for the plain `ds` command |
| `ds acceptance [--profile NAME]` | Run installed platform acceptance against a rehearsal home |
| `ds rehearsal-install --rehearsal-home PATH` | Bootstrap a rehearsal runtime |
| `ds backup [--backup-dir DIR] [--execute]` | Plan or create a runtime backup |
| `ds restore-check --backup-path PATH` | Validate a backup without restoring it |
| `ds rollback-check --backup-path PATH` | Validate a legacy-upgrade backup |
| `ds uninstall-check` | Inventory uninstall targets without deleting |
| `ds migrate-legacy [--dry-run\|--execute]` | Plan or execute a guarded legacy install migration |
| `ds repair-adapters [--execute]` | Plan or repair Dream-Studio-owned adapter surfaces |

---

## Integration

| Command | Description |
|---------|-------------|
| `ds integrate detect` | List detected AI tools and their config roots |
| `ds integrate status` | One-line integration health summary per tool |
| `ds integrate doctor [TOOL]` | Full health report for a tool (default: claude_code) |
| `ds integrate plan TOOL [--scope {user\|project}]` | Print dry-run file operation plan |
| `ds integrate install TOOL [--scope {user\|project}] [--dry-run\|--execute]` | Install integration for a tool |

---

## Projects

| Command | Description |
|---------|-------------|
| `ds project register --name NAME --path DIR [--description DESC]` | Register a new project |
| `ds project list [--status STATUS] [--include-deleted]` | List registered projects |
| `ds project status PROJECT_ID` | Show milestone/WO summary for a project |
| `ds project next PROJECT_ID` | Return the first open work order for a project |
| `ds project set-active PROJECT_ID` | Set the active project |
| `ds project deactivate PROJECT_ID` | Deactivate a project |
| `ds project start PROJECT_ID [--planning-root DIR]` | Activate project and start its next open WO |
| `ds project delete PROJECT_ID [--confirm]` | Delete a project and all dependents |
| `ds project state [--planning-root DIR]` | Full state: active project, next WO, gates, brief, tasks, gotchas |

---

## Work Orders

| Command | Description |
|---------|-------------|
| `ds work-order start WO_ID [--planning-root DIR]` | Start a work order, write context.md |
| `ds work-order list [--project PROJECT_ID] [--status STATUS]` | List work orders |
| `ds work-order close WO_ID [--force] [--planning-root DIR]` | Close a work order (gate-checked) |
| `ds work-order block WO_ID --reason REASON` | Block a work order |
| `ds work-order unblock WO_ID` | Unblock a work order |
| `ds work-order task-done WO_ID TASK_ID [--planning-root DIR]` | Mark a task complete, update context.md |
| `ds work-order tasks WO_ID` | List tasks for a work order |
| `ds work-order add-tasks WO_ID --from-file FILE` | Parse tasks.md and insert tasks |

---

## Milestones

| Command | Description |
|---------|-------------|
| `ds milestone close MS_ID [--force] [--planning-root DIR]` | Close a milestone (runs verification sequence) |
| `ds milestone list PROJECT_ID` | List milestones for a project |
| `ds milestone status MS_ID [--planning-root DIR]` | Show milestone detail and open gate checks |

---

## Tasks

| Command | Description |
|---------|-------------|
| `ds task set-active TASK_ID` | Set the active task context |
| `ds task active` | Show the current active task |
| `ds task clear-active` | Clear the active task context |

---

## Design Briefs

| Command | Description |
|---------|-------------|
| `ds design-brief show PROJECT_ID` | Show design brief for a project |
| `ds design-brief create PROJECT_ID` | Create a draft design brief |
| `ds design-brief lock BRIEF_ID` | Lock a design brief (human approval gate) |
| `ds design-brief update BRIEF_ID --field FIELD --value VALUE` | Update a field on a draft brief |
| `ds design-brief set-system BRIEF_ID SYSTEM` | Set design system (`tech-minimal`, `editorial-modern`, `brutalist-bold`, `playful-rounded`, `executive-clean`) |

---

## Skills

| Command | Description |
|---------|-------------|
| `ds skill invoke SPECIFIER [--target PATH] [--work-order WO_ID] [--project PROJECT_ID]` | Invoke a skill (`pack:mode` format, e.g. `core:build`) |
| `ds skill list [--pack PACK]` | List available skills |

---

## Workflows

| Command | Description |
|---------|-------------|
| `ds workflow start YAML_PATH [--name NAME]` | Initialise a workflow from a YAML file |
| `ds workflow status [WF_KEY]` | Show workflow status |
| `ds workflow list` | List all active workflows |
| `ds workflow advance WF_KEY [--dry-run]` | Execute the next wave of ready nodes |
| `ds workflow run WF_KEY [--dry-run] [--non-interactive]` | Run workflow to completion |

---

## Projections

| Command | Description |
|---------|-------------|
| `ds projection list` | List all projections with state |
| `ds projection status NAME` | Detailed status for one projection |
| `ds projection rebuild NAME` | Drop and rebuild a projection from canonical events |
| `ds projection dead-letter list [--projection NAME]` | List dead-letter entries |
| `ds projection dead-letter retry EVENT_ID` | Re-queue a dead-letter entry |
| `ds projection dead-letter resolve EVENT_ID` | Mark dead-letter entry resolved |
| `ds projection daemon status` | Check if daemon is running |
| `ds projection daemon start` | Print daemon start instructions |
| `ds projection daemon stop` | Stop the running daemon |

---

## Memory & Learning

| Command | Description |
|---------|-------------|
| `ds memory ingest [--project PROJECT] [--sessions-dir DIR] [--planning-dir DIR] [--dry-run]` | Ingest session history and planning files |
| `ds memory ingest-sessions [--claude-projects-dir DIR] [--dry-run]` | Harvest intelligence from Claude Code session history |
| `ds memory ingest-entries [--dry-run]` | Sync gotchas, lessons, corrections into memory_entries |
| `ds memory ingest-status` | Show last automated ingestion run status |
| `ds memory dedup-orphans [--execute]` | Remove NULL-source_type memory_entries with content-matched counterparts |
| `ds learn review [--limit N] [--batch]` | Interactive review of pending classified signals |
| `ds learn expand [--extension-id ID] [--batch]` | Compile personalization/capability/onboarding extensions |

---

## Spool & Events

| Command | Description |
|---------|-------------|
| `ds spool ingest` | Process all pending spool events |
| `ds spool archive` | Bundle prior-week processed files into a dated zip |
| `ds spool consolidate-year [YEAR]` | Bundle prior-year weekly archives into a yearly zip |
| `ds spool archives list` | List .zip files in the archives directory |
| `ds spool archives inspect ARCHIVE_NAME` | List entries inside a spool archive zip |

---

## Analytics & Diagnostics

| Command | Description |
|---------|-------------|
| `ds analytics-ingest --file PAYLOAD [--execute]` | Import normalized analytics facts into SQLite |
| `ds diagnostics list [--source SOURCE] [--category CATEGORY] [--limit N]` | Show recent diagnostic entries |
| `ds diagnostics clear [--source SOURCE]` | Truncate diagnostic log files |
| `ds analyze intake TARGET_PATH [--persistent]` | Register a brownfield repo for intake scanning |
| `ds analyze aggregate` | Run ML metrics aggregation |

---

## Context & Intelligence

| Command | Description |
|---------|-------------|
| `ds contract-atlas` | Show Contract Atlas summary |
| `ds contract-atlas-refresh [--execute] [--changed-file FILE]` | Plan or refresh Contract Atlas lifecycle exports |
| `ds context-packet [--adapter ADAPTER] [--packet-type TYPE] [--project-id ID]` | Preview a context packet |
| `ds policy [--actor ACTOR] [--action ACTION] [--target TARGET]` | Preview a policy decision |

---

## Behavioral Evals

| Command | Description |
|---------|-------------|
| `ds eval run [--all \| --eval-id ID \| --skill SKILL] [--evals-dir DIR]` | Run behavioral evals |
| `ds eval baseline` | Print current baseline scores |
| `ds eval compare [--eval-id ID]` | Compare recent run scores against baseline |
| `ds eval list [--skill SKILL] [--evals-dir DIR]` | List available eval cases |
