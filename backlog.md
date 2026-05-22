# Dream Studio — Backlog

## TA-series: Token Attribution Remediation (In Progress)

**Status:** TA0–TA4 complete — 3 workstreams remaining

### 10-Workstream Plan

| ID | Title | Status |
|----|-------|--------|
| TA0a | Audit findings baseline | Complete (pre-existing) |
| TA0b | Dual event store reconciliation | Complete — PR #37 |
| TA0 | SDLC entity creation events + backfill | Complete — PR #38 |
| TA0c | Retire activity_log, migrate to canonical events | Complete — PR #39 |
| TA1 | Task lifecycle events | Complete — PR #40 |
| TA2 | Active task context + skill SDLC trace | Complete — PR #41 |
| TA3 | Universal token capture (PostToolUse hook) | Complete — PR #42 |
| TA3b | Execution context (parent_invocation_id + stale-state audit) | Pending |
| **TA4** | **Remove hardcoded project_id + enforce attribution_status** | **Complete — this PR** |
| TA5 | Dashboard truth-up (remove synthesizer) | Pending |
| TA6 | End-to-end verification | Pending |

### TA0b Summary
- `canonical_events` is now the single authoritative event store
- `execution_events` is now a projection rebuilt by the ingestor from canonical events
- Domain field (`sdlc` | `telemetry` | `system`) added to all canonical event traces
- Migration 058: domain field requirement documented
- Migration 059: `_built_from_event_id` column added to execution_events for canonical linkage
- Migration 060: backfill — domain added to existing events, execution_events populated from canonical

### TA0 Summary
- `project.created`, `project.deleted`, `milestone.created`, `milestone.deleted`, `work_order.created` added to registry
- Forward emission from `register_project`, `delete_project`, `create_milestone`, `create_work_order`
- `work_order.started` and `work_order.closed` traces extended with `milestone_id` + `attribution_status`
- Migration 061: backfill — synthetic *.created events for 19 pre-TA0 rows (attribution_status: "backfill")
- `task.created` and `task.started` deferred to TA1

### TA1 Summary (this PR)
- `task.created`, `task.started` (no emitter — no in_progress call site), `task.deleted` added to registry
- Forward emission from `create_task()` and `add_tasks_from_file()` → `task.created`
- Forward emission from `delete_project()` cascade → `task.deleted` per deleted task
- `task.completed` trace enriched with `milestone_id` + `project_id` (resolved via JOIN with ds_work_orders)
- Migration 064: backfill — synthetic `task.created` events for all pre-TA1 task rows (attribution_status: "backfill")
- **Finding: `task.started` has no call site.** Tasks transition directly pending → complete; no in_progress state exists for tasks (only work orders). Type registered for TA2 active-task wiring but emitter_implemented=False.

### TA2 Summary (this PR)
- `core/sdlc/active_task.py` introduced: set/get/clear active task context at `~/.dream-studio/state/active_task.json` (env-overridable via DS_ACTIVE_TASK_PATH)
- Active task resolves full SDLC chain (task_id → work_order_id → milestone_id → project_id) at set time
- `skill.invoked` events now carry task_id, work_order_id, milestone_id, attribution_status ("fully_attributed" or "orphan")
- `task.completed` emitter auto-clears active_task.json when the completed task matches the active pointer
- CLI commands: `ds task set-active <task_id>`, `ds task active`, `ds task clear-active`
- DS_ACTIVE_TASK_PATH env var added to test guard fixture in tests/conftest.py
- Existing 21 skill.invoked events remain orphans permanently (active task was never set when they fired)

### TA3 Summary (this PR)
- `core/telemetry/token_capture.py` introduced: `handle_post_tool_use()` processes PostToolUse hook payloads
- Attribution chain: active_task → CWD `.dream-studio-project` marker → orphan
- `core/sdlc/cwd_resolver.py`: walks up from cwd, parses JSON (TA3+ format) or plain UUID (legacy) markers
- `core/telemetry/machine_id.py`: stable Dream Studio-managed UUID at `~/.dream-studio/state/machine_id`
- `core/telemetry/diagnostics.py`: two-tier JSONL diagnostic stream (failure / anomaly / performance)
- `runtime/hooks/core/on-post-tool-use.py`: thin shim; delegates to token_capture, exits 0 always
- `token.consumed` event type registered (domain: telemetry, emitter_implemented: True)
- `ds project register --path <dir>` now writes JSON `.dream-studio-project` marker at registration
- `ds diagnostics list/clear` CLI commands for diagnostic stream visibility
- Q3 decision: marker whose project_id is absent from ds_projects → attribution_status: "partial" + anomaly logged; auditor reconciles
- DS_MACHINE_ID_PATH and DS_DIAGNOSTICS_DIR env guards added to tests/conftest.py
- git context (commit, branch, remote) and platform context captured in execution_context payload
- No absolute filesystem paths in emitted events (registered_from_path is informational only, never emitted)
- Marker format authority: marker file for attribution resolution; ds_projects for project metadata; auditor reconciles drift
- **Deferred to TA3b:** parent_invocation_id linking tool call → skill/workflow/agent invocation; stale active_task state detection and audit

---

## Phantom SIGINT during pytest on Windows (RESOLVED)

Windows 11 + Python 3.12 + the ingest pipeline's rapid file moves and SQLite writes triggered phantom SIGINT delivery during pytest sessions. Investigation eliminated:

- All third-party pytest plugins (anyio, asyncio, aio, cov, faker)
- Pytest built-in plugins (cacheprovider, capture, faulthandler, terminalprogress)
- Python output buffering, colorama, ANSI escape handling
- Windows Defender, OneDrive sync, Logitech G HUB, GoXLR, Cowork
- WAL mode SQLite journal files (still occurred with DELETE mode)
- UCPD, CldFlt, gameflt filesystem filter drivers (detach test)
- Filesystem ACLs on TEMP (took ownership, recreated tree from scratch)
- SeCreateSymbolicLinkPrivilege (granted via Developer Mode + secpol.msc)
- Pytest's pytest-current and per-test symlink machinery

The signal source could not be fully isolated but was reproducibly bounded to calls through `ingest_pending` involving SQLite writes following file moves.

Resolution:

1. Module-level Windows console control handler in `spool/ingestor.py` using `SetConsoleCtrlHandler` via ctypes. Absorbs single phantom CTRL_C events while preserving real user Ctrl+C (two within 1 second forward to default handler). Production-facing.

2. SIGINT handler at the top of `tests/conftest.py` plus a `pytest_configure` hook that reinstalls our handler after pytest installs its own. Prevents pytest's SIGINT machinery from printing a KeyboardInterrupt banner after the test summary line.

Both fixes are Windows-only. Linux CI is unaffected. End users on Windows get the production handler automatically with no setup.

Future investigation if needed:
- Procmon trace during the actual SIGINT moment (not cleanup phase)
- Test on a fresh Windows machine to confirm machine-specific vs universal
- Try Python 3.11 or 3.13 to check for 3.12-specific regression

## Platform-aware infrastructure (NEW IN PR #36)

Dream Studio detects OS, shell, Python version, and terminal at install time. Profile persisted at `~/.dream-studio/state/platform.json`. Module: `core.config.platform`. Used to surface shell-correct command syntax in error messages and diagnostic output.

Future extension: include platform context in canonical events so token attribution and SDLC analytics can break down by environment.
