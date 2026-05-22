# Phase 0c — Final Depth Fill
*Audit date: 2026-05-22*
*Repo: C:\Users\Dannis Seay\builds\dream-studio-clean*
*Supplements: 00-mechanical-inventory.md (Phase 0 breadth) and 00b-mechanical-inventory-depth.md (Phase 0b depth)*
*This document fills 10 operator-identified gaps before Phase 1 analysis begins.*

---


---

## Gap 1: Hooks — Behavior Depth
*Addresses: each hook file in runtime/hooks/ with full behavioral documentation*
*Phase: 0c mechanical inventory — pure observation, no interpretation*
*Generated: 2026-05-22*

---

### Dispatch Layer Summary

Two installed entry-point files exist at `~/.claude/hooks/`:

**`~/.claude/hooks/run.py`** — Spool emitter. Handles four Claude Code hook events (UserPromptSubmit, Stop, PostToolUse, PostCompact). Primary responsibilities:

- Reads `argv[1]` for the hook event name and parses stdin as JSON payload.
- Resolves plugin root via `CLAUDE_PLUGIN_ROOT` env var, `.plugin-root` sidecar file, or path traversal fallback.
- Maps each event to a normalizer function in `emitters.claude_code.emitter` and calls `write_envelopes()` from `emitters.shared.spool_writer` — emits spooled event records to disk.
- On `UserPromptSubmit`: runs `_version_check()` (compares `VERSION` file against `~/.dream-studio/state/installed-version`) and `_enforcement_check()` (currently always returns None — fail-open, enforcement deferred to Slice 10). Prints a JSON `{"type": "message", "content": ...}` message if either check yields a notice.
- On `Stop`: calls `ingest_pending()` from `spool.ingestor` to flush spooled events into the DB; then calls `_cleanup_session_file()` to delete the PID-based session file from `$DS_SPOOL_ROOT/.sessions/`.
- Always exits 0.

**`~/.claude/hooks/dispatch/hooks.py`** — Tool-agnostic handler dispatcher. Primary responsibilities:

- Reads `argv[1]` for event name and stdin for JSON payload; extracts `toolName` from payload.
- Calls `_resolve_handlers(event_name, tool_name, plugin_root)` which returns a list of `(name, path)` tuples:
  - `UserPromptSubmit` → `[meta/on-prompt-dispatch]`
  - `Stop` → `[meta/on-stop-dispatch]`
  - `PostCompact` → `[meta/on-post-compact]`
  - `PostToolUse` (any tool) → `[meta/on-tool-activity]`, then:
    - `toolName == "Skill"` appends `[meta/on-skill-metrics, meta/on-skill-complete]`
    - `toolName in ("Edit", "Write", "MultiEdit")` appends `[meta/on-edit-dispatch]`
    - `toolName == "Read"` appends `[meta/on-skill-load]`
- Imports `control.execution.dispatch_tracking` and calls `run_handlers(handlers, raw_payload, event_name, state_dir)`.
- Always exits 0.

**Routing summary table:**

| Claude Code Event | toolName condition | Handlers invoked (in order) |
|---|---|---|
| UserPromptSubmit | (any) | on-prompt-dispatch → [on-prompt-validate, on-session-start, on-first-run, on-memory-retrieve, on-milestone-start, on-context-threshold, on-pulse] |
| Stop | (any) | on-stop-dispatch → [on-session-end, on-stop-handoff, on-quality-score, on-skill-telemetry, on-milestone-end, on-token-log, on-meta-review, on-workflow-progress, on-changelog-nudge] |
| PostCompact | (any) | on-post-compact |
| PostToolUse | Skill | on-tool-activity, on-skill-metrics, on-skill-complete |
| PostToolUse | Edit, Write, MultiEdit | on-tool-activity, on-edit-dispatch → [on-agent-correction, on-game-validate, on-security-scan, on-structure-check] |
| PostToolUse | Read | on-tool-activity, on-skill-load |
| PostToolUse | (other) | on-tool-activity only |

Note: `on-prompt-dispatch` and `on-edit-dispatch` are themselves sub-dispatchers that invoke further handlers. `on-stop-dispatch` iterates its handler list directly (not via `run_handlers`/`execute_handlers` — uses `load_module` + direct `mod.main()` calls with timing).

---

### Hook Files

---

#### runtime/hooks/meta/on-prompt-dispatch.py
- **Size:** 2,398 bytes | **Last modified:** 2026-05-19
- **Event:** UserPromptSubmit (via `dispatch/hooks.py` → `_resolve_handlers`)
- **Docstring:**
  ```
  Dispatcher: UserPromptSubmit — single process for all prompt-fired hooks.
  Replaces 6 subprocess invocations with one process that imports and calls
  each handler sequentially. Reads stdin once and re-injects it before each
  handler's main() so existing code works unchanged.
  Handlers (in order):
    1. on-session-start    (runtime/hooks/meta)
    2. on-first-run        (runtime/hooks/meta)
    3. on-memory-retrieve  (runtime/hooks/meta)
    4. on-milestone-start  (runtime/hooks/core)
    5. on-context-threshold (runtime/hooks/meta)
    6. on-pulse            (runtime/hooks/meta)
  ```
  Note: Actual HANDLERS list at runtime also includes `on-prompt-validate` as first entry (not reflected in the docstring comment).
- **Handler:** `main()`
- **Behavior:**
  - Reads all of stdin as `raw_payload`.
  - Calls `execute_handlers(HANDLERS, raw_payload, STATE_DIR)` from `control.execution.dispatch_tracking`.
  - HANDLERS list (7 entries): on-prompt-validate, on-session-start, on-first-run, on-memory-retrieve, on-milestone-start, on-context-threshold, on-pulse.
  - Each handler is executed sequentially in-process by `execute_handlers`.
  - STATE_DIR is `~/.dream-studio/state`.
- **Emits:** none observed directly — delegates to child handlers
- **DB reads:** none
- **DB writes:** none
- **Spool/diagnostic output:** none
- **External calls:** `subprocess` imported at module level (via `_get_plugin_root` traversal — not called in `main()`)
- **Live in canonical_events:** Cannot determine — this is a dispatcher; child handlers interact with DB

---

#### runtime/hooks/meta/on-stop-dispatch.py
- **Size:** 4,209 bytes | **Last modified:** 2026-05-19
- **Event:** Stop (via `dispatch/hooks.py` → `_resolve_handlers`)
- **Docstring:**
  ```
  Dispatcher: Stop — single process for all stop-fired hooks.
  ```
- **Handler:** `main()`
- **Behavior:**
  - Reads all of stdin as `raw_payload`.
  - Iterates HANDLERS list (9 entries): on-session-end, on-stop-handoff, on-quality-score, on-skill-telemetry, on-milestone-end, on-token-log, on-meta-review, on-workflow-progress, on-changelog-nudge.
  - For each handler: calls `load_module(name, path)` from `control.execution.dispatch_helpers`; if module has `main`, resets `sys.stdin` to `io.StringIO(raw_payload)`, calls `mod.main()`, records timing via `write_timing(STATE_DIR, "Stop", name, elapsed_ms)`.
  - After all handlers complete, calls `_dispatch_handoff_continuation()`.
  - `_dispatch_handoff_continuation()`: reads `~/.dream-studio/state/handoff-latest.json`; if the file exists, age < 120 seconds, and content is non-empty, reads `~/.dream-studio/state/pending-handoff.json` for flags and cwd; constructs a `claude <flags> "Continue from handoff: <content>"` command string; calls `_spawn_new_session(claude_cmd, cwd)` from `session_config`; then deletes both `handoff-latest.json` and `pending-handoff.json`.
- **Emits:** none observed directly — delegates to child handlers
- **DB reads:** none directly (child handlers read DB)
- **DB writes:** none directly (timing written via `write_timing` to state dir file)
- **Spool/diagnostic output:** `write_timing` writes to state dir (exact filename determined by `dispatch_helpers`)
- **External calls:** none directly — `_spawn_new_session` from `session_config` called conditionally
- **Live in canonical_events:** Cannot determine — this is a dispatcher

---

#### runtime/hooks/meta/on-edit-dispatch.py
- **Size:** 2,498 bytes | **Last modified:** 2026-05-19
- **Event:** PostToolUse (toolName in Edit, Write, MultiEdit) (via `dispatch/hooks.py`)
- **Docstring:**
  ```
  Dispatcher: PostToolUse Edit|Write — single process for all edit/write hooks.
  Replaces 4 subprocess invocations with one process that imports and calls
  each handler sequentially. Reads stdin once and re-injects it before each
  handler's main() so existing code works unchanged.
  Handlers (in order):
    1. on-agent-correction (runtime/hooks/quality)
    2. on-game-validate    (runtime/hooks/domains)
    3. on-security-scan    (runtime/hooks/quality)
    4. on-structure-check  (runtime/hooks/quality)
  ```
- **Handler:** `main()`
- **Behavior:**
  - Reads all of stdin as `raw_payload`, parses as JSON.
  - Extracts `tool_input.file_path` or `tool_input.path` from payload; normalizes backslashes to forward slashes.
  - Checks file_path against `PROTECTED_PATHS = ["settings.json", "settings.local.json", "CLAUDE.md"]`; exits 0 without running any handlers if any protected path string appears in file_path.
  - Calls `run_handlers(HANDLERS, raw_payload, "PostToolUse_Edit_Write", STATE_DIR)` with 4 handlers.
  - STATE_DIR is `~/.dream-studio/state`.
- **Emits:** none observed directly — delegates to child handlers
- **DB reads:** none
- **DB writes:** none
- **Spool/diagnostic output:** none
- **External calls:** `subprocess` present in `_get_plugin_root` resolution path (not called in `main()`)
- **Live in canonical_events:** Cannot determine — this is a dispatcher

---

#### runtime/hooks/meta/on-context-threshold.py
- **Size:** 5,444 bytes | **Last modified:** 2026-05-19
- **Event:** UserPromptSubmit (via on-prompt-dispatch, position 6 of 7)
- **Docstring:**
  ```
  Context threshold handler.
  At 75% normalized context usage: harvest session state, then spawn
  a fresh Claude Code session that inherits invocation flags.
  Never blocks execution.
  ```
- **Handler:** `main()`
- **Behavior:**
  - Reads stdin; extracts `session_id` and `context_window.used_percentage` from payload.
  - If no `session_id`, exits 0.
  - If `used_percentage` is missing, reads a bridge file at `$TMPDIR/claude-ctx-{session_id}.json` (max 120 seconds old) for `used_pct`/`raw_pct`.
  - Computes `normalized` percentage relative to `COMPACT_THRESHOLD` (83.0); if `normalized < HARVEST_THRESHOLD` (75.0), exits 0 without action.
  - Checks spawn lock file at `$TMPDIR/claude-spawn-lock-{session_id}.json`; if lock is less than 300 seconds old, exits 0 (prevents double-triggering).
  - Calls `_emit_harvest(session_id, normalized_pct, raw_pct)` which calls `spool.emitter.emit("ds_session_harvest", {...})`.
  - Writes spawn lock file at `$TMPDIR/claude-spawn-lock-{session_id}.json` with current timestamp.
  - Calls `read_session_config(session_id)` from `session_config` (or `runtime.session_config`); writes `~/.dream-studio/state/pending-handoff.json` with session_id, triggered_at, cwd, invocation_flags, status="pending".
  - Prints: `[Dream Studio] Context at 75% — preparing handoff for continuation session. Finish your current thought.`
- **Emits:** `ds_session_harvest` (via `spool.emitter.emit`)
- **DB reads:** none
- **DB writes:** none
- **Spool/diagnostic output:** `$TMPDIR/claude-spawn-lock-{session_id}.json` (spawn lock); `~/.dream-studio/state/pending-handoff.json` (handoff trigger); spool emit via `spool.emitter.emit` (indirect file write)
- **External calls:** none
- **Live in canonical_events:** NO — `ds_session_harvest` not found in canonical_events table. `context.threshold.crossed` has 19 rows (different event type name — emitted by a different path).

---

#### runtime/hooks/meta/on-prompt-validate.py
- **Size:** 3,475 bytes | **Last modified:** 2026-05-19
- **Event:** UserPromptSubmit (via on-prompt-dispatch, position 1 of 7 — first to run)
- **Docstring:**
  ```
  Prompt validation hook - validates user input for security risks.
  ```
- **Handler:** `main()`
- **Behavior:**
  - Reads stdin and parses as JSON payload.
  - Calls `_check_pending_handoff(payload)`: reads `~/.dream-studio/state/pending-handoff.json` if it exists; if file age < 60 seconds and status == "pending", updates status to "in_progress", prepends a hardcoded handoff instruction to `payload["prompt"]`, writes the modified payload to stdout via `sys.stdout.write(json.dumps(payload))`, and returns True. If True, exits 0 immediately.
  - If `rebuff_validator` import failed (`_VALIDATOR_AVAILABLE = False`), returns without scanning.
  - Extracts `payload["prompt"]`; if empty, returns.
  - Calls `validate_user_input(user_prompt, {"source": "user_prompt"})` from `guardrails.scanners.rebuff_validator`.
  - If `is_injection` is True and `risk_score >= 0.8`: prints a CRITICAL warning with up to 3 detected patterns and a recommendation.
  - If `is_injection` is True and `risk_score >= 0.6`: prints a WARNING with recommendation.
  - Does not block execution regardless of result.
- **Emits:** none
- **DB reads:** none
- **DB writes:** none
- **Spool/diagnostic output:** none; writes to stdout only (advisory messages and possibly modified prompt JSON)
- **External calls:** none
- **Live in canonical_events:** NO — no matching event type; `prompt.lifecycle.submitted` (249 rows) emitted via `run.py` spool path, not this hook.

---

#### runtime/hooks/meta/on-session-start.py
- **Size:** 2,583 bytes | **Last modified:** 2026-05-19
- **Event:** UserPromptSubmit (via on-prompt-dispatch, position 2 of 7)
- **Docstring:**
  ```
  Hook: on-session-start — record new session on first user prompt.
  ```
- **Handler:** `main()`
- **Behavior:**
  - Reads stdin; extracts `session_id` from payload, `CLAUDE_SESSION_ID` env var, or generates a new UUID as fallback.
  - Checks sentinel `session-started-{session_id}` via `has_sentinel()`; if present, returns immediately (idempotent — runs once per session).
  - Calls `upsert_project(project_id, cwd)` where `project_id = Path.cwd().name`.
  - Calls `insert_session(session_id, project_id)`.
  - Calls `set_sentinel("session-started-{session_id}", "session")`.
  - Calls `detect_invocation_flags()` and `write_session_config(session_id, {...})` from `session_config` module — writes a JSON file with session_id, flags, cwd, timestamp, continuation_count=0.
- **Emits:** none (no spool emit calls observed)
- **DB reads:** sentinel table (via `has_sentinel`)
- **DB writes:** ds_projects or projects table (via `upsert_project`); ds_sessions or sessions table (via `insert_session`); sentinels table (via `set_sentinel`)
- **Spool/diagnostic output:** session config JSON file (path determined by `session_config.write_session_config`)
- **External calls:** none
- **Live in canonical_events:** `system.session.recorded` has 51 rows — this hook is the likely source via `insert_session`.

---

#### runtime/hooks/meta/on-first-run.py
- **Size:** 2,334 bytes | **Last modified:** 2026-05-19
- **Event:** UserPromptSubmit (via on-prompt-dispatch, position 3 of 7)
- **Docstring:**
  ```
  Hook: on-first-run — welcome new users and prompt Director profile setup.
  ```
- **Handler:** `main()`
- **Behavior:**
  - Reads config via `state.read_config()`.
  - Calls `hydrate_registry_once()` from `core.utils.init_helpers` (idempotent via sentinel).
  - If `cfg.get("director_name")` is set: ensures `onboarding_mode` is set to "full" if missing, writes config, returns.
  - If `director_name` is not set: prints a multi-line welcome message instructing the user to close the session and run `workflow: run studio-onboard` in a new session.
- **Emits:** none
- **DB reads:** config file (via `state.read_config()`)
- **DB writes:** config file (via `state.write_config(cfg)`) — sets `onboarding_mode` to "full" if not set
- **Spool/diagnostic output:** none
- **External calls:** none
- **Live in canonical_events:** NO — no matching event type observed

---

#### runtime/hooks/meta/on-memory-retrieve.py
- **Size:** 2,101 bytes | **Last modified:** 2026-05-19
- **Event:** UserPromptSubmit (via on-prompt-dispatch, position 4 of 7)
- **Docstring:**
  ```
  Hook: on-memory-retrieve — inject relevant memories into context.
  ```
- **Handler:** `main(payload: dict)`
- **Behavior:**
  - Receives `payload` dict; extracts `payload["prompt"]` string.
  - If prompt is empty, returns.
  - Calls `paths.memory_dir()`; if directory does not exist, returns.
  - Calls `MemorySearch(mem_dir).refresh_if_stale().search(prompt, top_k=5)`.
  - Calls `debug("on-memory-retrieve", ...)` to log result count.
  - If no results, returns.
  - Writes `~/.dream-studio/state/memory-last-score.json` with `{"top_score": results[0]["score"]}`.
  - Prints an XML-formatted `<relevant-context>` block to stdout with up to 5 memory snippets (each wrapped in `<memory path="...">` tags).
- **Emits:** none
- **DB reads:** none (reads from memory_dir filesystem, not DB)
- **DB writes:** none
- **Spool/diagnostic output:** `~/.dream-studio/state/memory-last-score.json`
- **External calls:** none
- **Live in canonical_events:** NO — no matching event type observed

---

#### runtime/hooks/meta/on-pulse.py
- **Size:** 2,030 bytes | **Last modified:** 2026-05-19
- **Event:** UserPromptSubmit (via on-prompt-dispatch, position 7 of 7 — last to run)
- **Docstring:**
  ```
  Hook: on-pulse — proactive cross-project health check.
  ```
- **Handler:** `main()`
- **Behavior:**
  - Records start time and start timestamp via `utcnow()`.
  - Calls `run_pulse_check()` from `interfaces.cli.pulse_collector`.
  - In `finally` block (always executes): computes `duration_ms`, records completion timestamp.
  - Calls `insert_hook_execution(hook_name="on_pulse", hook_type="periodic", trigger_context={}, started_at, completed_at, duration_ms, exit_code, status, error_message)` from `core.event_store.studio_db`.
- **Emits:** none observed (no spool emit calls)
- **DB reads:** Cannot determine — delegated to `run_pulse_check()` internals
- **DB writes:** hook_executions table (via `insert_hook_execution`); additional writes by `run_pulse_check()` — cannot determine from this file alone
- **Spool/diagnostic output:** none
- **External calls:** none
- **Live in canonical_events:** `system.hook.execution.logged` has 45 rows — `insert_hook_execution` likely maps to this event type.

---

#### runtime/hooks/meta/on-skill-metrics.py
- **Size:** 2,337 bytes | **Last modified:** 2026-05-19
- **Event:** PostToolUse / toolName=Skill (via dispatch/hooks.py, position 1 of 2 after on-tool-activity)
- **Docstring:**
  ```
  Hook: on-skill-metrics — append skill usage record.
  ```
- **Handler:** `main()`
- **Behavior:**
  - Parses stdin as JSON payload.
  - Extracts `tool_input.skill` or `tool_input.name` (fallback "unknown") and `tool_input.args`.
  - Calls `build_display_name(skill_name, skill_args)` from `control.skills.metrics` to get `(display_name, mode)`.
  - Calls `get_model_for_skill(...)` from `control.execution.models.selector` to determine model string.
  - Calls `write_skill_usage(~/.dream-studio/state, display_name, mode, session_id, model)` — writes skill usage to state dir (exact file path determined by `metrics` module).
  - Calls `insert_token_usage(session_id, project_id, skill_name=display_name, input_tokens=0, output_tokens=0, model)` from `core.event_store.studio_db`.
- **Emits:** none observed directly
- **DB reads:** Cannot determine — delegated to `get_model_for_skill`
- **DB writes:** token_usage table or equivalent (via `insert_token_usage`)
- **Spool/diagnostic output:** skill usage file in `~/.dream-studio/state` (path determined by `write_skill_usage`)
- **External calls:** none
- **Live in canonical_events:** `skill.invoked` has 21 rows — `insert_token_usage` likely contributes; `token.consumed` has 7 rows.

---

#### runtime/hooks/meta/on-skill-complete.py
- **Size:** 2,794 bytes | **Last modified:** 2026-05-19
- **Event:** PostToolUse / toolName=Skill (via dispatch/hooks.py, position 2 of 2 after on-tool-activity and on-skill-metrics)
- **Docstring:**
  ```
  Hook: on-skill-complete — advisory chain-suggest after skill invocation.
  ```
- **Handler:** `main()`
- **Behavior:**
  - Reads stdin as `raw_input`.
  - Calls `skill_completion.parse_skill_payload(raw_input)` to extract `(skill_name, skill_args)`.
  - If no skill_name, returns.
  - Extracts `session_id` and sets `project_id = Path.cwd().name` from payload.
  - Calls `studio_db.log_skill_execution(skill_name, skill_args, status="success", model, session_id, project_id)` — TC-007 log entry.
  - Calls `record_outcome(skill_name, "unknown", "success", 0.0, 0)` from `control.skills.calibration`.
  - Resolves `skill_dir` via `skill_completion.locate_skill_dir(skill_name, skill_args, plugin_root)`.
  - If `skill_dir` exists: calls `skill_completion.process_chain_suggests(skill_name, skill_dir)` — prints chain suggestions to stdout.
- **Emits:** none (writes to DB and stdout)
- **DB reads:** Cannot determine — delegated to `record_outcome` and `log_skill_execution` internals
- **DB writes:** activity_log table (via `log_skill_execution`); calibration table (via `record_outcome`)
- **Spool/diagnostic output:** none
- **External calls:** none
- **Live in canonical_events:** `skill.invoked` has 21 rows.

---

#### runtime/hooks/meta/on-skill-load.py
- **Size:** 2,585 bytes | **Last modified:** 2026-05-19
- **Event:** PostToolUse / toolName=Read (via dispatch/hooks.py)
- **Docstring:**
  ```
  Hook: on-skill-load — log skill reads and resolve director_name.
  ```
- **Handler:** `main()`
- **Behavior:**
  - Reads stdin; parses as JSON; strips BOM.
  - Checks `payload["tool_name"] != "Read"`; returns if not a Read tool call.
  - Extracts `tool_input.file_path`; checks path against regex `skills[\\/].+\.md$`; returns if no match.
  - Returns if path matches `examples\.md$`.
  - Calls `extract_skill_name(file_path)` to get `skill_name`.
  - Prints: `[dream-studio] Skill loaded: {skill_name}` to stdout.
  - Appends a tab-separated line (`timestamp\tskill_name\tsession_id`) to `~/.dream-studio/meta/skill-usage.log`.
  - Reads `director_name` from config via `config_state.read_config()`.
  - Calls `resolve_director_placeholder(file_path, director)` from `control.skills.loader`; if a resolution is found, prints: `[dream-studio] {{director_name}} resolves to '{resolved}'.`
- **Emits:** none
- **DB reads:** config file (via `config_state.read_config()`)
- **DB writes:** none
- **Spool/diagnostic output:** `~/.dream-studio/meta/skill-usage.log` (append mode)
- **External calls:** none
- **Live in canonical_events:** NO — no matching event type observed

---

#### runtime/hooks/meta/on-skill-telemetry.py
- **Size:** 1,496 bytes | **Last modified:** 2026-05-19
- **Event:** Stop (via on-stop-dispatch, position 4 of 9)
- **Docstring:**
  ```
  Hook: on-skill-telemetry — capture skill telemetry at session end.
  ```
- **Handler:** `main()`
- **Behavior:**
  - Parses stdin as JSON payload; extracts `session_id`.
  - Calls `get_session_skills(state_dir / "skill-usage.jsonl", session_id)` from `core.telemetry.processor`.
  - If skills found: calls `write_telemetry(state_dir / "telemetry-buffer.jsonl", skills, detect_success(payload))`.
- **Emits:** none
- **DB reads:** none
- **DB writes:** none
- **Spool/diagnostic output:** reads `~/.dream-studio/state/skill-usage.jsonl`; writes `~/.dream-studio/state/telemetry-buffer.jsonl`
- **External calls:** none
- **Live in canonical_events:** NO — no matching event type observed

---

#### runtime/hooks/meta/on-tool-activity.py
- **Size:** 1,967 bytes | **Last modified:** 2026-05-19
- **Event:** PostToolUse (any toolName — always the first handler invoked for PostToolUse)
- **Docstring:**
  ```
  Hook: on-tool-activity — rolling snapshot of recent tool usage.
  Trigger: PostToolUse.
  Maintains activity feed at ~/.dream-studio/state/activity.json with recent tool calls.
  ```
- **Handler:** `main()`
- **Behavior:**
  - Reads stdin; strips BOM; parses as JSON payload.
  - Extracts `tool_name` and `tool_input` from payload.
  - Checks file path against `PROTECTED_PATHS = ["settings.json", "settings.local.json", "CLAUDE.md"]`; returns without action if match.
  - Calls `tool_tracking.maybe_harden_nudge(tool_name, tool_input)` — prints hardening advisory if applicable.
  - Calls `tool_tracking.maybe_security_suggest(tool_name, tool_input)` — prints security suggestion if applicable.
  - Calls `tool_tracking.update_activity_feed(tool_name, tool_input)` — updates `~/.dream-studio/state/activity.json`.
- **Emits:** none
- **DB reads:** none
- **DB writes:** none
- **Spool/diagnostic output:** `~/.dream-studio/state/activity.json` (via `update_activity_feed`)
- **External calls:** none
- **Live in canonical_events:** `hook.tool_activity` has 247 rows — this hook is the source.

---

#### runtime/hooks/meta/on-token-log.py
- **Size:** 2,348 bytes | **Last modified:** 2026-05-19
- **Event:** Stop (via on-stop-dispatch, position 6 of 9)
- **Docstring:**
  ```
  Hook: on-token-log — append session token usage to the token log.
  ```
- **Handler:** `main(payload: dict)`
- **Behavior:**
  - Receives parsed payload dict.
  - Extracts `session_name` (fallback to `session_id`), `timestamp`.
  - If `prompt_tokens` present in payload: reads `model`, `prompt_tokens`, `completion_tokens`, `total_tokens` directly.
  - Else: calls `extract_usage_from_transcript(payload.get("transcript_path", ""))` from `core.telemetry.token_logger`.
  - Calls `write_token_log(~/.dream-studio/meta/token-log.md, timestamp, session_name, model, prompt_t, completion_t, total_t, hook_output_bytes, hook_overhead_est)` — appends a row to the markdown log.
  - Prints a JSON status dict to stdout with session_name, model, total_tokens.
- **Emits:** none
- **DB reads:** none
- **DB writes:** none
- **Spool/diagnostic output:** `~/.dream-studio/meta/token-log.md` (append via `write_token_log`)
- **External calls:** none
- **Live in canonical_events:** `token.consumption.recorded` has 180 rows; `token.consumed` has 7 rows — separate spool path via `run.py`, not this hook directly.

---

#### runtime/hooks/meta/on-meta-review.py
- **Size:** 2,922 bytes | **Last modified:** 2026-05-19
- **Event:** Stop (via on-stop-dispatch, position 7 of 9)
- **Docstring:**
  ```
  Hook: on-meta-review — weekly retrospective across recent sessions.
  ```
- **Handler:** `main()`
- **Behavior:**
  - Constructs review file path: `~/.dream-studio/meta/review-{YYYY-MM-DD}.md`; if file already exists today, returns (runs at most once per day).
  - Calls `parse_token_log()` or `parse_session_context()[0]` to get sessions list.
  - If no sessions, returns.
  - Calls `generate_review(sessions, extra_themes)` and `draft_theme_lessons(themes, timestamp)` from `control.review.engine`.
  - If lessons were drafted, prints each drafted lesson name to stdout.
  - Calls `get_pending_drafts()` and appends pending draft list to review text.
  - Writes complete review to `~/.dream-studio/meta/review-{YYYY-MM-DD}.md`.
  - Calls `get_escalation_candidates(threshold=3)` from `core.learning.lesson_threshold`; for each candidate skill with 3+ draft lessons, prints an escalation warning to stdout.
  - Prints: `[dream-studio] Meta-review complete — N sessions → /path/to/review.md`
  - Prints a JSON status dict to stdout.
- **Emits:** none
- **DB reads:** none (reads from `~/.dream-studio/meta/token-log.md` via `parse_token_log`)
- **DB writes:** none (writes to `~/.dream-studio/meta/`)
- **Spool/diagnostic output:** `~/.dream-studio/meta/review-{YYYY-MM-DD}.md`; draft lesson files (paths determined by `draft_theme_lessons`)
- **External calls:** none
- **Live in canonical_events:** NO — no matching event type observed

---

#### runtime/hooks/meta/on-post-compact.py
- **Size:** 1,845 bytes | **Last modified:** 2026-05-19
- **Event:** PostCompact (via dispatch/hooks.py → `_resolve_handlers`)
- **Docstring:**
  ```
  Hook: on-post-compact — reset context tracking after /compact.
  ```
- **Handler:** `main()`
- **Behavior:**
  - Reads stdin; strips BOM; parses as JSON payload.
  - Extracts `session_id` and `cwd` from payload; resolves cwd via `paths.project_root()` if not in payload.
  - If `session_id` present: calls `reset_context_bridge(session_id)` from `core.utils.compact_utils` — resets the bridge file so context percentage displays as ~0%.
  - Calls `clear_sentinels(projects_dir(cwd), session_id)` — clears sentinel files so context threshold warnings will fire fresh as context grows.
  - Prints JSON `{"status": "ok", "hook": "on-post-compact", "reset": True}` to stdout.
- **Emits:** none
- **DB reads:** none
- **DB writes:** none (sentinel files in projects dir, not DB)
- **Spool/diagnostic output:** bridge file cleared (path determined by `reset_context_bridge`); sentinel files cleared (paths in `projects_dir(cwd)`)
- **External calls:** none
- **Live in canonical_events:** NO — no matching event type observed

---

#### runtime/hooks/meta/on-session-end.py
- **Size:** 1,924 bytes | **Last modified:** 2026-05-19
- **Event:** Stop (via on-stop-dispatch, position 1 of 9 — first to run)
- **Docstring:**
  ```
  Hook: on-session-end — close out the session row on Stop event.
  ```
- **Handler:** `main()`
- **Behavior:**
  - Parses stdin as JSON payload; extracts `session_id`; returns if not present.
  - Checks sentinel `session-ended-{session_id}` via `has_sentinel()`; returns if present (idempotent).
  - Extracts `input_tokens` and `output_tokens` from payload (only if `prompt_tokens` key is present).
  - Calls `end_session(session_id, input_tokens, output_tokens)` from `core.event_store.studio_db`.
  - Calls `validate_session_research(session_id)` from `control.session.manager`.
  - Calls `set_sentinel(sentinel_key, "session")`.
- **Emits:** none
- **DB reads:** sentinels table (via `has_sentinel`)
- **DB writes:** sessions table (via `end_session`); sentinels table (via `set_sentinel`)
- **Spool/diagnostic output:** none
- **External calls:** none
- **Live in canonical_events:** `system.session.closed` has 33 rows — `end_session` is the likely source.

---

#### runtime/hooks/core/on-milestone-start.py
- **Size:** 1,707 bytes | **Last modified:** 2026-05-19
- **Event:** UserPromptSubmit (via on-prompt-dispatch, position 5 of 7)
- **Docstring:**
  ```
  Hook: on-milestone-start — write a marker when a DCL command opens a milestone.
  Trigger: UserPromptSubmit matching a build/deploy DCL command.
  Purpose: Persist a milestone marker to `~/.dream-studio/state/milestone-active.txt`
  so `on-milestone-end` (and advisory hooks) can detect an in-flight milestone.
  ```
- **Handler:** `main()`
- **Behavior:**
  - Calls `milestone.read_user_message()` to extract the user prompt text from stdin.
  - If no message or `milestone.is_dcl_command(message)` returns False, returns without action.
  - If `milestone.marker_exists(paths.state_dir())` returns True: calls `milestone.print_already_active(message)` and returns.
  - If marker does not exist: calls `milestone.create_marker(message, paths.state_dir())`; on success calls `milestone.print_workflow_reminder(message)`; on failure prints `[on-milestone-start] failed to write marker`.
- **Emits:** none
- **DB reads:** none
- **DB writes:** none
- **Spool/diagnostic output:** `~/.dream-studio/state/milestone-active.txt` (written by `milestone.create_marker`)
- **External calls:** none
- **Live in canonical_events:** NO — no matching event type observed

---

#### runtime/hooks/core/on-milestone-end.py
- **Size:** 1,624 bytes | **Last modified:** 2026-05-19
- **Event:** Stop (via on-stop-dispatch, position 5 of 9)
- **Docstring:**
  ```
  Hook: on-milestone-end — emit checkpoint and clear the marker at turn end.
  Trigger: Stop.
  Purpose: If a milestone marker exists, record completion to the milestone log,
  print a checkpoint reminder, and clear the marker. If the milestone ran longer
  than DIFFICULTY_THRESHOLD_MINUTES, draft a retrospective lesson for review.
  ```
- **Handler:** `main()`
- **Behavior:**
  - Calls `milestone.load_and_clear_marker(paths.state_dir())` — reads and deletes `milestone-active.txt`; returns None if absent.
  - If no marker data, returns.
  - Calls `milestone.log_completion(marker_data, paths.meta_dir())` — appends to milestone log file.
  - Calls `milestone.print_checkpoint(marker_data)` — prints checkpoint reminder to stdout.
  - Calls `milestone.draft_lesson_if_long(marker_data, paths.meta_dir())` — if milestone duration exceeded threshold, drafts a retrospective lesson file.
- **Emits:** none
- **DB reads:** none
- **DB writes:** none
- **Spool/diagnostic output:** milestone log file in `~/.dream-studio/meta/`; lesson draft file in `~/.dream-studio/meta/` (conditional); `~/.dream-studio/state/milestone-active.txt` deleted
- **External calls:** none
- **Live in canonical_events:** NO — no matching event type observed

---

#### runtime/hooks/core/on-stop-handoff.py
- **Size:** 1,960 bytes | **Last modified:** 2026-05-19
- **Event:** Stop (via on-stop-dispatch, position 2 of 9)
- **Docstring:**
  ```
  Hook: on-stop-handoff — write a handoff + recap on natural session Stop.
  Trigger: Stop event.
  Only writes if there is actual git activity: working tree has changes OR a
  commit was made in the last 24 hours. Skips silently when the session was idle.
  Uses is_pct=False with kb=0 as a sentinel — the Stop event has no context %
  available. The handoff labels this as a "session end" (not a threshold trigger).
  Must complete in < 2 seconds.
  ```
- **Handler:** `main()`
- **Behavior:**
  - Calls `context_handoff.parse_stop_payload(sys.stdin.read(), paths.project_root())` to extract `(session_id, cwd)`.
  - Calls `context_handoff.has_session_activity(cwd)` — checks for git working tree changes or recent commits; returns without action if no activity.
  - Constructs sentinel key `handoff-done-{session_id or 'unknown'}`; checks `has_sentinel(key)`; returns if already done.
  - Calls `context_handoff.write_session_handoff(cwd, session_id)` — writes handoff document; returns path.
  - Calls `context_handoff.record_session_to_db(cwd, session_id, handoff_path)`.
  - Calls `set_sentinel(key, "handoff-done")`.
- **Emits:** none
- **DB reads:** sentinels table (via `has_sentinel`)
- **DB writes:** sentinels table (via `set_sentinel`); session handoff table (via `record_session_to_db`)
- **Spool/diagnostic output:** handoff document file (path determined by `write_session_handoff`)
- **External calls:** none (git operations performed inside `has_session_activity`)
- **Live in canonical_events:** `system.handoff.created` has 26 rows — `record_session_to_db` is the likely source.

---

#### runtime/hooks/core/on-post-tool-use.py
- **Size:** 2,316 bytes | **Last modified:** 2026-05-22
- **Event:** PostToolUse — this file is NOT in the dispatch routing chain; it appears to be an alternate/standalone shim not invoked via `dispatch/hooks.py`. Cannot determine from source alone whether it is registered in `settings.json` independently.
- **Docstring:**
  ```
  Hook shim: PostToolUse — token attribution capture.
  Thin shim. Reads stdin, delegates to core.telemetry.token_capture, exits 0.
  Last-resort failure logging if the module import or call fails.
  ```
- **Handler:** `main()`
- **Behavior:**
  - Reads all of stdin as `payload_raw`.
  - Parses as JSON payload.
  - Calls `handle_post_tool_use(payload)` from `core.telemetry.token_capture`.
  - On any exception: calls `_emergency_log(error, payload_raw)` — writes a JSONL entry to `~/.dream-studio/state/diagnostics/hook-failures.jsonl` (or `$DS_DIAGNOSTICS_DIR`), with ts, category="failure", source, error string, and truncated payload (first 500 chars).
  - Returns 0.
- **Emits:** none
- **DB reads:** Cannot determine — delegated to `handle_post_tool_use`
- **DB writes:** Cannot determine — delegated to `handle_post_tool_use`
- **Spool/diagnostic output:** `~/.dream-studio/state/diagnostics/hook-failures.jsonl` (error path only)
- **External calls:** none
- **Live in canonical_events:** `tool.execution.completed` has 822 rows — `handle_post_tool_use` is the likely source.

---

#### runtime/hooks/core/on-changelog-nudge.py
- **Size:** 1,673 bytes | **Last modified:** 2026-05-19
- **Event:** Stop (via on-stop-dispatch, position 9 of 9 — last to run)
- **Docstring:**
  ```
  Hook: on-changelog-nudge — remind to update CHANGELOG.md when source files changed.
  Trigger: Stop.
  Checks git status: if tracked source files are modified/added but CHANGELOG.md is
  not among them, prints a one-line advisory. Never blocks.
  ```
- **Handler:** `main()`
- **Behavior:**
  - Calls `changelog_helpers.find_project_root(paths.project_root())`.
  - Calls `changelog_helpers.get_git_status(root)` — runs git status to get list of changed files.
  - If no changed files, returns.
  - Calls `changelog_helpers.analyze_changes(status_lines)` — returns dict with `source_changed` and `changelog_changed` and `readme_changed` booleans.
  - If `source_changed` and not `changelog_changed`: calls `changelog_helpers.print_changelog_nudge()` — prints advisory to stdout.
  - If `readme_changed`: calls `changelog_helpers.check_and_nudge_readme_quality(root)`.
- **Emits:** none
- **DB reads:** none (the grep matched `UPDATE CHANGELOG` as a false positive from the docstring text "CHANGELOG.md is not among them" — no actual SQL UPDATE found in file)
- **DB writes:** none
- **Spool/diagnostic output:** none
- **External calls:** git (via `changelog_helpers.get_git_status` — uses subprocess or equivalent)
- **Live in canonical_events:** NO — no matching event type observed

---

#### runtime/hooks/core/on-workflow-progress.py
- **Size:** 1,554 bytes | **Last modified:** 2026-05-19
- **Event:** Stop (via on-stop-dispatch, position 8 of 9)
- **Docstring:**
  ```
  Hook: on-workflow-progress — read-only workflow status reporter.
  Trigger: Stop event.
  Reads ~/.dream-studio/state/workflows.json (written by Chief-of-Staff
  during workflow execution) and prints a summary if any workflow is active.
  This hook NEVER writes state — Chief-of-Staff owns the state file.
  ```
- **Handler:** `main()`
- **Behavior:**
  - Calls `workflow_tracking.load_active_workflows(paths.state_dir())` — reads `~/.dream-studio/state/workflows.json`.
  - If no active workflows, returns.
  - Iterates over workflows; calls `workflow_tracking.print_workflow_status(workflow_id, workflow_data)` for each — prints status summary to stdout.
- **Emits:** none
- **DB reads:** none
- **DB writes:** none
- **Spool/diagnostic output:** none (read-only; reads `~/.dream-studio/state/workflows.json` but does not write)
- **External calls:** none
- **Live in canonical_events:** `workflow.node.completed` has 25 rows; `workflow.completed` has 2 rows — these are written by Chief-of-Staff, not this hook.

---

#### runtime/hooks/domains/on-game-validate.py
- **Size:** 1,317 bytes | **Last modified:** 2026-05-19
- **Event:** PostToolUse (Edit, Write, MultiEdit) (via on-edit-dispatch, position 2 of 4)
- **Docstring:**
  ```
  Hook: on-game-validate — validate game project files on Edit|Write.
  ```
- **Handler:** `main()`
- **Behavior:**
  - Calls `pack_context.is_pack_active("domains")`; returns without action if domains pack is not active.
  - Reads stdin; strips BOM; parses as JSON payload.
  - Extracts file path from `CLAUDE_FILE_PATH` env var; falls back to `tool_input.file_path` from payload.
  - If no file path, returns.
  - Calls `game_validate_orchestrator.validate_and_format(Path(file_path_str))` from `runtime.lib.domains`.
  - If result is non-None: prints `result.output` to stdout.
  - If `result.should_block` is True: calls `sys.exit(2)` — this is the only hook in the chain that can produce a blocking exit code.
- **Emits:** none
- **DB reads:** Cannot determine — delegated to `pack_context.is_pack_active` and `validate_and_format`
- **DB writes:** none
- **Spool/diagnostic output:** none
- **External calls:** none
- **Live in canonical_events:** NO — no matching event type observed

---

#### runtime/hooks/quality/on-agent-correction.py
- **Size:** 1,033 bytes | **Last modified:** 2026-05-14
- **Event:** PostToolUse (Edit, Write, MultiEdit) (via on-edit-dispatch, position 1 of 4)
- **Docstring:**
  ```
  Hook: on-agent-correction — log director corrections and accumulate patterns.
  Trigger: PostToolUse on Edit|Write.
  When the director-corrections.md file is updated, parse the newest correction,
  append to corrections.log, and draft lessons when patterns repeat 3+ times.
  ```
- **Handler:** `main()`
- **Behavior:**
  - Reads file path from `CLAUDE_FILE_PATH` env var; returns if empty.
  - Calls `correction_patterns.is_corrections_file(file_path)` — returns if the written file is not the corrections file.
  - Calls `correction_patterns.extract_latest_correction(Path(file_path))` — parses newest entry from the corrections markdown file.
  - If no correction extracted, returns.
  - Calls `correction_patterns.print_logged_message(correction)` — prints acknowledgment to stdout.
  - Calls `correction_patterns.log_correction(correction, paths.meta_dir())` — appends to corrections.log in meta dir.
  - Calls `correction_patterns.check_and_draft_lesson(correction, paths.meta_dir())` — drafts a lesson file if the same correction pattern has appeared 3+ times.
- **Emits:** none
- **DB reads:** none
- **DB writes:** none
- **Spool/diagnostic output:** corrections.log in `~/.dream-studio/meta/`; lesson draft file in `~/.dream-studio/meta/` (conditional)
- **External calls:** none
- **Live in canonical_events:** NO — no matching event type observed

---

#### runtime/hooks/quality/on-quality-score.py
- **Size:** 1,202 bytes | **Last modified:** 2026-05-14
- **Event:** Stop (via on-stop-dispatch, position 3 of 9)
- **Docstring:**
  ```
  Hook: on-quality-score — advisory scoring after a milestone completes.
  Trigger: Stop (ordering matters in hooks.json — run before on-milestone-end).
  When a milestone marker exists, scan the git diff since the milestone
  started for: test coverage proxy, debug leftovers, potential secrets,
  large files, and scope. Prints a summary, appends a row to
  `~/.dream-studio/meta/quality-log.md`, and writes the overall score to
  `~/.dream-studio/meta/quality-score.json`. Never blocks — Director
  decides.
  ```
- **Handler:** `main()`
- **Behavior:**
  - Calls `quality_scoring.load_milestone_marker(paths.state_dir())` — reads `milestone-active.txt`; returns None if absent.
  - If no marker, returns without action.
  - Calls `quality_scoring.run_quality_checks(marker["started_at"], paths.project_root())` — runs checks against git diff since milestone started; returns `(results, score, label)`.
  - If no results, returns.
  - Calls `quality_scoring.print_report(marker["command"], results, score, label)` — prints advisory summary to stdout.
  - Calls `quality_scoring.save_outputs(marker["command"], results, score, label, paths.meta_dir())` — writes `~/.dream-studio/meta/quality-log.md` (append) and `~/.dream-studio/meta/quality-score.json`.
- **Emits:** none
- **DB reads:** none
- **DB writes:** none
- **Spool/diagnostic output:** `~/.dream-studio/meta/quality-log.md` (append); `~/.dream-studio/meta/quality-score.json`
- **External calls:** git diff (via `quality_scoring.run_quality_checks` — uses subprocess or equivalent)
- **Live in canonical_events:** NO — no matching event type observed

---

#### runtime/hooks/quality/on-security-scan.py
- **Size:** 1,006 bytes | **Last modified:** 2026-05-19
- **Event:** PostToolUse (Edit, Write, MultiEdit) (via on-edit-dispatch, position 3 of 4)
- **Docstring:**
  ```
  Hook: on-security-scan — lightweight security pattern check on Edit/Write.
  Trigger: PostToolUse (Edit|Write).
  Scans new content for high-signal security anti-patterns and prints a warning.
  Advisory only — never blocks.
  ```
- **Handler:** `main()`
- **Behavior:**
  - Reads stdin; strips BOM; parses as JSON payload.
  - Checks `tool_name` against ("Edit", "Write"); returns if not one of these.
  - Calls `security_patterns.extract_content(payload)` to get `(file_path, content)`.
  - If no content or `security_patterns.should_scan(file_path)` returns False, returns.
  - Calls `security_patterns.scan_for_patterns(content)` to get findings list.
  - If findings present: calls `security_patterns.print_warning(file_path, findings)` — prints advisory to stdout.
  - Never calls `sys.exit(2)` — advisory only.
- **Emits:** none
- **DB reads:** none
- **DB writes:** none
- **Spool/diagnostic output:** none
- **External calls:** none
- **Live in canonical_events:** NO — no matching event type observed

---

#### runtime/hooks/quality/on-structure-check.py
- **Size:** 1,116 bytes | **Last modified:** 2026-05-19
- **Event:** PostToolUse (Write only) (via on-edit-dispatch, position 4 of 4)
- **Docstring:**
  ```
  Hook: on-structure-check — nudge when source files are placed outside standard dirs.
  Trigger: PostToolUse (Write only — creating new files).
  Checks FSC conventions: .py/.ts/.js source files should live in src/, lib/, hooks/,
  app/, or tests/ — not scattered at the project root. Advisory only.
  ```
- **Handler:** `main()`
- **Behavior:**
  - Reads stdin; strips BOM; parses as JSON payload.
  - Checks `payload["tool_name"] != "Write"`; returns if not Write (Edit is excluded at this hook level).
  - Calls `structure_rules.extract_file_path(payload)` to get file path.
  - If no file path or `structure_rules.is_source_file(file_path)` returns False, returns.
  - Calls `structure_rules.check_structure_violation(file_path)` — checks if path falls outside standard directories.
  - If violation found: calls `structure_rules.emit_nudge_once(violation, file_path, paths.state_dir())` — prints advisory once per violation via sentinel mechanism.
- **Emits:** none
- **DB reads:** none
- **DB writes:** none (sentinel-based deduplication likely uses state dir files)
- **Spool/diagnostic output:** sentinel file in `~/.dream-studio/state/` (via `emit_nudge_once`)
- **External calls:** none
- **Live in canonical_events:** NO — no matching event type observed

---

### Canonical Events Cross-Reference Summary

| event_type | row count | Hook(s) responsible |
|---|---|---|
| tool.execution.completed | 822 | core/on-post-tool-use.py (via `handle_post_tool_use`) |
| prompt.lifecycle.submitted | 249 | run.py spool emitter (not a runtime/hooks file) |
| hook.tool_activity | 247 | meta/on-tool-activity.py (via `update_activity_feed`) |
| token.consumption.recorded | 180 | run.py spool emitter (not a runtime/hooks file) |
| event.validation.failed | 57 | Cannot determine from hook source files |
| system.session.recorded | 51 | meta/on-session-start.py (via `insert_session`) |
| system.hook.execution.logged | 45 | meta/on-pulse.py (via `insert_hook_execution`) |
| system.session.closed | 33 | meta/on-session-end.py (via `end_session`) |
| system.handoff.created | 26 | core/on-stop-handoff.py (via `record_session_to_db`) |
| workflow.node.completed | 25 | Chief-of-Staff (not a hook file) |
| skill.invoked | 21 | meta/on-skill-complete.py (via `log_skill_execution`) |
| context.threshold.crossed | 19 | Cannot determine — `ds_session_harvest` emitted by on-context-threshold.py but `context.threshold.crossed` is a different event name |
| work_order.started | 15 | CLI (not a hook file) |
| work_order.created | 14 | CLI (not a hook file) |
| task.created | 9 | CLI (not a hook file) |
| token.consumed | 7 | meta/on-skill-metrics.py (via `insert_token_usage`) |
| milestone.created | 4 | CLI (not a hook file) |
| task.completed | 4 | CLI (not a hook file) |
| work_order.closed | 4 | CLI (not a hook file) |
| gate.bypassed | 3 | CLI (not a hook file) |
| project.created | 3 | CLI (not a hook file) |
| workflow.completed | 2 | Chief-of-Staff (not a hook file) |

**Hook files with zero confirmed canonical_events rows:**
on-prompt-validate, on-first-run, on-memory-retrieve, on-context-threshold (emits `ds_session_harvest` — not found in DB), on-post-compact, on-skill-load, on-skill-telemetry, on-meta-review, on-token-log, on-changelog-nudge, on-workflow-progress, on-milestone-start, on-milestone-end, on-quality-score, on-security-scan, on-structure-check, on-agent-correction, on-game-validate.

**Hook files not in runtime/hooks/ that produce canonical_events rows:**
- `run.py` (spool emitter): produces `prompt.lifecycle.submitted`, `token.consumption.recorded`
- `emitters/` path: produces event records via `write_envelopes`

---

# Phase 0c — Gap 2 & Gap 3: CLI and API Handler→Table Mapping

**Audit date:** 2026-05-22
**Repo:** `C:\Users\Dannis Seay\builds\dream-studio-clean`
**Runtime DB:** `C:\Users\Dannis Seay\.dream-studio\state\studio.db`
**Methodology:** Static source read + import-time route enumeration. DB table names extracted via SQL-pattern grep across core/* and projections/api/routes/*. Event types extracted via CanonicalEventEnvelope grep.

---

## Gap 2: CLI Commands — Handler→Table Mapping

**Primary entrypoint:** `interfaces/cli/ds.py` (90 KB)
**Submodule entrypoints:**
- `interfaces/cli/ds_spool.py` — spool group
- `interfaces/cli/ds_workflow.py` — workflow group
- `interfaces/cli/ds_memory.py` — memory group
- All project/work-order/design-brief/milestone/task/diagnostics dispatch is inline in `ds.py`

---

### spool ingest

- **Handler:** `interfaces/cli/ds_spool.py:cmd_ingest()` → delegates to `spool.ingestor.ingest_pending()`
- **DB reads:** `canonical_events` (SELECT for deduplication before insert)
- **DB writes:** `canonical_events` (INSERT OR IGNORE)
- **Secondary writes (session harvester path):** `reg_gotchas`, `raw_approaches`, `ds_documents`, `ds_technology_signals`
- **Events emitted:** none (this is the consumer; it processes spool files and inserts into DB)
- **External calls:** reads `~/.dream-studio/events/pending/` filesystem; delegates to `projections.core.execution_events_projection.apply` on success
- **Implementation status:** IMPLEMENTED

---

### workflow start

- **Handler:** `interfaces/cli/ds_workflow.py:cmd_start()` → delegates to `control.execution.workflow.state.cmd_start()`
- **DB reads:** none directly (reads YAML file from filesystem)
- **DB writes:** none directly (writes `workflows.json` state file; archives to `studio_db.archive_workflow` on completion)
- **Events emitted:** none at start; `spool.writer.write_event` with `EventType` on node completion
- **External calls:** YAML file IO, `control/execution/workflow/` state machinery
- **Implementation status:** IMPLEMENTED

### workflow status

- **Handler:** `interfaces/cli/ds_workflow.py:cmd_status()` → delegates to `control.execution.workflow.state.cmd_status()`
- **DB reads:** none (reads `workflows.json`)
- **DB writes:** none
- **Events emitted:** none
- **External calls:** filesystem (workflows.json)
- **Implementation status:** IMPLEMENTED

### workflow list

- **Handler:** `interfaces/cli/ds_workflow.py:cmd_list()` → delegates to `control.execution.workflow.state.cmd_status(key=None)`
- **DB reads:** none
- **DB writes:** none
- **Events emitted:** none
- **External calls:** filesystem (workflows.json)
- **Implementation status:** IMPLEMENTED

### workflow advance

- **Handler:** `interfaces/cli/ds_workflow.py:cmd_advance()` → `control.execution.workflow.runner.WorkflowRunner.advance()`
- **DB reads:** none directly; runner reads `workflows.json`
- **DB writes:** none directly; writes `workflows.json`; may call `spool.writer.write_event`
- **Events emitted:** spool event via `spool.writer.write_event` with `EventType` on node execution
- **External calls:** may invoke skill invocation pipeline
- **Implementation status:** IMPLEMENTED

### workflow run

- **Handler:** `interfaces/cli/ds_workflow.py:cmd_run()`
  - Default path: `control.execution.workflow.runner.WorkflowRunner.run()`
  - `pre-push --non-interactive` path: `core.gates.pre_push.run_pre_push_gates()`
- **DB reads:** none directly (reads workflows.json); pre-push path reads source files
- **DB writes:** none directly; may write via spool
- **Events emitted:** spool events per wave via `spool.writer.write_event`
- **External calls:** subprocess skill execution, filesystem IO
- **Implementation status:** IMPLEMENTED

---

### memory ingest

- **Handler:** `interfaces/cli/ds_memory.py:cmd_memory_ingest()` → `run_memory_ingest()`
- **DB reads:** `reg_gotchas` (existence check), `ds_documents` (existence check), `reg_projects` (project_id lookup)
- **DB writes:** `reg_gotchas` (INSERT), `ds_documents` (INSERT — doc_type=architecture_decision, doc_type=session_handoff; DELETE+INSERT on upsert)
- **Events emitted:** none
- **External calls:** reads filesystem — `~/.sessions/`, `~/.planning/` tree (handoff-*.md, recap-*.md, GOTCHAS.md, ADR-*.md, ARCHITECTURE*.md)
- **Implementation status:** IMPLEMENTED

### memory ingest-sessions

- **Handler:** `interfaces/cli/ds_memory.py:cmd_memory_ingest_sessions()` → `spool.session_harvester.SessionHarvester`
- **DB reads:** `reg_gotchas` (existence check), `ds_documents` (existence check)
- **DB writes:** `reg_gotchas` (INSERT), `raw_approaches` (INSERT OR IGNORE), `ds_documents` (INSERT OR IGNORE), `ds_technology_signals` (INSERT / ON CONFLICT UPDATE)
- **Events emitted:** none
- **External calls:** reads `~/.claude/projects/` JSONL session files; interactive consent prompt unless `--no-consent-prompt`
- **Implementation status:** IMPLEMENTED

---

### project register

- **Handler:** `interfaces/cli/ds.py:_project_register()` → `core.projects.mutations.register_project()`
- **DB reads:** none (existence not checked before insert)
- **DB writes:** `ds_projects` (INSERT)
- **Events emitted:** `project.created` (CanonicalEventEnvelope → spool)
- **External calls:** writes `.dream-studio-project` marker file at project path
- **Implementation status:** IMPLEMENTED

### project list

- **Handler:** `interfaces/cli/ds.py:_project_list()` → `core.projects.queries.get_project_list()`
- **DB reads:** `ds_projects`
- **DB writes:** none
- **Events emitted:** none
- **External calls:** none
- **Implementation status:** IMPLEMENTED

### project status

- **Handler:** `interfaces/cli/ds.py:_project_status()` → `core.projects.queries.get_project_status()`
- **DB reads:** `ds_projects`, `ds_milestones` (COUNT), `ds_work_orders` (COUNT, open COUNT)
- **DB writes:** none
- **Events emitted:** none
- **External calls:** none
- **Implementation status:** IMPLEMENTED

### project next

- **Handler:** `interfaces/cli/ds.py:_project_next()` → `core.projects.queries.get_next_work_order()`
- **DB reads:** `ds_work_orders` (first open, ordered)
- **DB writes:** none
- **Events emitted:** none
- **External calls:** none
- **Implementation status:** IMPLEMENTED

### project set-active

- **Handler:** `interfaces/cli/ds.py:_project_set_active()` → `core.projects.mutations.set_active_project()`
- **DB reads:** `ds_projects` (existence check)
- **DB writes:** `ds_projects` (UPDATE status='paused' for old active, UPDATE status='active' for new)
- **Events emitted:** none
- **External calls:** none
- **Implementation status:** IMPLEMENTED

### project deactivate

- **Handler:** `interfaces/cli/ds.py:_project_deactivate()` → `core.projects.mutations.deactivate_project()`
- **DB reads:** `ds_projects` (existence check)
- **DB writes:** `ds_projects` (UPDATE status='paused')
- **Events emitted:** none
- **External calls:** none
- **Implementation status:** IMPLEMENTED

### project start

- **Handler:** `interfaces/cli/ds.py:_project_start()` → `core.projects.start.start_project()`
- **DB reads:** `ds_projects` (name lookup), `ds_work_orders` (next open), `ds_design_briefs` (brief check), `ds_milestones` (title), `ds_tasks` (task list), `reg_gotchas` (gotchas), `ds_work_order_types`
- **DB writes:** `ds_projects` (UPDATE status='active'), `ds_work_orders` (UPDATE status='in_progress')
- **Events emitted:** `work_order.started` (CanonicalEventEnvelope → spool)
- **External calls:** writes `context.md` to `.planning/` directory
- **Implementation status:** IMPLEMENTED

### project delete

- **Handler:** `interfaces/cli/ds.py:_project_delete()` → `core.projects.mutations.delete_project()`
- **DB reads:** `ds_projects` (existence), `ds_work_orders` (COUNT), `ds_milestones` (COUNT), `ds_tasks` (COUNT), `ds_tasks` (task list for event)
- **DB writes:** `ds_tasks` (DELETE), `ds_work_orders` (DELETE), `ds_milestones` (DELETE), `ds_design_briefs` (DELETE if table exists), `ds_projects` (DELETE)
- **Events emitted:** `project.deleted` (CanonicalEventEnvelope), `task.deleted` per task
- **External calls:** none
- **Implementation status:** IMPLEMENTED (requires `--confirm` flag for projects with dependents)

### project state

- **Handler:** `interfaces/cli/ds.py:_project_state()` → `core.projects.queries.get_project_state()`
- **DB reads:** `ds_projects` (active), `ds_work_orders` (next open + task counts), `ds_tasks` (counts), `ds_design_briefs` (brief status/fields), `reg_gotchas`
- **DB writes:** none
- **Events emitted:** none
- **External calls:** checks `.planning/` gate files on filesystem
- **Implementation status:** IMPLEMENTED

---

### integrate detect

- **Handler:** `interfaces/cli/ds.py:_integrate_dispatch()` branch `detect` → `integrations.detector.detect_all()`
- **DB reads:** none
- **DB writes:** none
- **Events emitted:** none
- **External calls:** filesystem scan for Claude Code / Codex config roots
- **Implementation status:** IMPLEMENTED

### integrate status

- **Handler:** `interfaces/cli/ds.py:_integrate_dispatch()` branch `status` → `integrations.health.doctor()` per tool
- **DB reads:** none directly
- **DB writes:** none
- **Events emitted:** none
- **External calls:** reads `~/.claude/` config files
- **Implementation status:** IMPLEMENTED

### integrate doctor

- **Handler:** `interfaces/cli/ds.py:_integrate_dispatch()` branch `doctor` → `integrations.health.doctor()`
- **DB reads:** none
- **DB writes:** none
- **Events emitted:** none
- **External calls:** reads config root files
- **Implementation status:** IMPLEMENTED

### integrate plan

- **Handler:** `interfaces/cli/ds.py:_integrate_dispatch()` branch `plan` → `ClaudeCodeInstaller.plan()`
- **DB reads:** none
- **DB writes:** none
- **Events emitted:** none
- **External calls:** reads `canonical/` source tree, reads existing config files (dry-run only)
- **Implementation status:** IMPLEMENTED

### integrate install

- **Handler:** `interfaces/cli/ds.py:_integrate_dispatch()` branch `install` → `ClaudeCodeInstaller.install(mode)`
- **DB reads:** none
- **DB writes:** none
- **Events emitted:** none
- **External calls:** writes files to `~/.claude/` (skills/, agents/, settings.json, CLAUDE.md); writes `.git/hooks/pre-push` if `--execute`
- **Implementation status:** IMPLEMENTED

---

### skill invoke

- **Handler:** `interfaces/cli/ds.py:_skill_invoke()` → `core.skills.invocation.load_skill_content()`, `core.skills.invocation.record_skill_invocation()`, `core.skills.invocation.seed_gate_artifact_files()`
- **DB reads:** `ds_work_orders` (project_id resolution), `ds_design_briefs` (brief_id check for website:discover)
- **DB writes:** `ds_design_briefs` (INSERT — create draft brief if none exists for website:discover)
- **Events emitted:** `skill.invoked` (CanonicalEventEnvelope → spool, best-effort)
- **External calls:** reads `canonical/skills/` SKILL.md file; writes gate artifact files (design-critique.md, security-scan.md) to `.planning/`; reads `.dream-studio-project` marker
- **Implementation status:** IMPLEMENTED

### skill list

- **Handler:** `interfaces/cli/ds.py:_skill_list()` → `core.skills.queries.list_skills()`
- **DB reads:** none (reads `canonical/skills/` filesystem, `packs.yaml`, per-mode `config.yml`)
- **DB writes:** none
- **Events emitted:** none
- **External calls:** reads `canonical/skills/` directory tree
- **Implementation status:** IMPLEMENTED

---

### work-order start

- **Handler:** `interfaces/cli/ds.py:_work_order_start()` → `core.work_orders.start.read_work_order_brief()` + `core.work_orders.start.start_work_order()`
- **DB reads:** `ds_work_orders`, `ds_work_order_types`, `ds_milestones`, `ds_projects`, `ds_tasks`, `ds_design_briefs`, `reg_gotchas`
- **DB writes:** `ds_work_orders` (UPDATE status='in_progress')
- **Events emitted:** `work_order.started` (CanonicalEventEnvelope → spool)
- **External calls:** writes `context.md` to `.planning/` directory; reads `.dream-studio-project` marker
- **Implementation status:** IMPLEMENTED

### work-order list

- **Handler:** `interfaces/cli/ds.py:_work_order_list()` → `core.work_orders.queries.list_work_orders()`
- **DB reads:** `ds_work_orders` (with optional project_id and status filters)
- **DB writes:** none
- **Events emitted:** none
- **External calls:** none
- **Implementation status:** IMPLEMENTED

### work-order close

- **Handler:** `interfaces/cli/ds.py:_work_order_close()` → `core.work_orders.close.close_work_order()`
- **DB reads:** `ds_work_orders`, `ds_work_order_types`, `ds_design_briefs` (gate check), `ds_documents` (gate check)
- **DB writes:** `ds_work_orders` (UPDATE status='complete')
- **Events emitted:** `work_order.closed` (CanonicalEventEnvelope → spool); `gate.bypassed` if `--force`
- **External calls:** checks `.planning/` gate artifact files on filesystem
- **Implementation status:** IMPLEMENTED

### work-order block

- **Handler:** `interfaces/cli/ds.py:_work_order_block()` → `core.work_orders.mutations.block_work_order()`
- **DB reads:** `ds_work_orders` (existence check)
- **DB writes:** `ds_work_orders` (UPDATE status='blocked', block_reason=...)
- **Events emitted:** `work_order.blocked` (CanonicalEventEnvelope → spool)
- **External calls:** none
- **Implementation status:** IMPLEMENTED

### work-order unblock

- **Handler:** `interfaces/cli/ds.py:_work_order_unblock()` → `core.work_orders.mutations.unblock_work_order()`
- **DB reads:** `ds_work_orders` (status check)
- **DB writes:** `ds_work_orders` (UPDATE status='in_progress', block_reason=NULL)
- **Events emitted:** none
- **External calls:** none
- **Implementation status:** IMPLEMENTED

### work-order task-done

- **Handler:** `interfaces/cli/ds.py:_work_order_task_done()` → `core.work_orders.mutations.mark_task_done()`
- **DB reads:** `ds_tasks` (task + work_order join, COUNT before/after)
- **DB writes:** `ds_tasks` (UPDATE status='complete')
- **Events emitted:** `task.completed` (CanonicalEventEnvelope → spool)
- **External calls:** updates `context.md` in `.planning/`; emits TodoWrite JSON to stdout if Claude Code environment detected; may call `core.sdlc.active_task.clear_active_task()`
- **Implementation status:** IMPLEMENTED

### work-order tasks

- **Handler:** `interfaces/cli/ds.py:_work_order_tasks()` → `core.work_orders.queries.list_tasks()`
- **DB reads:** `ds_work_orders` (existence check), `ds_tasks`
- **DB writes:** none
- **Events emitted:** none
- **External calls:** none
- **Implementation status:** IMPLEMENTED

### work-order add-tasks

- **Handler:** `interfaces/cli/ds.py:_work_order_add_tasks()` → `core.work_orders.mutations.add_tasks_from_file()`
- **DB reads:** `ds_work_orders` (existence check, milestone_id)
- **DB writes:** `ds_tasks` (INSERT per task)
- **Events emitted:** `task.created` per inserted task (CanonicalEventEnvelope → spool)
- **External calls:** reads tasks.md file from disk
- **Implementation status:** IMPLEMENTED

---

### design-brief show

- **Handler:** `interfaces/cli/ds.py:_design_brief_show()` → `core.design_briefs.queries.get_design_brief()`
- **DB reads:** `ds_design_briefs`
- **DB writes:** none
- **Events emitted:** none
- **External calls:** none
- **Implementation status:** IMPLEMENTED

### design-brief create

- **Handler:** `interfaces/cli/ds.py:_design_brief_create()` → `core.design_briefs.mutations.create_design_brief()`
- **DB reads:** none (no existence guard before insert)
- **DB writes:** `ds_design_briefs` (INSERT, status='draft')
- **Events emitted:** none
- **External calls:** none
- **Implementation status:** IMPLEMENTED

### design-brief lock

- **Handler:** `interfaces/cli/ds.py:_design_brief_lock()` → `core.design_briefs.mutations.lock_design_brief()`
- **DB reads:** `ds_design_briefs` (existence check)
- **DB writes:** `ds_design_briefs` (UPDATE status='locked')
- **Events emitted:** none
- **External calls:** none
- **Implementation status:** IMPLEMENTED

### design-brief update

- **Handler:** `interfaces/cli/ds.py:_design_brief_update()` → `core.design_briefs.mutations.update_design_brief_field()`
- **DB reads:** `ds_design_briefs` (status check — must be draft)
- **DB writes:** `ds_design_briefs` (UPDATE field=value)
- **Events emitted:** none
- **External calls:** none
- **Implementation status:** IMPLEMENTED (allowed fields: purpose, audience, tone, design_system, font_pairing, brand_tokens, raw_output)

### design-brief set-system

- **Handler:** `interfaces/cli/ds.py:_design_brief_set_system()` → `core.design_briefs.mutations.set_design_system()`
- **DB reads:** `ds_design_briefs` (status check)
- **DB writes:** `ds_design_briefs` (UPDATE design_system=system_name)
- **Events emitted:** none
- **External calls:** none
- **Implementation status:** IMPLEMENTED (allowed values: tech-minimal, editorial-modern, brutalist-bold, playful-rounded, executive-clean)

---

### milestone close

- **Handler:** `interfaces/cli/ds.py:_milestone_close()` → `core.milestones.close.close_milestone()`
- **DB reads:** `ds_milestones`, `ds_work_orders` (open work orders check)
- **DB writes:** `ds_milestones` (UPDATE status='complete')
- **Events emitted:** `milestone.completed` (CanonicalEventEnvelope → spool); `gate.bypassed` if `--force`
- **External calls:** checks `.planning/` gate files
- **Implementation status:** IMPLEMENTED

### milestone list

- **Handler:** `interfaces/cli/ds.py:_milestone_list()` → `core.milestones.queries.list_milestones()`
- **DB reads:** `ds_milestones`, `ds_work_orders` (COUNT per milestone)
- **DB writes:** none
- **Events emitted:** none
- **External calls:** none
- **Implementation status:** IMPLEMENTED

### milestone status

- **Handler:** `interfaces/cli/ds.py:_milestone_status()` → `core.milestones.queries.get_milestone_status()`
- **DB reads:** `ds_milestones`, `ds_work_orders`
- **DB writes:** none
- **Events emitted:** none
- **External calls:** checks `.planning/` gate files
- **Implementation status:** IMPLEMENTED

---

### task set-active

- **Handler:** `interfaces/cli/ds.py:_task_set_active()` → `core.sdlc.active_task.set_active_task()`
- **DB reads:** `ds_tasks` (JOIN `ds_work_orders`, `ds_milestones`, `ds_projects` to resolve full SDLC chain)
- **DB writes:** none (writes JSON to `~/.dream-studio/state/active_task.json`)
- **Events emitted:** none
- **External calls:** writes file to `~/.dream-studio/state/active_task.json`
- **Implementation status:** IMPLEMENTED

### task active

- **Handler:** `interfaces/cli/ds.py:_task_get_active()` → `core.sdlc.active_task.get_active_task()`
- **DB reads:** none (reads `~/.dream-studio/state/active_task.json`)
- **DB writes:** none
- **Events emitted:** none
- **External calls:** reads `active_task.json`
- **Implementation status:** IMPLEMENTED

### task clear-active

- **Handler:** `interfaces/cli/ds.py:_task_clear_active()` → `core.sdlc.active_task.clear_active_task()`
- **DB reads:** none
- **DB writes:** none (deletes `active_task.json`)
- **Events emitted:** none
- **External calls:** deletes `~/.dream-studio/state/active_task.json`
- **Implementation status:** IMPLEMENTED

---

### diagnostics list

- **Handler:** `interfaces/cli/ds.py:_diagnostics_dispatch()` branch `list` (inline, no core delegate)
- **DB reads:** none
- **DB writes:** none
- **Events emitted:** none
- **External calls:** reads `*.jsonl` files from `core.telemetry.diagnostics._diagnostics_dir()` (filesystem, not SQLite)
- **Implementation status:** IMPLEMENTED

### diagnostics clear

- **Handler:** `interfaces/cli/ds.py:_diagnostics_dispatch()` branch `clear` (inline, no core delegate)
- **DB reads:** none
- **DB writes:** none
- **Events emitted:** none
- **External calls:** truncates (write empty string) `*.jsonl` files in diagnostics dir
- **Implementation status:** IMPLEMENTED

---

### dashboard --status

- **Handler:** `interfaces/cli/ds.py:_dashboard_status()` (inline)
- **DB reads:** none (reads installed runtime model, checks sqlite_path.exists())
- **DB writes:** none
- **Events emitted:** none
- **External calls:** reads `~/.dream-studio/` path config
- **Implementation status:** IMPLEMENTED (returns static capability dict, does not start server)

### dashboard --serve

- **Handler:** `interfaces/cli/ds.py:_dashboard_serve()` (inline)
- **DB reads:** none
- **DB writes:** none
- **Events emitted:** none
- **External calls:** `subprocess.run([uvicorn, projections.api.main:app])` — starts the FastAPI server as foreground process
- **Implementation status:** IMPLEMENTED

### dashboard --open

- **Handler:** `interfaces/cli/ds.py:_dashboard_open()` (inline)
- **DB reads:** none
- **DB writes:** none
- **Events emitted:** none
- **External calls:** `subprocess.Popen([uvicorn ...])` (background); `webbrowser.open(url)`; polls port
- **Implementation status:** IMPLEMENTED

### dashboard --check

- **Handler:** `interfaces/cli/ds.py:_dashboard_check()` (inline)
- **DB reads:** none
- **DB writes:** none
- **Events emitted:** none
- **External calls:** HTTP GET probes to `/dashboard` and `/api/health`
- **Implementation status:** IMPLEMENTED

---

### Single-action top-level commands

The following commands have no sub-dispatch — each is handled inline in `ds.py:main()`.

| Command | Handler (module:function) | DB reads | DB writes | External calls | Status |
|---|---|---|---|---|---|
| `status` | `core.health.status.get_runtime_status()` | none direct | none | reads filesystem paths | IMPLEMENTED |
| `version` | `core.health.version.get_version()` | none | none | reads VERSION file | IMPLEMENTED |
| `doctor` | `core.health.doctor.run_doctor_checks()` | none | none | reads ~/.claude/, ~/.dream-studio/ | IMPLEMENTED |
| `repair` | inline `_repair_plan()` → calls `_doctor_status()` | none | none | same as doctor | IMPLEMENTED |
| `update` | `_update_command()` → `ClaudeCodeInstaller.install()` | none | none | writes ~/.claude/ files, updates installed-version | IMPLEMENTED |
| `validate` | `core.health.validate.run_validation()` | none | none | reads source tree | IMPLEMENTED |
| `contract-atlas` | `core.shared_intelligence.contract_atlas.build_contract_atlas(conn)` | reads multiple registry tables | none | reads source tree | IMPLEMENTED |
| `contract-atlas-refresh` | `core.shared_intelligence.contract_atlas_lifecycle.refresh_contract_atlas_exports(conn)` | reads registry tables | none | writes export files to --output-dir | IMPLEMENTED |
| `adapters` | `core.installed_runtime.adapter_router_status(conn)` | reads adapter tables via conn | none | none | IMPLEMENTED |
| `router` | same as `adapters` | same | none | none | IMPLEMENTED |
| `modules` | `core.module_profiles.module_profiles()` | none | none | reads source tree YAML | IMPLEMENTED |
| `platform-hardening` | `core.shared_intelligence.platform_hardening.platform_hardening_summary(conn)` | reads platform tables | none | none | IMPLEMENTED |
| `policy` | `core.shared_intelligence.platform_hardening.evaluate_policy_decision()` | none | none | none | IMPLEMENTED |
| `analytics-ingest` | `core.analytics_ingestion.ingest_analytics_payload(conn, payload)` | various analytics tables | analytics tables (INSERT/UPDATE) | reads JSON file | IMPLEMENTED |
| `install` | `core.installed_productization.first_run_setup()` or `detect_legacy_install()` | none | none | writes ~/.dream-studio/, ~/.claude/ | IMPLEMENTED |
| `install-command` | `core.installed_productization.install_global_command_surface()` | none | none | writes launcher scripts | IMPLEMENTED |
| `acceptance` | `core.installed_productization.productization_acceptance_report()` | none | none | reads rehearsal home | IMPLEMENTED |
| `backup` | `core.installed_productization.backup_runtime()` | none | none | copies ~/.dream-studio/ | IMPLEMENTED |
| `restore-check` | `core.installed_productization.restore_runtime_check()` | none | none | reads backup archive | IMPLEMENTED |
| `update-check` | `core.installed_productization.update_runtime_check()` | none | none | reads VERSION + installed-version | IMPLEMENTED |
| `uninstall-check` | `core.installed_productization.uninstall_runtime_check()` | none | none | scans install targets | IMPLEMENTED |
| `migrate-legacy` | `core.installed_productization.migrate_legacy_install()` | none | none | moves legacy files | IMPLEMENTED |
| `repair-adapters` | `core.installed_productization.repair_adapter_surfaces()` | none | none | writes adapter surface files | IMPLEMENTED |
| `rollback-check` | `core.installed_productization.rollback_runtime_check()` | none | none | reads backup path | IMPLEMENTED |
| `context-packet` | `core.shared_intelligence.context_packets.generate_shared_context_packet(conn)` | reads projects/work_orders/briefs | none (persist=False for CLI preview) | none | IMPLEMENTED |
| `rehearsal-install` | `core.installed_runtime.bootstrap_rehearsal_runtime()` | none | none | creates rehearsal dir tree | IMPLEMENTED |

---

## Gap 3: API Endpoints — Handler→Table Mapping

**Entrypoint:** `projections/api/main.py`
**Route enumeration source:** live import (`from projections.api.main import app`), confirmed 2026-05-22.
**Auth decorators:** none — no authentication middleware registered. All routes are open to localhost (CORS restricted to localhost origins only via `projections/api/safety.py:localhost_origins()`).
**Response models:** pydantic models defined in `projections/api/models/` and inline. Only selected routes use typed `response_model`; most return `dict` or `JSONResponse`.

---

### router: metrics (`/api/v1/metrics`) — `projections/api/routes/metrics.py`

Queries DB via `core.config.database.get_connection()` and delegated collectors in `projections/core/collectors/`.

#### GET /api/v1/metrics/

- **Handler:** `get_all_metrics()`
- **DB reads:** delegates to session/skill/token/model collector queries — `raw_sessions`, `hook_executions`, `canonical_events`
- **DB writes:** none
- **Response model:** dict (aggregated metrics)
- **Implementation status:** REAL_DATA

#### GET /api/v1/metrics/sessions

- **Handler:** `get_session_metrics()`
- **DB reads:** `raw_sessions`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/metrics/skills

- **Handler:** `get_skill_metrics()`
- **DB reads:** `hook_executions` (skill usage SQL via `projections/api/queries/token_attribution.py`)
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/metrics/tokens

- **Handler:** `get_token_metrics()`
- **DB reads:** `hook_executions` (token usage SQL), `raw_sessions`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/metrics/models

- **Handler:** `get_model_metrics()`
- **DB reads:** `hook_executions`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/metrics/lessons

- **Handler:** `get_lesson_metrics()`
- **DB reads:** delegated collector (likely `reg_gotchas` or lessons table)
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/metrics/workflows

- **Handler:** `get_workflow_metrics()`
- **DB reads:** `reg_workflows` (via collector)
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

---

### router: insights (`/api/v1/insights`) — `projections/api/routes/insights.py`

Uses `projections.core.collectors`, `projections.core.analyzers`, `projections.core.insights`.

#### GET /api/v1/insights/

- **Handler:** `get_all_insights()`
- **DB reads:** `raw_sessions` (via collectors)
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/insights/strengths

- **Handler:** `get_strengths()`
- **DB reads:** `raw_sessions` (via analyzers)
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/insights/issues

- **Handler:** `get_issues()`
- **DB reads:** `raw_sessions`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/insights/opportunities

- **Handler:** `get_opportunities()`
- **DB reads:** `raw_sessions`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/insights/risks

- **Handler:** `get_risks()`
- **DB reads:** `raw_sessions`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/insights/high-priority

- **Handler:** `get_high_priority()`
- **DB reads:** `raw_sessions`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/insights/recommendations

- **Handler:** `get_recommendations()`
- **DB reads:** `raw_sessions`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### POST /api/v1/insights/root-cause

- **Handler:** `analyze_root_cause()`
- **Request body:** JSON with analysis parameters
- **DB reads:** `raw_sessions`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/insights/rhythm

- **Handler:** `get_work_rhythm()`
- **DB reads:** `raw_sessions`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

---

### router: reports (`/api/v1/reports`) — `projections/api/routes/reports.py`

Uses `projections.core.reports.ReportGenerator`, `projections.core.insights.InsightEngine`.

#### POST /api/v1/reports/generate

- **Handler:** `generate_report()`
- **Request body:** report parameters
- **DB reads:** delegates to ReportGenerator (reads raw_sessions, hook_executions etc.)
- **DB writes:** none (generates report in-memory or temp storage)
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/reports

- **Handler:** `list_reports()`
- **DB reads:** none (reads filesystem report store or in-memory)
- **DB writes:** none
- **Response model:** dict list
- **Implementation status:** REAL_DATA

#### GET /api/v1/reports/{report_id}

- **Handler:** `get_report()`
- **DB reads:** none (reads report store)
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### DELETE /api/v1/reports/{report_id}

- **Handler:** `delete_report()`
- **DB reads:** none
- **DB writes:** none (deletes from report store)
- **Response model:** dict
- **Implementation status:** REAL_DATA

---

### router: exports (`/api/v1/export`) — `projections/api/routes/exports.py`

Large file (27 KB). Handles multi-format export (PDF, Excel, PPTX, CSV, PowerBI).

#### POST /api/v1/export/

- **Handler:** `create_export()`
- **Request body:** export spec
- **DB reads:** various (delegates to report engine)
- **DB writes:** none (writes export file)
- **Response model:** dict with export_id
- **Implementation status:** REAL_DATA

#### GET /api/v1/export/{export_id}

- **Handler:** `get_export_status()`
- **DB reads:** none (reads export job store)
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/export/{export_id}/download

- **Handler:** `download_export()`
- **DB reads:** none
- **DB writes:** none
- **Response model:** FileResponse
- **Implementation status:** REAL_DATA

#### DELETE /api/v1/export/{export_id}

- **Handler:** `delete_export()`
- **DB reads:** none
- **DB writes:** none (deletes export file)
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/export/pdf/{report_id}

- **Handler:** `export_pdf()`
- **DB reads:** delegates to report engine
- **DB writes:** none
- **Response model:** FileResponse or dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/export/excel/{report_id}

- **Handler:** `export_excel()`
- **DB reads:** delegates to report engine
- **DB writes:** none
- **Response model:** FileResponse or dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/export/pptx/{report_id}

- **Handler:** `export_pptx()`
- **DB reads:** delegates to report engine
- **DB writes:** none
- **Response model:** FileResponse or dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/export/csv

- **Handler:** `export_csv()`
- **DB reads:** `raw_sessions`, `hook_executions` (via collectors)
- **DB writes:** none
- **Response model:** StreamingResponse (CSV)
- **Implementation status:** REAL_DATA

#### GET /api/v1/export/powerbi

- **Handler:** `export_powerbi()`
- **DB reads:** `raw_sessions`, `hook_executions`, `canonical_events` (via collectors)
- **DB writes:** none
- **Response model:** dict (Power BI compatible JSON)
- **Implementation status:** REAL_DATA

---

### router: schedules (`/api/v1/schedules`) — `projections/api/routes/schedules.py`

Uses `projections.core.scheduler.ReportScheduler` and `ScheduleStorage`.

#### GET /api/v1/schedules

- **Handler:** `list_schedules()`
- **DB reads:** none (schedule storage is file/memory backed per ScheduleStorage)
- **DB writes:** none
- **Response model:** list of schedule dicts
- **Implementation status:** REAL_DATA

#### POST /api/v1/schedules

- **Handler:** `create_schedule()`
- **Request body:** schedule definition
- **DB reads:** none
- **DB writes:** none (writes to schedule store)
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### PUT /api/v1/schedules/{job_id}

- **Handler:** `update_schedule()`
- **DB reads:** none
- **DB writes:** none (updates schedule store)
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### DELETE /api/v1/schedules/{job_id}

- **Handler:** `delete_schedule()`
- **DB reads:** none
- **DB writes:** none (deletes from scheduler + storage)
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### POST /api/v1/schedules/{job_id}/pause

- **Handler:** `pause_schedule()`
- **DB reads:** none
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### POST /api/v1/schedules/{job_id}/resume

- **Handler:** `resume_schedule()`
- **DB reads:** none
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

---

### router: realtime (`/api/v1`) — `projections/api/routes/realtime.py`

#### GET /api/v1/connection-stats

- **Handler:** `get_connection_stats()`
- **DB reads:** none (reads WebSocket connection manager state)
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### POST /api/v1/broadcast/hook-execution

- **Handler:** `broadcast_hook_execution()`
- **Request body:** hook execution payload
- **DB reads:** none
- **DB writes:** none
- **Response model:** dict
- **External calls:** WebSocket broadcast
- **Implementation status:** REAL_DATA

---

### router: alerts (`/api/v1/alerts`) — `projections/api/routes/alerts.py`

Uses `core.config.database.get_connection()` directly; `projections.core.alerts.rule_manager.RuleManager`, `projections.core.sla.tracker.SLATracker`.

#### GET /api/v1/alerts/rules

- **Handler:** `list_rules()`
- **DB reads:** `alert_rules`
- **DB writes:** none
- **Response model:** list of rule dicts
- **Implementation status:** REAL_DATA

#### POST /api/v1/alerts/rules

- **Handler:** `create_rule()`
- **Request body:** rule definition
- **DB reads:** none
- **DB writes:** `alert_rules` (INSERT via RuleManager)
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### PUT /api/v1/alerts/rules/{rule_id}

- **Handler:** `update_rule()`
- **Request body:** updated rule fields
- **DB reads:** `alert_rules`
- **DB writes:** `alert_rules` (UPDATE via RuleManager)
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### DELETE /api/v1/alerts/rules/{rule_id}

- **Handler:** `delete_rule()`
- **DB reads:** none
- **DB writes:** `alert_rules` (DELETE via RuleManager)
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/alerts/history

- **Handler:** `get_alert_history()`
- **DB reads:** `alert_history`
- **DB writes:** none
- **Response model:** list of alert dicts
- **Implementation status:** REAL_DATA

#### GET /api/v1/alerts/sla

- **Handler:** `get_sla_metrics()`
- **DB reads:** `alert_history` (via SLATracker)
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/alerts/analytics

- **Handler:** `get_alert_analytics()`
- **DB reads:** `alert_history`, `alert_rules`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

---

### router: ml (`/api/v1/ml`) — `projections/api/routes/ml.py`

Note: routes mount with doubled path prefix (`/api/v1/ml/api/v1/ml/...`) — this is a router prefix bug.

#### GET /api/v1/ml/api/v1/ml/recommendations

- **Handler:** `get_recommendations()`
- **DB reads:** none (in-memory statistical model or empty)
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** STUBBED (ml.py is 4 KB; purely computed, no real ML model)

#### GET /api/v1/ml/api/v1/ml/forecast/tokens

- **Handler:** `forecast_tokens()`
- **DB reads:** none / `raw_sessions`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** STUBBED

#### GET /api/v1/ml/api/v1/ml/forecast/sessions

- **Handler:** `forecast_sessions()`
- **DB reads:** `raw_sessions`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** STUBBED

#### GET /api/v1/ml/api/v1/ml/patterns

- **Handler:** `detect_patterns()`
- **DB reads:** `raw_sessions`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** STUBBED

#### GET /api/v1/ml/api/v1/ml/clustering

- **Handler:** `cluster_behaviors()`
- **DB reads:** `raw_sessions`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** STUBBED

#### GET /api/v1/ml/api/v1/ml/benchmarks

- **Handler:** `get_benchmarks()`
- **DB reads:** none
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** STUBBED

#### GET /api/v1/ml/api/v1/ml/evaluation

- **Handler:** `evaluate_models()`
- **DB reads:** none
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** STUBBED

#### GET /api/v1/ml/api/v1/ml/status

- **Handler:** `ml_status()`
- **DB reads:** none
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** STUBBED

---

### router: analytics (`/api/v1/analytics`) — `projections/api/routes/analytics.py`

#### GET /api/v1/analytics/anomalies

- **Handler:** `get_anomalies()`
- **DB reads:** `raw_sessions`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/analytics/trends

- **Handler:** `get_trends()`
- **DB reads:** `raw_sessions`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/analytics/performance

- **Handler:** `get_performance()`
- **DB reads:** `raw_sessions`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

---

### router: project_intelligence (`/api/v1/projects`) — `projections/api/routes/project_intelligence.py`

Large file (109 KB). Uses `core.config.database.get_connection()`.

#### GET /api/v1/projects

- **Handler:** `list_projects()`
- **DB reads:** `reg_projects`, `prd_documents`, `pi_dependencies`, `security_findings`, `dashboard_attention_items`, `validation_results`, `execution_events`, `route_decision_records`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/projects/{project_id}/health

- **Handler:** `get_project_health()`
- **DB reads:** `reg_projects`, `validation_results`, `dashboard_attention_items`, `pi_components`, `security_findings`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/projects/{project_id}/details

- **Handler:** `get_project_details()`
- **DB reads:** `reg_projects`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/projects/{project_id}/history

- **Handler:** `get_project_history()`
- **DB reads:** `pi_analysis_runs`, `pi_violations`, `pi_bugs`, `pi_improvements`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/projects/analysis-runs/{run_id}

- **Handler:** `get_analysis_run()`
- **DB reads:** `pi_analysis_runs`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/projects/{project_id}/prds

- **Handler:** `get_project_prds()`
- **DB reads:** `prd_documents`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/projects/{project_id}/security

- **Handler:** `get_project_security()`
- **DB reads:** `security_findings`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/projects/{project_id}/activity

- **Handler:** `get_project_activity()`
- **DB reads:** `execution_events`, `route_decision_records`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/projects/{project_id}/dependencies

- **Handler:** `get_project_dependencies()`
- **DB reads:** `pi_components`, `pi_dependencies`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

---

### router: prd (`/api/prd`) — `projections/api/routes/prd.py`

Uses `core.event_store.studio_db`.

#### GET /api/prd/list

- **Handler:** `list_prds()`
- **DB reads:** `prd_documents`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/prd/{prd_id}

- **Handler:** `get_prd()`
- **DB reads:** `prd_documents`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/prd/{prd_id}/waves/ready

- **Handler:** `get_prd_ready_waves()`
- **DB reads:** `prd_documents` (and wave-related tables)
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/prd/{prd_id}/progress

- **Handler:** `get_prd_progress()`
- **DB reads:** `prd_documents`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/prd/{prd_id}/handoffs

- **Handler:** `get_prd_handoffs()`
- **DB reads:** `prd_handoffs`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

---

### router: discovery_internal (`/api/discovery/internal`) — `projections/api/routes/discovery_internal.py`

Uses `core.graph` and `core.config.database.get_connection()`.

#### GET /api/discovery/internal/graph/{project_id}

- **Handler:** `get_dependency_graph()`
- **DB reads:** `reg_projects`, `pi_components`, graph edges
- **DB writes:** none
- **Response model:** dict (nodes + edges)
- **Implementation status:** REAL_DATA

#### GET /api/discovery/internal/impact/{component_id}

- **Handler:** `analyze_component_impact()`
- **DB reads:** `pi_components`, graph edges
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/discovery/internal/components/{project_id}

- **Handler:** `list_components()`
- **DB reads:** `pi_components`
- **DB writes:** none
- **Response model:** list of component dicts
- **Implementation status:** REAL_DATA

#### GET /api/discovery/internal/stats/{project_id}

- **Handler:** `get_project_stats()`
- **DB reads:** `reg_projects`, `pi_components`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/discovery/internal/cycles/{project_id}

- **Handler:** `detect_cycles()`
- **DB reads:** `pi_components`, graph edges
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/discovery/internal/communities/{project_id}

- **Handler:** `detect_communities()`
- **DB reads:** `pi_components`, graph edges
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

---

### router: discovery_external — `projections/api/routes/discovery_external.py`

No DB prefix in main.py (tags only), routes at `/api/discovery/external/`.

#### POST /api/discovery/external/tools

- **Handler:** `search_external_tools()`
- **Request body:** search query
- **DB reads:** none (external tool registry or static catalog)
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/discovery/external/tools/{tool_id}

- **Handler:** `get_tool_details()`
- **DB reads:** none
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/discovery/external/health

- **Handler:** `health_check()`
- **DB reads:** none
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

---

### router: discovery_research — `projections/api/routes/discovery_research.py`

Uses `core.event_store.studio_db._connect`. Research cache backed by `research_cache` table.

#### POST /api/discovery/research

- **Handler:** `trigger_research()`
- **Request body:** topic/query
- **DB reads:** `research_cache` (topic lookup)
- **DB writes:** `research_cache` (INSERT on cache miss)
- **External calls:** `control.research.web` — live web research
- **Response model:** ResearchReport
- **Implementation status:** REAL_DATA

#### GET /api/discovery/research/{cache_id}

- **Handler:** `get_cached_research_by_id()`
- **DB reads:** `research_cache`
- **DB writes:** none
- **Response model:** ResearchReport
- **Implementation status:** REAL_DATA

#### GET /api/discovery/research

- **Handler:** `get_cached_research_by_topic()`
- **DB reads:** `research_cache`
- **DB writes:** none
- **Response model:** ResearchReport or 404
- **Implementation status:** REAL_DATA

#### DELETE /api/discovery/research/{cache_id}

- **Handler:** `invalidate_cached_research()`
- **DB reads:** none
- **DB writes:** `research_cache` (DELETE)
- **Response model:** dict
- **Implementation status:** REAL_DATA

---

### router: hooks (`/api/v1/hooks`) — `projections/api/routes/hooks.py`

Uses `core.config.database.get_connection()` directly. Reads hook telemetry tables.

#### GET /api/v1/hooks/executions

- **Handler:** `list_hook_executions()`
- **DB reads:** `hook_executions` (with optional column guards via `sqlite_schema.has_columns`)
- **DB writes:** none
- **Response model:** dict (list + count)
- **Implementation status:** REAL_DATA

#### GET /api/v1/hooks/executions/{exec_id}

- **Handler:** `get_hook_execution_details()`
- **DB reads:** `hook_executions`, `hook_findings`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/hooks/findings

- **Handler:** `list_hook_findings()`
- **DB reads:** `hook_findings`
- **DB writes:** none
- **Response model:** dict (list + count)
- **Implementation status:** REAL_DATA

#### GET /api/v1/hooks/performance

- **Handler:** `get_hook_performance()`
- **DB reads:** `hook_executions` (aggregated timing), falls back to `hook_invocations`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/hooks/stats

- **Handler:** `get_hook_stats()`
- **DB reads:** `hook_executions`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/hooks/anomalies

- **Handler:** `list_hook_anomalies()`
- **DB reads:** `hook_findings`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

---

### router: security (`/api/v1/security`) — `projections/api/routes/security.py`

Uses `core.config.database.get_connection()`. Reads security finding tables.

#### GET /api/v1/security/findings

- **Handler:** `list_all_findings()`
- **DB reads:** `security_findings`, `vw_security_summary` (optional view)
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/security/sarif

- **Handler:** `list_sarif_findings()`
- **DB reads:** `sec_sarif_findings`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/security/cve

- **Handler:** `list_cve_matches()`
- **DB reads:** `sec_cve_matches`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/security/reviews

- **Handler:** `list_manual_reviews()`
- **DB reads:** `sec_manual_reviews`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/security/stats

- **Handler:** `get_security_stats()`
- **DB reads:** `security_findings`, `sec_sarif_findings`, `sec_cve_matches`, `sec_manual_reviews`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### POST /api/v1/security/sarif/import

- **Handler:** `import_sarif_file()`
- **Request body:** UploadFile (SARIF JSON)
- **DB reads:** none
- **DB writes:** `sec_sarif_findings` (INSERT — marked TODO in code; parse_sarif_file() stub not yet wired)
- **External calls:** file upload / parsing
- **Implementation status:** STUBBED (parser integration noted as TODO in source)

---

### router: audits (`/api/v1/audits`) — `projections/api/routes/audits.py`

Uses `core.config.database.get_connection()` and `core.config.database.transaction()`.

#### GET /api/v1/audits/runs

- **Handler:** `list_audit_runs()`
- **DB reads:** `audit_runs`
- **DB writes:** none
- **Response model:** dict (list)
- **Implementation status:** REAL_DATA

#### GET /api/v1/audits/runs/{audit_id}

- **Handler:** `get_audit_run_details()`
- **DB reads:** `audit_runs`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### POST /api/v1/audits/runs

- **Handler:** `create_audit_run()`
- **Request body:** audit run parameters
- **DB reads:** none
- **DB writes:** `audit_runs` (INSERT)
- **Response model:** dict with audit_id
- **Implementation status:** REAL_DATA

#### GET /api/v1/audits/stats

- **Handler:** `get_audit_stats()`
- **DB reads:** `audit_runs`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/audits/findings/{audit_id}

- **Handler:** `get_audit_findings()`
- **DB reads:** `audit_runs`, optionally `sec_sarif_findings`
- **DB writes:** none
- **Response model:** dict (finding list)
- **Implementation status:** REAL_DATA

---

### router: intelligence (`/api/v1/intelligence`) — `projections/api/routes/intelligence.py`

Uses `core.config.database.get_connection()`. Reads canonical_events, hook_executions, decision_log.

#### GET /api/v1/intelligence/overview

- **Handler:** `get_overview()`
- **DB reads:** `hook_executions`, `canonical_events`, `decision_log`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/intelligence/token-intelligence

- **Handler:** `get_token_intelligence()`
- **DB reads:** `hook_executions`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/intelligence/agent-capabilities

- **Handler:** `get_agent_capabilities()`
- **DB reads:** `hook_executions`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/intelligence/architecture

- **Handler:** `get_architecture_intelligence()`
- **DB reads:** `canonical_events`, `hook_executions`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/v1/intelligence/system-controls

- **Handler:** `get_system_controls_intelligence()`
- **DB reads:** `decision_log`, `hook_executions`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

---

### router: telemetry (`/api/telemetry`) — `projections/api/routes/telemetry.py`

Uses `core.telemetry.read_models` and `core.config.database.get_db_path()`.

#### GET /api/telemetry/summary

- **Handler:** `get_telemetry_summary()`
- **DB reads:** via `core.telemetry.read_models` — `ds_projects`, `ds_milestones`, `ds_work_orders`, `ds_tasks`, `ds_technology_signals`, `canonical_events`, `reg_gotchas`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/telemetry/projects

- **Handler:** `list_telemetry_projects()`
- **DB reads:** `ds_projects` (via read_models)
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/telemetry/projects/{project_id}

- **Handler:** `get_project_telemetry()`
- **DB reads:** `ds_projects`, `ds_milestones`, `ds_work_orders`, `ds_tasks`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/telemetry/milestones/{milestone_id}

- **Handler:** `get_milestone_telemetry()`
- **DB reads:** `ds_milestones`, `ds_work_orders`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/telemetry/tasks/{task_id}

- **Handler:** `get_task_telemetry()`
- **DB reads:** `ds_tasks`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/telemetry/process-runs/{process_run_id}

- **Handler:** `get_process_run_telemetry()`
- **DB reads:** Cannot determine without reading telemetry.read_models — process_run table unclear
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/telemetry/components

- **Handler:** `get_component_usage()`
- **DB reads:** `pi_components`, `ds_technology_signals`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/telemetry/components/{component_type}/{component_id}

- **Handler:** `get_component_telemetry()`
- **DB reads:** `pi_components`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/telemetry/attention

- **Handler:** `get_dashboard_attention()`
- **DB reads:** `dashboard_attention_items`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/telemetry/modules

- **Handler:** `get_telemetry_modules()`
- **DB reads:** none (reads source tree module profiles)
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/telemetry/status

- **Handler:** `get_dashboard_data_status()`
- **DB reads:** `ds_projects`, `canonical_events`, `hook_executions` (via `core.telemetry.dashboard_freshness`)
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

---

### router: shared_intelligence (`/api/shared-intelligence`) — `projections/api/routes/shared_intelligence.py`

Large file (31 KB). Delegates almost entirely to `core.shared_intelligence.*` modules. Most routes are read-only projections with no DB writes.

#### GET /api/shared-intelligence/status

- **Handler:** `get_shared_intelligence_status()`
- **DB reads:** multiple shared_intelligence tables (via core delegates)
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/analytics-only

- **Handler:** `get_analytics_only_status()`
- **DB reads:** analytics profile tables
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/module-contracts

- **Handler:** `get_module_contracts()`
- **DB reads:** none (reads source tree YAML)
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/expert-workflows

- **Handler:** `get_expert_workflow_catalog()`
- **DB reads:** none (reads canonical/workflows/ YAML files)
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/career-ops

- **Handler:** `get_career_ops_status()`
- **DB reads:** career ops tables (if present)
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/capability-center

- **Handler:** `get_capability_center()`
- **DB reads:** none (reads source tree)
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/agents/registry

- **Handler:** `get_scoped_agent_registry()`
- **DB reads:** none (reads canonical/agents/ tree)
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/agents/context-packet

- **Handler:** `preview_scoped_agent_context_packet()`
- **DB reads:** none
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/github-repo-intake

- **Handler:** `get_github_repo_intake()`
- **DB reads:** none (reads filesystem / git metadata)
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/platform-hardening

- **Handler:** `get_platform_hardening()`
- **DB reads:** platform hardening tables via `_with_conn`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/platform-hardening/skill-evaluations through /demo (6 sub-routes)

- **Handlers:** `get_skill_evaluation_harness()`, `preview_policy_decision()`, `get_connector_ingestion_framework()`, `get_privacy_redaction_status()`, `get_local_watch_scheduler_status()`, `get_team_pilot_rollup_status()`, `get_installer_distribution_status()`, `get_demo_case_study_system_status()`
- **DB reads:** various platform hardening and registry tables
- **DB writes:** none
- **Response model:** dict each
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/prd-authority

- **Handler:** `get_prd_authority_lifecycle()`
- **DB reads:** `prd_documents`, work_order tables via `core.shared_intelligence.prd_authority`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/adapter-router

- **Handler:** `get_adapter_router_status()`
- **DB reads:** adapter registry tables via `core.installed_runtime.adapter_router_status(conn)`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/security-lifecycle

- **Handler:** `get_security_lifecycle_status()`
- **DB reads:** security tables via `core.security.lifecycle.build_security_lifecycle_gate(conn)`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/production-readiness

- **Handler:** `get_production_readiness_status()`
- **DB reads:** production readiness tables
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/production-readiness/controls

- **Handler:** `get_production_readiness_controls()`
- **DB reads:** same
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/learning-dashboard

- **Handler:** `get_learning_dashboard()`
- **DB reads:** `reg_gotchas`, `reg_workflows`, hook_executions (via `learning_hardening_dashboard_view`)
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/adapters/projections

- **Handler:** `get_adapter_projection_report()`
- **DB reads:** adapter tables
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/adapters/staleness

- **Handler:** `get_adapter_staleness_report()`
- **DB reads:** adapter tables via `core.shared_intelligence.adapter_staleness`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/context-packets/{adapter_id}

- **Handler:** `preview_context_packet()`
- **DB reads:** `ds_projects`, `ds_work_orders`, `ds_design_briefs` (via `generate_shared_context_packet`)
- **DB writes:** none (persist=False in preview mode)
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/capability-routes

- **Handler:** `get_capability_routes()`
- **DB reads:** none (reads source tree)
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/capability-routes/recommendation

- **Handler:** `preview_capability_route()`
- **DB reads:** none
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/model-providers

- **Handler:** `get_model_provider_summary()`
- **DB reads:** none (static registry)
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/model-providers/capability-matrix

- **Handler:** `get_model_provider_capability_matrix()`
- **DB reads:** none
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/ai-usage-accounting

- **Handler:** `get_ai_usage_accounting()`
- **DB reads:** hook_executions, canonical_events (via `core.shared_intelligence.usage_accounting`)
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/task-attribution

- **Handler:** `get_task_attribution()`
- **DB reads:** `ds_tasks`, `ds_work_orders`, `hook_executions` (via `core.shared_intelligence.task_attribution`)
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/task-attribution/work-orders/{work_order_id}

- **Handler:** `get_work_order_task_attribution()`
- **DB reads:** `ds_tasks`, `ds_work_orders`, `hook_executions`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/contract-atlas

- **Handler:** `get_contract_atlas()`
- **DB reads:** contract/registry tables via `core.shared_intelligence.contract_atlas.build_contract_atlas(conn)`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/contract-atlas/maturity-ledger

- **Handler:** `get_contract_atlas_maturity_ledger()`
- **DB reads:** contract tables via `core.shared_intelligence.maturity_ledger`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/contract-atlas/docs-drift

- **Handler:** `get_contract_atlas_docs_drift()`
- **DB reads:** contract tables via `core.shared_intelligence.contract_atlas_lifecycle`
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

#### GET /api/shared-intelligence/contract-atlas/freshness

- **Handler:** `get_contract_atlas_freshness()`
- **DB reads:** contract tables
- **DB writes:** none
- **Response model:** dict
- **Implementation status:** REAL_DATA

---

### Static / infrastructure routes — `projections/api/main.py`

#### GET /

- **Handler:** `root()`
- **DB reads:** none
- **DB writes:** none
- **Response:** FileResponse (dashboard.html) or JSON capability dict
- **Implementation status:** IMPLEMENTED

#### GET /dashboard

- **Handler:** `dashboard()`
- **DB reads:** none
- **DB writes:** none
- **Response:** FileResponse (dashboard.html) or 404
- **Implementation status:** IMPLEMENTED

#### GET /frontend/{file_path:path}

- **Handler:** `frontend_assets()`
- **DB reads:** none
- **DB writes:** none
- **Response:** FileResponse
- **Implementation status:** IMPLEMENTED

#### GET /api/health

- **Handler:** `health_check()`
- **DB reads:** none
- **DB writes:** none
- **Response:** `{"status": "healthy", "version": "1.0.0"}`
- **Implementation status:** IMPLEMENTED

---

## Cross-Gap Observations (mechanical, not judgment)

1. **Workflow commands use file-backed state, not SQLite.** `workflow start/status/list/advance/run` all operate on `workflows.json`. The only SQLite contact is `archive_workflow()` called on completion and `reg_workflows` updates via `control/execution/workflow/learning.py`.

2. **Task and diagnostics commands bypass SQLite entirely.** `task set-active/active/clear-active` use `active_task.json`. `diagnostics list/clear` use `*.jsonl` files. Neither touches studio.db.

3. **ML router has a path-doubling bug.** All routes under `ml.router` resolve to `/api/v1/ml/api/v1/ml/...` because the router prefix is already included in its own route paths. This makes those endpoints unreachable via the documented URL pattern `/api/v1/ml/...`.

4. **POST /api/v1/security/sarif/import is STUBBED.** Source code contains a TODO marker — the parser integration (`parse_sarif_file`) is not wired.

5. **The `ds_work_order.py` module is a separate file-backed work order system** unrelated to the SQLite-backed `work-order` subcommand group in `ds.py`. It handles YAML/JSON work order files used by the file-backed pipeline, not the studio.db records. It is not reachable from the `ds work-order` CLI surface.

6. **No API authentication.** Zero auth decorators on any route. Access controlled by CORS (localhost origins only) and the fact that the server binds to `127.0.0.1` by default.

7. **`db_type` ambiguity in metrics routes.** The metrics router delegates to collectors in `projections/core/collectors/` which use `authority_sources.skill_usage_sql` and `token_usage_sql` — both resolve to `hook_executions`, not the `ds_*` SDLC tables. Metrics routes do not read `ds_work_orders` or `ds_tasks`.

---

# Phase 0c Mechanical Inventory — Gap 4 & Gap 7
## dream-studio-clean | 2026-05-22

---

## Gap 7: Database Schema — Complete Dump

**Source:** `C:\Users\Dannis Seay\.dream-studio\state\studio.db`
**Captured:** 2026-05-22

**Totals:**
- Tables (including FTS shadow tables and internal tables): 182
- Views: 13
- Explicit (non-auto) indexes: 248

---

### All Tables (182)

> Note: The task specification estimated 147 tables. The actual count at dump time is 182, which includes FTS5 shadow tables (`_config`, `_data`, `_docsize`, `_idx`) for `ds_documents_fts`, `fts_gotchas`, and `memory_fts`. Row counts reflect live state as of 2026-05-22.

#### Tables with live row data (non-zero)

| Table | Rows |
|-------|------|
| _schema_version | 61 |
| canonical_events | 1,840 |
| ds_design_briefs | 1 |
| ds_documents | 12 |
| ds_documents_fts (virtual) | 12 |
| ds_documents_fts_config | 1 |
| ds_documents_fts_data | 27 |
| ds_documents_fts_docsize | 12 |
| ds_documents_fts_idx | 25 |
| ds_milestones | 4 |
| ds_projects | 25 |
| ds_tasks | 9 |
| ds_technology_signals | 54 |
| ds_work_order_types | 10 |
| ds_work_orders | 14 |
| execution_events | 929 |
| fts_gotchas (virtual) | 1,488 |
| fts_gotchas_config | 1 |
| fts_gotchas_data | 74 |
| fts_gotchas_docsize | 1,488 |
| fts_gotchas_idx | 72 |
| hook_executions | 45 |
| hook_invocations | 917 |
| memory_fts_config | 1 |
| memory_fts_data | 2 |
| outcome_records | 2 |
| reg_gotchas | (via FTS, row count not shown) |
| tool_invocations | 917 |
| validation_failures | 57 |
| workflow_invocations | 2 |

All other tables have 0 rows.

---

### Full Table Schemas

```
TABLE: _schema_version | rows=61
CREATE TABLE _schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)

TABLE: adapter_authority_profiles | rows=0
CREATE TABLE adapter_authority_profiles (
    adapter_id TEXT PRIMARY KEY,
    adapter_type TEXT NOT NULL,
    adapter_name TEXT NOT NULL,
    authority_role TEXT NOT NULL DEFAULT 'projection',
    owns_source_of_truth INTEGER NOT NULL DEFAULT 0,
    config_projection_path TEXT,
    supported_context_packets_json TEXT NOT NULL DEFAULT '[]',
    supported_result_types_json TEXT NOT NULL DEFAULT '[]',
    stale_detection_policy_json TEXT NOT NULL DEFAULT '{}',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (adapter_type IN ('claude', 'codex', 'cursor', 'copilot', 'chatgpt', 'mcp', 'local_model', 'shell', 'other')),
    CHECK (authority_role IN ('projection', 'executor', 'reviewer', 'observer')),
    CHECK (owns_source_of_truth = 0)
)
INDEXES: sqlite_autoindex_adapter_authority_profiles_1 (pk)

TABLE: adapter_executions | rows=0
CREATE TABLE "adapter_executions" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER,
    adapter_type TEXT NOT NULL,
    normalized_at TEXT NOT NULL,
    execution_time_ms REAL,
    metadata TEXT
)
INDEXES: idx_adapter_executions_activity, idx_adapter_executions_perf, idx_adapter_executions_time, idx_adapter_executions_type

TABLE: adapter_result_records | rows=0
CREATE TABLE adapter_result_records (
    result_id TEXT PRIMARY KEY,
    adapter_id TEXT NOT NULL,
    packet_id TEXT,
    project_id TEXT, milestone_id TEXT, task_id TEXT, process_run_id TEXT,
    result_type TEXT NOT NULL,
    normalized_status TEXT NOT NULL,
    decision_refs_json TEXT NOT NULL DEFAULT '[]',
    code_change_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    validation_refs_json TEXT NOT NULL DEFAULT '[]',
    research_refs_json TEXT NOT NULL DEFAULT '[]',
    risk_refs_json TEXT NOT NULL DEFAULT '[]',
    artifact_refs_json TEXT NOT NULL DEFAULT '[]',
    outcome_refs_json TEXT NOT NULL DEFAULT '[]',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (adapter_id) REFERENCES adapter_authority_profiles(adapter_id),
    FOREIGN KEY (packet_id) REFERENCES shared_context_packets(packet_id)
)
FOREIGN KEYS: adapter_id → adapter_authority_profiles, packet_id → shared_context_packets
INDEXES: idx_adapter_results_scope

TABLE: agent_context_scope_policies | rows=0
CREATE TABLE agent_context_scope_policies (
    policy_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    policy_status TEXT NOT NULL DEFAULT 'active',
    required_context_json TEXT NOT NULL DEFAULT '[]',
    forbidden_context_json TEXT NOT NULL DEFAULT '[]',
    forbidden_by_default_json TEXT NOT NULL DEFAULT '[]',
    approval_required_json TEXT NOT NULL DEFAULT '[]',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (agent_id) REFERENCES agent_registry_records(agent_id)
)
FOREIGN KEYS: agent_id → agent_registry_records

TABLE: agent_invocations | rows=0
CREATE TABLE agent_invocations (
    invocation_id TEXT PRIMARY KEY,
    project_id TEXT, milestone_id TEXT, task_id TEXT, process_run_id TEXT,
    event_id TEXT,
    agent_id TEXT NOT NULL,
    status TEXT NOT NULL,
    purpose TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES execution_events(event_id)
)
FOREIGN KEYS: event_id → execution_events
INDEXES: idx_agent_invocations_scope

TABLE: agent_registry_records | rows=0
CREATE TABLE agent_registry_records (
    agent_id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    purpose TEXT NOT NULL,
    allowed_tools_json TEXT NOT NULL DEFAULT '[]',
    read_scope_json TEXT NOT NULL DEFAULT '[]',
    write_scope_json TEXT NOT NULL DEFAULT '[]',
    data_sensitivity_scope_json TEXT NOT NULL DEFAULT '[]',
    required_context_json TEXT NOT NULL DEFAULT '[]',
    forbidden_context_json TEXT NOT NULL DEFAULT '[]',
    output_contract_json TEXT NOT NULL DEFAULT '{}',
    validation_requirements_json TEXT NOT NULL DEFAULT '[]',
    approval_boundaries_json TEXT NOT NULL DEFAULT '[]',
    risk_level TEXT NOT NULL DEFAULT 'medium',
    max_context_budget INTEGER NOT NULL DEFAULT 8000,
    allowed_data_classes_json TEXT NOT NULL DEFAULT '[]',
    result_schema_json TEXT NOT NULL DEFAULT '{}',
    enabled INTEGER NOT NULL DEFAULT 1,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (risk_level IN ('low', 'medium', 'high')),
    CHECK (enabled IN (0, 1))
)
INDEXES: idx_agent_registry_enabled

TABLE: agent_result_records | rows=0
CREATE TABLE agent_result_records (
    agent_result_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    project_id TEXT, task_id TEXT,
    result_status TEXT NOT NULL,
    normalized_target_tables_json TEXT NOT NULL DEFAULT '[]',
    result_payload_json TEXT NOT NULL DEFAULT '{}',
    validation_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (agent_id) REFERENCES agent_registry_records(agent_id)
)
FOREIGN KEYS: agent_id → agent_registry_records

TABLE: ai_adapter_accounting_profiles | rows=0
CREATE TABLE ai_adapter_accounting_profiles (
    profile_id TEXT PRIMARY KEY,
    adapter_id TEXT NOT NULL,
    provider TEXT, model_id TEXT,
    configuration_label TEXT NOT NULL,
    billing_mode TEXT NOT NULL,
    token_visibility TEXT NOT NULL,
    cost_visibility TEXT NOT NULL,
    usage_source TEXT NOT NULL,
    cost_source TEXT NOT NULL DEFAULT 'unavailable',
    confidence TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (billing_mode IN ('subscription_plan','plan_allowance','token_metered','api_metered','credit_metered','enterprise_contract','unknown','unavailable')),
    CHECK (token_visibility IN ('exact','partial','estimated','unavailable')),
    CHECK (cost_visibility IN ('exact','provider_reported','estimated','allocated_subscription_cost','unavailable','unknown')),
    CHECK (usage_source IN ('provider_metadata','provider_usage_export','local_telemetry','plan_usage_panel','manual_config','unavailable')),
    CHECK (cost_source IN ('provider_metadata','provider_usage_export','billing_api','plan_allocation_config','local_estimate','unavailable','unknown')),
    CHECK (confidence IN ('high','medium','low','unknown')),
    CHECK (active IN (0, 1)),
    FOREIGN KEY (adapter_id) REFERENCES adapter_authority_profiles(adapter_id)
)
FOREIGN KEYS: adapter_id → adapter_authority_profiles
INDEXES: idx_ai_accounting_profiles_adapter

TABLE: ai_usage_operational_records | rows=0
CREATE TABLE ai_usage_operational_records (
    usage_record_id TEXT PRIMARY KEY,
    project_id TEXT, milestone_id TEXT, task_id TEXT, work_order_id TEXT, process_run_id TEXT,
    adapter_id TEXT NOT NULL,
    provider TEXT, model_id TEXT, accounting_profile_id TEXT, token_usage_id TEXT,
    billing_mode TEXT NOT NULL DEFAULT 'unknown',
    token_visibility TEXT NOT NULL DEFAULT 'unavailable',
    cost_visibility TEXT NOT NULL DEFAULT 'unknown',
    usage_source TEXT NOT NULL DEFAULT 'local_telemetry',
    cost_source TEXT NOT NULL DEFAULT 'unknown',
    confidence TEXT NOT NULL DEFAULT 'unknown',
    input_tokens INTEGER, output_tokens INTEGER, cached_tokens INTEGER, total_tokens INTEGER,
    cost_amount REAL, cost_currency TEXT,
    run_count INTEGER NOT NULL DEFAULT 1,
    files_touched_json TEXT NOT NULL DEFAULT '[]',
    commands_run_json TEXT NOT NULL DEFAULT '[]',
    validation_result TEXT, pr_result_outcome TEXT, success INTEGER, failure_reason TEXT, rework_needed INTEGER,
    security_findings_json TEXT NOT NULL DEFAULT '[]',
    readiness_findings_json TEXT NOT NULL DEFAULT '[]',
    duration_ms INTEGER,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    [multiple CHECK constraints on billing_mode, token_visibility, cost_visibility, usage_source, cost_source, confidence, success, rework_needed]
    FOREIGN KEY (adapter_id) REFERENCES adapter_authority_profiles(adapter_id),
    FOREIGN KEY (accounting_profile_id) REFERENCES ai_adapter_accounting_profiles(profile_id),
    FOREIGN KEY (token_usage_id) REFERENCES token_usage_records(token_usage_id)
)
INDEXES: idx_ai_usage_operational_process, idx_ai_usage_operational_scope

TABLE: alert_history | rows=0
CREATE TABLE alert_history (
    alert_id TEXT PRIMARY KEY,
    rule_id TEXT,
    triggered_at TEXT NOT NULL,
    metric_value REAL,
    severity TEXT,
    resolved_at TEXT,
    FOREIGN KEY (rule_id) REFERENCES alert_rules(rule_id)
)
FOREIGN KEYS: rule_id → alert_rules
INDEXES: idx_alert_history_rule, idx_alert_history_triggered

TABLE: alert_rules | rows=0
CREATE TABLE alert_rules (
    rule_id TEXT PRIMARY KEY,
    rule_name TEXT NOT NULL,
    metric_path TEXT NOT NULL,
    condition TEXT NOT NULL,
    threshold REAL,
    severity TEXT,
    enabled BOOLEAN DEFAULT 1
)
INDEXES: idx_alert_rules_enabled

TABLE: artifact_authority_records | rows=0
CREATE TABLE artifact_authority_records (
    record_id TEXT PRIMARY KEY,
    record_type TEXT NOT NULL,
    project_id TEXT, milestone_id TEXT, task_id TEXT, process_run_id TEXT,
    source_path TEXT, source_hash TEXT,
    authority_status TEXT NOT NULL DEFAULT 'canonical',
    file_is_export INTEGER NOT NULL DEFAULT 1,
    human_export_path TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    supersedes_record_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (record_type IN ('work_order','handoff','continuation_packet','evidence_summary','report','route_decision','release_packet','cleanup_cutover_record','operator_decision','other')),
    CHECK (authority_status IN ('canonical','superseded','draft','export_only','rejected')),
    FOREIGN KEY (supersedes_record_id) REFERENCES artifact_authority_records(record_id)
)
INDEXES: idx_artifact_authority_scope

TABLE: artifact_records | rows=0
CREATE TABLE artifact_records (
    artifact_id TEXT PRIMARY KEY,
    project_id TEXT, milestone_id TEXT, task_id TEXT, process_run_id TEXT,
    event_id TEXT,
    artifact_path TEXT NOT NULL,
    artifact_role TEXT NOT NULL,
    lifecycle_status TEXT NOT NULL,
    source_authority TEXT,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES execution_events(event_id)
)
FOREIGN KEYS: event_id → execution_events
INDEXES: idx_artifact_records_scope

TABLE: audit_runs | rows=0
CREATE TABLE audit_runs (
    audit_id TEXT PRIMARY KEY,
    activity_id INTEGER,
    audit_type TEXT NOT NULL CHECK(audit_type IN ('code_quality','security','performance','architecture','compliance')),
    audit_scope TEXT NOT NULL CHECK(audit_scope IN ('project','prd','task','skill','file','function')),
    target_id TEXT NOT NULL,
    target_type TEXT NOT NULL CHECK(target_type IN ('project','prd','task','skill','file','function','module')),
    status TEXT NOT NULL CHECK(status IN ('running','completed','failed','cancelled')) DEFAULT 'running',
    findings_count INTEGER DEFAULT 0,
    critical_count INTEGER DEFAULT 0,
    high_count INTEGER DEFAULT 0,
    medium_count INTEGER DEFAULT 0,
    low_count INTEGER DEFAULT 0,
    report_path TEXT,
    summary TEXT,
    started_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    completed_at TEXT,
    duration_s REAL,
    FOREIGN KEY (activity_id) REFERENCES activity_log(activity_id) ON DELETE SET NULL
)
NOTE: FK to activity_log which was dropped in migration 063. Dangling FK.
INDEXES: idx_audit_severity (partial), idx_audit_started, idx_audit_target, idx_audit_type_status

TABLE: authority_projection_records | rows=0
CREATE TABLE authority_projection_records (
    projection_id TEXT PRIMARY KEY,
    project_id TEXT, milestone_id TEXT, task_id TEXT, process_run_id TEXT, event_id TEXT,
    projection_domain TEXT NOT NULL,
    source_authority TEXT NOT NULL,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    lifecycle_status TEXT NOT NULL,
    authority_role TEXT NOT NULL,
    derived_fields_json TEXT NOT NULL DEFAULT '{}',
    confidence TEXT NOT NULL DEFAULT 'unknown',
    stale_superseded_json TEXT NOT NULL DEFAULT '{}',
    stop_gate_implications_json TEXT NOT NULL DEFAULT '[]',
    validation_requirements_json TEXT NOT NULL DEFAULT '[]',
    dashboard_readiness_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES execution_events(event_id)
)
INDEXES: idx_authority_projection_scope

TABLE: automation_checkpoints | rows=0
CREATE TABLE automation_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    checkpoint_name TEXT NOT NULL,
    checkpoint_data TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES automation_log(run_id) ON DELETE CASCADE
)
FOREIGN KEYS: run_id → automation_log (CASCADE)
INDEXES: idx_checkpoint_run, idx_checkpoint_created, idx_checkpoint_run_created

TABLE: automation_log | rows=0
CREATE TABLE automation_log (
    run_id TEXT PRIMARY KEY,
    script_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    items_processed INTEGER DEFAULT 0,
    items_total INTEGER,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0
)
INDEXES: idx_automation_log_started_at, idx_automation_log_status

TABLE: blocker_resolution_records | rows=0
CREATE TABLE blocker_resolution_records (
    blocker_id TEXT PRIMARY KEY,
    project_id TEXT, milestone_id TEXT, task_id TEXT, process_run_id TEXT, event_id TEXT,
    blocker_class TEXT NOT NULL,
    route_class TEXT NOT NULL,
    confidence TEXT NOT NULL,
    resolution_status TEXT NOT NULL,
    prompt_required INTEGER NOT NULL DEFAULT 0,
    dashboard_approval_required INTEGER NOT NULL DEFAULT 0,
    rationale TEXT,
    research_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES execution_events(event_id)
)
INDEXES: idx_blocker_records_scope

TABLE: canonical_events | rows=1,840
CREATE TABLE canonical_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    trace JSON NOT NULL DEFAULT '{}',
    severity TEXT NOT NULL DEFAULT 'info',
    payload JSON NOT NULL DEFAULT '{}',
    actor JSON,
    confidence_score REAL,
    source_type TEXT,
    raw_prompt_retained INTEGER NOT NULL DEFAULT 0,
    raw_tool_output_retained INTEGER NOT NULL DEFAULT 0,
    schema_version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    invocation_mode TEXT   -- added by migration 052 via ALTER TABLE
)
INDEXES: idx_canonical_events_timestamp, idx_canonical_events_event_type

TABLE: capability_center_records | rows=0
CREATE TABLE capability_center_records (
    capability_record_id TEXT PRIMARY KEY,
    component_type TEXT NOT NULL,
    component_id TEXT NOT NULL,
    name TEXT NOT NULL,
    purpose TEXT, version TEXT, owner TEXT,
    input_contract_json TEXT NOT NULL DEFAULT '{}',
    output_contract_json TEXT NOT NULL DEFAULT '{}',
    trigger_conditions_json TEXT NOT NULL DEFAULT '[]',
    when_not_to_run_json TEXT NOT NULL DEFAULT '[]',
    known_gaps_json TEXT NOT NULL DEFAULT '[]',
    hardening_candidates_json TEXT NOT NULL DEFAULT '[]',
    evaluation_status TEXT NOT NULL DEFAULT 'unavailable',
    evaluation_score REAL,
    supersession_status TEXT NOT NULL DEFAULT 'current',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    last_reviewed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (component_type IN ('skill','workflow','agent','control','evaluation','hardening_candidate')),
    CHECK (evaluation_status IN ('unavailable','partial','validated','manual_review_required')),
    CHECK (supersession_status IN ('current','superseded','deprecated','manual_review_required'))
)
INDEXES: idx_capability_center_component

TABLE: capability_route_records | rows=0
CREATE TABLE capability_route_records (
    capability_route_id TEXT PRIMARY KEY,
    project_id TEXT, milestone_id TEXT, task_id TEXT, process_run_id TEXT,
    task_class TEXT NOT NULL,
    selected_adapter_id TEXT,
    selected_model_profile_id TEXT,
    route_basis_json TEXT NOT NULL DEFAULT '{}',
    risk_level TEXT NOT NULL DEFAULT 'medium',
    cost_sensitivity TEXT NOT NULL DEFAULT 'medium',
    validation_required INTEGER NOT NULL DEFAULT 1,
    operator_approval_required INTEGER NOT NULL DEFAULT 0,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (selected_adapter_id) REFERENCES adapter_authority_profiles(adapter_id),
    FOREIGN KEY (selected_model_profile_id) REFERENCES model_provider_profiles(model_profile_id)
)
INDEXES: idx_capability_routes_scope

TABLE: career_application_events | rows=0
TABLE: career_application_field_mappings | rows=0
TABLE: career_applications | rows=0
TABLE: career_browser_automation_runs | rows=0
TABLE: career_case_studies | rows=0
TABLE: career_cover_letter_versions | rows=0
TABLE: career_evidence_refs | rows=0
TABLE: career_interview_story_bank | rows=0
TABLE: career_job_opportunities | rows=0
TABLE: career_portfolio_artifacts | rows=0
TABLE: career_profile_fields | rows=0
TABLE: career_profiles | rows=0
TABLE: career_resume_versions | rows=0
TABLE: career_role_targets | rows=0
TABLE: career_scorecards | rows=0
-- All career_* tables added in migration 044. All 0 rows. All have career_profiles as root FK anchor.

TABLE: compliance_review_flags | rows=0
TABLE: connector_ingestion_runs | rows=0

TABLE: cor_skill_corrections | rows=0
CREATE TABLE cor_skill_corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telemetry_id INTEGER NOT NULL REFERENCES raw_skill_telemetry(id),
    corrected_success INTEGER NOT NULL,
    reason TEXT,
    corrected_at TEXT NOT NULL
)
FOREIGN KEYS: telemetry_id → raw_skill_telemetry
INDEXES: idx_corrections_telemetry

TABLE: dashboard_attention_items | rows=0
TABLE: dashboard_authority_reconciliation_records | rows=0

TABLE: decision_event_link | rows=0
CREATE TABLE decision_event_link (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    FOREIGN KEY (decision_id) REFERENCES decision_log(decision_id)
)
INDEXES: idx_link_decision, idx_link_event, idx_link_relation

TABLE: decision_log | rows=0
CREATE TABLE decision_log (
    decision_id TEXT PRIMARY KEY,
    decision_type TEXT NOT NULL,
    context TEXT, outcome TEXT, reasoning TEXT NOT NULL, confidence REAL,
    policy_applied TEXT, source_subsystem TEXT, timestamp TEXT NOT NULL
)
INDEXES: idx_decision_type, idx_decision_subsystem, idx_decision_timestamp, idx_decision_confidence

TABLE: decision_records | rows=0
TABLE: demo_case_study_packets | rows=0

TABLE: ds_design_briefs | rows=1
CREATE TABLE ds_design_briefs (
    brief_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES ds_projects(project_id),
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','locked')),
    purpose TEXT, audience TEXT, tone TEXT, design_system TEXT,
    font_pairing TEXT, brand_tokens TEXT, raw_output TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
)
INDEXES: idx_ds_design_briefs_project

TABLE: ds_documents | rows=12
CREATE TABLE ds_documents (
    doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_type TEXT NOT NULL,
    parent_doc_id INTEGER,
    project_id TEXT REFERENCES reg_projects(project_id),
    skill_id TEXT REFERENCES reg_skills(skill_id),
    session_id TEXT REFERENCES raw_sessions(session_id),
    title TEXT NOT NULL,
    content TEXT, format TEXT DEFAULT 'markdown',
    metadata TEXT, tags TEXT, keywords TEXT,
    version INTEGER DEFAULT 1,
    status TEXT DEFAULT 'active',
    created_at TEXT NOT NULL, created_by TEXT, updated_at TEXT,
    access_count INTEGER DEFAULT 0, last_accessed TEXT, ttl_days INTEGER, expires_at TEXT,
    source_path TEXT,   -- added by migration 050
    FOREIGN KEY (parent_doc_id) REFERENCES ds_documents(doc_id)
)
INDEXES: idx_ds_documents_type, idx_ds_documents_project, idx_ds_documents_skill,
         idx_ds_documents_session, idx_ds_documents_created, idx_ds_documents_expires,
         idx_ds_documents_parent, idx_ds_documents_source_path

TABLE: ds_documents_fts | rows=12 (virtual)
CREATE VIRTUAL TABLE ds_documents_fts USING fts5(
    title, content, keywords, tags,
    content=ds_documents, content_rowid=doc_id
)
-- Shadow tables: ds_documents_fts_config, ds_documents_fts_data, ds_documents_fts_docsize, ds_documents_fts_idx

TABLE: ds_milestones | rows=4
CREATE TABLE ds_milestones (
    milestone_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES ds_projects(project_id),
    title TEXT NOT NULL, description TEXT, due_date TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','active','complete','skipped')),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    order_index INTEGER DEFAULT 0   -- added by migration 056
)
INDEXES: idx_ds_milestones_project

TABLE: ds_projects | rows=25
CREATE TABLE ds_projects (
    project_id TEXT PRIMARY KEY,
    name TEXT NOT NULL, description TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','paused','archived','complete')),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
)

TABLE: ds_tasks | rows=9
CREATE TABLE ds_tasks (
    task_id TEXT PRIMARY KEY,
    work_order_id TEXT NOT NULL REFERENCES ds_work_orders(work_order_id),
    project_id TEXT NOT NULL REFERENCES ds_projects(project_id),
    title TEXT NOT NULL, description TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','in_progress','blocked','complete','cancelled')),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
)
INDEXES: idx_ds_tasks_work_order, idx_ds_tasks_project

TABLE: ds_technology_signals | rows=54
CREATE TABLE ds_technology_signals (
    signal_id TEXT PRIMARY KEY,
    extension TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    last_seen TEXT NOT NULL
)

TABLE: ds_work_order_types | rows=10
CREATE TABLE ds_work_order_types (
    type_id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    pre_build_gate TEXT, build_executor TEXT, post_build_gate TEXT,
    workflow_template TEXT,         -- added by migration 057
    precondition_skill TEXT,        -- added by migration 057
    task_generator TEXT,            -- added by migration 057
    resolution_instructions TEXT    -- added by migration 057
)

TABLE: ds_work_orders | rows=14
CREATE TABLE ds_work_orders (
    work_order_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES ds_projects(project_id),
    milestone_id TEXT REFERENCES ds_milestones(milestone_id),
    title TEXT NOT NULL, description TEXT,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK(status IN ('open','in_progress','review','complete','cancelled','blocked')),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    work_order_type TEXT,   -- added by migration 049
    block_reason TEXT       -- added by migration 051
)
INDEXES: idx_ds_work_orders_project, idx_ds_work_orders_milestone

TABLE: execution_dependencies | rows=0
CREATE TABLE execution_dependencies (
    dependency_id TEXT PRIMARY KEY,
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    dependency_type TEXT NOT NULL CHECK(dependency_type IN ('blocks','informs','follows')),
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (source_node_id) REFERENCES execution_nodes(node_id),
    FOREIGN KEY (target_node_id) REFERENCES execution_nodes(node_id),
    UNIQUE(source_node_id, target_node_id, dependency_type)
)
INDEXES: idx_execution_deps_source, idx_execution_deps_target, idx_execution_deps_type

TABLE: execution_event_links | rows=0
CREATE TABLE execution_event_links (
    link_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (node_id) REFERENCES execution_nodes(node_id),
    UNIQUE(node_id, event_id)
)
INDEXES: idx_execution_event_links_node, idx_execution_event_links_event

TABLE: execution_events | rows=929
CREATE TABLE execution_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL, event_name TEXT NOT NULL,
    project_id TEXT, milestone_id TEXT, task_id TEXT, process_run_id TEXT,
    parent_event_id TEXT,
    actor_type TEXT, actor_id TEXT,
    agent_id TEXT, skill_id TEXT, workflow_id TEXT, hook_id TEXT, tool_id TEXT,
    model_id TEXT, adapter_id TEXT,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    outcome_status TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    _built_from_event_id TEXT,   -- added by migration 059
    FOREIGN KEY (parent_event_id) REFERENCES execution_events(event_id)
)
INDEXES: idx_execution_events_scope, idx_execution_events_process,
         idx_execution_events_canonical_link (partial, WHERE _built_from_event_id IS NOT NULL)

TABLE: execution_nodes | rows=0
CREATE TABLE execution_nodes (
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL CHECK(node_type IN ('project','prd','plan','phase','wave','task')),
    parent_id TEXT, project_id TEXT, prd_id TEXT, plan_id TEXT, phase_id TEXT, wave_id TEXT,
    title TEXT NOT NULL, description TEXT,
    metadata JSON, context_hash TEXT, context_summary TEXT, context_tokens INTEGER,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','active','blocked','completed','failed','skipped')),
    priority INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT, completed_at TEXT, duration_seconds REAL,
    FOREIGN KEY (parent_id) REFERENCES execution_nodes(node_id),
    [5 additional self-referential FKs for project_id, prd_id, plan_id, phase_id, wave_id]
)
INDEXES: idx_execution_nodes_parent, idx_execution_nodes_project, idx_execution_nodes_status,
         idx_execution_nodes_type, idx_execution_nodes_created

TABLE: execution_outputs | rows=0
CREATE TABLE execution_outputs (
    output_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    output_type TEXT NOT NULL CHECK(output_type IN ('code','document','decision','artifact','result')),
    output_hash TEXT, output_summary TEXT, output_data JSON, file_paths TEXT, tokens_produced INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (node_id) REFERENCES execution_nodes(node_id)
)
INDEXES: idx_execution_outputs_node, idx_execution_outputs_type, idx_execution_outputs_created

TABLE: fts_gotchas | virtual
CREATE VIRTUAL TABLE fts_gotchas USING fts5(
    gotcha_id, title, context, fix, keywords,
    content=reg_gotchas, content_rowid=rowid
)
-- Shadow tables: fts_gotchas_config (1 row), fts_gotchas_data (74 rows), fts_gotchas_docsize (1488 rows), fts_gotchas_idx (72 rows)

TABLE: github_repo_adoption_decisions | rows=0
TABLE: github_repo_attribution_records | rows=0
TABLE: github_repo_dependency_findings | rows=0
TABLE: github_repo_evaluations | rows=0
TABLE: github_repo_integration_candidates | rows=0
TABLE: github_repo_license_findings | rows=0
TABLE: github_repo_pattern_references | rows=0
TABLE: github_repo_security_findings | rows=0
-- All github_repo_* tables added in migration 044. 0 rows. FK anchor: github_repo_evaluations.

TABLE: guardrail_decisions | rows=0
CREATE TABLE guardrail_decisions (
    decision_id TEXT PRIMARY KEY,
    rule_id TEXT NOT NULL,
    event_id TEXT,
    action TEXT NOT NULL CHECK(action IN ('allow','block','require_approval','advisory')),
    message TEXT NOT NULL, evaluated_at TEXT NOT NULL, metadata TEXT
)
INDEXES: idx_guardrail_decisions_rule_id, idx_guardrail_decisions_evaluated_at, idx_guardrail_decisions_action

TABLE: guardrail_rules_audit | rows=0
CREATE TABLE guardrail_rules_audit (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id TEXT NOT NULL,
    loaded_at TEXT NOT NULL, file_path TEXT NOT NULL, rule_hash TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1))
)
INDEXES: idx_guardrail_rules_audit_rule_id

TABLE: hardening_candidate_records | rows=0
TABLE: hook_executions | rows=45
CREATE TABLE "hook_executions" (
    hook_exec_id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER,   -- nullable (nullified by migration 062)
    hook_name TEXT NOT NULL, hook_type TEXT, trigger_context TEXT,
    started_at DATETIME NOT NULL, completed_at DATETIME,
    duration_ms INTEGER, exit_code INTEGER,
    status TEXT CHECK(status IN ('pending','running','success','failed','timeout')),
    output TEXT, error_message TEXT, cpu_time_ms INTEGER, memory_mb REAL
)
NOTE: activity_id was NOT NULL FK to activity_log in migration 018; made nullable in 062.
INDEXES: idx_hook_exec_activity, idx_hook_exec_name_status, idx_hook_exec_duration, idx_hook_exec_started

TABLE: hook_findings | rows=0
CREATE TABLE "hook_findings" (
    finding_id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER,   -- nullable (nullified by migration 062)
    hook_exec_id INTEGER NOT NULL,
    finding_type TEXT NOT NULL,
    severity TEXT CHECK(severity IN ('info','warning','error','critical')),
    message TEXT NOT NULL, context TEXT, recommendation TEXT,
    status TEXT CHECK(status IN ('open','acknowledged','resolved','wont_fix')),
    resolved_at DATETIME, resolution_notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (hook_exec_id) REFERENCES hook_executions(hook_exec_id) ON DELETE CASCADE
)
FOREIGN KEYS: hook_exec_id → hook_executions (CASCADE)
INDEXES: idx_hook_finding_activity, idx_hook_finding_exec, idx_hook_finding_status_severity

TABLE: hook_invocations | rows=917
CREATE TABLE hook_invocations (
    invocation_id TEXT PRIMARY KEY,
    project_id TEXT, milestone_id TEXT, task_id TEXT, process_run_id TEXT, event_id TEXT,
    hook_id TEXT NOT NULL, status TEXT NOT NULL,
    prevented_risky_action INTEGER NOT NULL DEFAULT 0,
    purpose TEXT, metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES execution_events(event_id)
)
INDEXES: idx_hook_invocations_scope

TABLE: installer_distribution_checks | rows=0
TABLE: learning_event_records | rows=0

TABLE: legacy_canonical_event_import_map | rows=0
CREATE TABLE legacy_canonical_event_import_map (
    import_map_id TEXT PRIMARY KEY,
    legacy_event_id TEXT NOT NULL,
    source_table TEXT NOT NULL DEFAULT 'canonical_events',
    event_type TEXT NOT NULL, taxonomy TEXT NOT NULL,
    target_table TEXT, target_record_id TEXT,
    import_status TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0,
    payload_hash TEXT NOT NULL, reason TEXT NOT NULL,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK(import_status IN ('pending_import','imported','skipped_duplicate','manual_review_required',
                            'retention_only','obsolete_no_action','superseded_by_current_authority',
                            'not_mapped','error'))
)
INDEXES: idx_legacy_event_import_map_target (UNIQUE), idx_legacy_event_import_map_status, idx_legacy_event_import_map_type

TABLE: local_watch_schedule_records | rows=0
TABLE: log_batch_imports | rows=0

TABLE: memory_fts | virtual
CREATE VIRTUAL TABLE memory_fts USING fts5(
    memory_id UNINDEXED, content, category, tags
)
-- Shadow tables: memory_fts_config (1 row), memory_fts_content (0), memory_fts_data (2), memory_fts_docsize (0), memory_fts_idx (0)

TABLE: memory_entries | rows=0 (not shown in dump — FTS5 content table referenced by fts_gotchas)
-- Note: memory_entries has 8 additional columns added by migration 032.

TABLE: model_provider_profiles | rows=0
CREATE TABLE model_provider_profiles (
    model_profile_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL, model_id TEXT NOT NULL,
    capability_tags_json TEXT NOT NULL DEFAULT '[]',
    context_limit_tokens INTEGER,
    cost_profile_json TEXT NOT NULL DEFAULT '{}',
    token_behavior_json TEXT NOT NULL DEFAULT '{}',
    output_quality_json TEXT NOT NULL DEFAULT '{}',
    failure_modes_json TEXT NOT NULL DEFAULT '[]',
    best_use_patterns_json TEXT NOT NULL DEFAULT '[]',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(provider, model_id)
)

TABLE: outcome_records | rows=2
TABLE: pi_analysis_runs | rows=0
TABLE: pi_bugs | rows=0
TABLE: pi_components | rows=0
TABLE: pi_dependencies | rows=0
TABLE: pi_improvements | rows=0
TABLE: pi_violations | rows=0
TABLE: pi_wave_tasks | rows=0
TABLE: pi_waves | rows=0
TABLE: policy_decision_records | rows=0
TABLE: prd_amendment_records | rows=0
TABLE: prd_documents | rows=0
TABLE: prd_handoffs | rows=0
TABLE: prd_plans | rows=0
TABLE: prd_route_reconciliation_records | rows=0
TABLE: prd_sessions | rows=0
TABLE: prd_tasks | rows=0
TABLE: prd_version_records | rows=0
TABLE: privacy_redaction_export_records | rows=0
TABLE: process_runs | rows=0

TABLE: production_readiness_assessment_runs | rows=0
TABLE: production_readiness_control_results | rows=0
TABLE: production_readiness_findings | rows=0
TABLE: production_readiness_remediation_work_orders | rows=0
TABLE: production_readiness_skill_control_mappings | rows=0
TABLE: project_assumption_records | rows=0
TABLE: project_change_order_records | rows=0
TABLE: project_health_scorecards | rows=0
TABLE: project_intake_questions | rows=0
TABLE: project_intake_records | rows=0
TABLE: project_milestone_records | rows=0
TABLE: project_readiness_scorecards | rows=0
TABLE: project_work_order_authority_records | rows=0

TABLE: raw_approaches | rows=0
TABLE: raw_handoffs | rows=0
TABLE: raw_lessons | rows=0
TABLE: raw_operational_snapshots | rows=0
TABLE: raw_planning_specs | rows=0
TABLE: raw_pulse_snapshots | rows=0
TABLE: raw_research | rows=0
TABLE: raw_sentinels | rows=0
TABLE: raw_sessions | rows=0
TABLE: raw_skill_telemetry | rows=0
TABLE: raw_specs | rows=0
TABLE: raw_tasks | rows=0
TABLE: raw_token_usage | rows=0
TABLE: raw_workflow_nodes | rows=0
TABLE: raw_workflow_runs | rows=0

TABLE: reg_analyzed_repos | rows=0
TABLE: reg_gotchas | rows=0 (content table for fts_gotchas; FTS docsize shows 1488 historical rows)
TABLE: reg_projects | rows=0
TABLE: reg_repo_extractions | rows=0
TABLE: reg_repo_research_links | rows=0
TABLE: reg_research_sources | rows=0
TABLE: reg_skill_deps | rows=0
TABLE: reg_skills | rows=0
TABLE: reg_workflows | rows=0

TABLE: release_readiness_records | rows=0
TABLE: research_cache | rows=0
TABLE: research_evidence_records | rows=0
TABLE: risk_mitigations | rows=0
TABLE: risk_register | rows=0
TABLE: route_decision_records | rows=0

TABLE: sec_cve_matches | rows=0
CREATE TABLE "sec_cve_matches" (
    cve_id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER,  -- nullable after migration 062
    package_name TEXT NOT NULL, package_version TEXT, cve_number TEXT,
    severity TEXT CHECK(severity IN ('critical','high','medium','low','info')),
    cvss_score REAL, description TEXT, status TEXT DEFAULT 'open',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
INDEXES: idx_cve_activity, idx_cve_status, idx_cve_severity, idx_cve_package

TABLE: sec_hook_checks | rows=0
CREATE TABLE "sec_hook_checks" (
    check_id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER,   -- nullable after migration 062
    hook_exec_id INTEGER NOT NULL,
    check_name TEXT NOT NULL, check_result TEXT NOT NULL,
    details TEXT, severity TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (hook_exec_id) REFERENCES hook_executions(hook_exec_id) ON DELETE CASCADE
)
INDEXES: idx_hook_check_activity, idx_hook_check_exec, idx_hook_check_result

TABLE: sec_manual_reviews | rows=0
CREATE TABLE "sec_manual_reviews" (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER,   -- nullable after migration 062
    reviewer TEXT, review_type TEXT,
    risk_level TEXT CHECK(risk_level IN ('critical','high','medium','low')),
    findings TEXT, status TEXT DEFAULT 'pending', reviewed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
INDEXES: idx_review_activity, idx_review_status, idx_review_risk

TABLE: sec_sarif_findings | rows=0
CREATE TABLE "sec_sarif_findings" (
    sarif_finding_id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER,   -- nullable after migration 062
    scan_tool TEXT, rule_id TEXT, severity TEXT,
    file_path TEXT, line_number INTEGER, message TEXT,
    status TEXT DEFAULT 'open', fingerprint TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
INDEXES: idx_sarif_activity, idx_sarif_status, idx_sarif_severity, idx_sarif_rule_file

TABLE: security_findings | rows=0
CREATE TABLE security_findings (
    finding_id TEXT PRIMARY KEY,
    project_id TEXT, milestone_id TEXT, task_id TEXT,
    scan_id TEXT, process_run_id TEXT,
    severity TEXT NOT NULL, category TEXT, rule_id TEXT,
    file_path TEXT, start_line INTEGER, end_line INTEGER,
    description TEXT NOT NULL, recommendation TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    introduced_by_agent_id TEXT, introduced_by_skill_id TEXT,
    introduced_by_workflow_id TEXT, introduced_by_hook_id TEXT,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
)
INDEXES: idx_security_findings_scope, idx_security_findings_file

TABLE: session_tasks | rows=0
TABLE: shared_context_packets | rows=0

TABLE: skill_evaluation_runs | rows=0
TABLE: skill_invocations | rows=0

TABLE: sum_analytics_run | rows=0
TABLE: sum_skill_summary | rows=0

TABLE: task_attribution_records | rows=0
CREATE TABLE task_attribution_records (
    record_id TEXT PRIMARY KEY,
    project_id TEXT, work_order_id TEXT, process_run_id TEXT,
    adapter_id TEXT, skill_id TEXT, workflow_id TEXT,
    task_type TEXT NOT NULL,
    execution_started_at TEXT, execution_completed_at TEXT,
    outcome TEXT NOT NULL,
    quality_score REAL, rework_required INTEGER NOT NULL DEFAULT 0,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
)
INDEXES: idx_task_attribution_project, idx_task_attribution_work_order,
         idx_task_attribution_process, idx_task_attribution_adapter, idx_task_attribution_outcome

TABLE: team_rollup_records | rows=0
TABLE: telemetry_entity_registry | rows=0
TABLE: telemetry_module_registry | rows=0

TABLE: token_usage_records | rows=0
CREATE TABLE token_usage_records (
    token_usage_id TEXT PRIMARY KEY,
    project_id TEXT, milestone_id TEXT, task_id TEXT, process_run_id TEXT,
    agent_id TEXT, skill_id TEXT, workflow_id TEXT, hook_id TEXT,
    model_id TEXT, provider TEXT,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_cost REAL NOT NULL DEFAULT 0,
    purpose TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    -- Added by migrations 042 and 043:
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    adapter_id TEXT,
    billing_mode TEXT NOT NULL DEFAULT 'unknown',
    token_visibility TEXT NOT NULL DEFAULT 'exact',
    cost_visibility TEXT NOT NULL DEFAULT 'unknown',
    usage_source TEXT NOT NULL DEFAULT 'local_telemetry',
    cost_source TEXT NOT NULL DEFAULT 'unknown',
    accounting_confidence TEXT NOT NULL DEFAULT 'medium'
)
INDEXES: idx_token_usage_scope

TABLE: tool_embeddings_cache | rows=0
CREATE TABLE tool_embeddings_cache (
    tool_id TEXT PRIMARY KEY,
    embedding BLOB NOT NULL,
    model_name TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (tool_id) REFERENCES tool_registry(tool_id) ON DELETE CASCADE
)
INDEXES: idx_embeddings_model

TABLE: tool_invocations | rows=917
CREATE TABLE tool_invocations (
    invocation_id TEXT PRIMARY KEY,
    project_id TEXT, milestone_id TEXT, task_id TEXT, process_run_id TEXT,
    event_id TEXT,
    tool_id TEXT NOT NULL, status TEXT NOT NULL, purpose TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES execution_events(event_id)
)
INDEXES: idx_tool_invocations_scope

TABLE: tool_registry | rows=0
CREATE TABLE tool_registry (
    tool_id TEXT PRIMARY KEY,
    name TEXT NOT NULL, category TEXT NOT NULL,
    description TEXT, source_url TEXT, install_command TEXT,
    tags TEXT, confidence_score REAL DEFAULT 0.5,
    last_verified_at TEXT, created_at TEXT DEFAULT (datetime('now'))
)
INDEXES: idx_tool_category, idx_tool_tags

TABLE: validation_failures | rows=57
CREATE TABLE validation_failures (
    failure_id TEXT PRIMARY KEY,
    event_id TEXT, event_type TEXT,
    errors JSON NOT NULL,
    attempted_event JSON NOT NULL,
    attempted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
INDEXES: idx_validation_failures_event_type

TABLE: validation_results | rows=0
TABLE: workflow_agent_skill_mappings | rows=0

TABLE: workflow_invocations | rows=2
CREATE TABLE workflow_invocations (
    invocation_id TEXT PRIMARY KEY,
    project_id TEXT, milestone_id TEXT, task_id TEXT, process_run_id TEXT,
    event_id TEXT,
    workflow_id TEXT NOT NULL, status TEXT NOT NULL, purpose TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES execution_events(event_id)
)
INDEXES: idx_workflow_invocations_scope
```

---

### All Views (13)

```sql
-- VIEW: effective_skill_runs
CREATE VIEW effective_skill_runs AS
SELECT
    t.id, t.skill_name, t.invoked_at,
    COALESCE(c.corrected_success, t.success) AS success,
    CASE WHEN c.id IS NOT NULL THEN 'corrected' ELSE 'heuristic' END AS signal_source,
    t.input_tokens, t.output_tokens, t.execution_time_s
FROM raw_skill_telemetry t
LEFT JOIN cor_skill_corrections c ON c.telemetry_id = t.id

-- VIEW: v_active_execution
CREATE VIEW v_active_execution AS
SELECT
    node_id, node_type, title, status, started_at,
    (julianday('now') - julianday(started_at)) * 24 * 60 as runtime_minutes
FROM execution_nodes
WHERE status = 'active'
ORDER BY started_at ASC

-- VIEW: v_blocked_nodes
CREATE VIEW v_blocked_nodes AS
SELECT
    en.node_id, en.node_type, en.title, en.status,
    COUNT(ed.dependency_id) as blocking_count
FROM execution_nodes en
JOIN execution_dependencies ed ON en.node_id = ed.source_node_id
JOIN execution_nodes blocker ON ed.target_node_id = blocker.node_id
WHERE en.status = 'blocked'
  AND blocker.status != 'completed'
  AND ed.dependency_type = 'blocks'
GROUP BY en.node_id
ORDER BY blocking_count DESC

-- VIEW: v_completion_rate
CREATE VIEW v_completion_rate AS
SELECT
    node_type,
    COUNT(*) as total,
    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
    ROUND(100.0 * SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) / COUNT(*), 1) as completion_pct
FROM execution_nodes
GROUP BY node_type

-- VIEW: vw_activity_timeline
-- Replaces former activity_log-based view (rewritten in migration 062)
CREATE VIEW vw_activity_timeline AS
SELECT
    event_id,
    event_type,
    timestamp AS event_timestamp,
    severity,
    json_extract(trace, '$.stream_type') AS stream_type,
    json_extract(trace, '$.stream_id') AS stream_id,
    json_extract(payload, '$.summary') AS summary
FROM canonical_events
ORDER BY timestamp DESC

-- VIEW: vw_approach_patterns
CREATE VIEW vw_approach_patterns AS
SELECT
    skill_id, approach,
    COUNT(*) AS times_tried,
    SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS successes,
    ROUND(CAST(SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS REAL) / COUNT(*) * 100, 1) AS success_pct,
    CAST(AVG(tokens_used) AS INTEGER) AS avg_tokens,
    ROUND(AVG(duration_s), 1) AS avg_duration
FROM raw_approaches
GROUP BY skill_id, approach
HAVING COUNT(*) >= 2

-- VIEW: vw_guardrail_decisions
CREATE VIEW vw_guardrail_decisions AS
SELECT
    decision_id, rule_id,
    action AS decision,
    event_id,
    evaluated_at AS event_timestamp,
    message AS reason
FROM guardrail_decisions
ORDER BY evaluated_at DESC

-- VIEW: vw_hook_performance
CREATE VIEW vw_hook_performance AS
SELECT
    hook_name,
    COUNT(*) AS execution_count,
    AVG(duration_ms) AS avg_duration_ms,
    MAX(duration_ms) AS max_duration_ms,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failure_count
FROM hook_executions
GROUP BY hook_name
ORDER BY avg_duration_ms DESC

-- VIEW: vw_prd_progress
CREATE VIEW vw_prd_progress AS
SELECT
    p.prd_id, p.title, p.status, p.total_tasks, p.completed_tasks,
    ROUND(100.0 * p.completed_tasks / NULLIF(p.total_tasks, 0), 1) AS pct_complete,
    p.created_at, p.approved_at, p.completed_at,
    (SELECT COUNT(*) FROM prd_handoffs h WHERE h.prd_id = p.prd_id) AS handoff_count,
    (SELECT COUNT(*) FROM prd_sessions s WHERE s.prd_id = p.prd_id) AS session_count
FROM prd_documents p

-- VIEW: vw_project_readiness_latest
CREATE VIEW vw_project_readiness_latest AS
SELECT
    pr.project_id, pr.assessment_id,
    pr.readiness_score, pr.confidence AS readiness_confidence,
    pr.status AS readiness_status,
    pr.missing_evidence_json, pr.blocking_factors_json, pr.created_at
FROM project_readiness_scorecards pr
JOIN (
    SELECT project_id, MAX(created_at) AS max_created_at
    FROM project_readiness_scorecards
    GROUP BY project_id
) latest ON pr.project_id = latest.project_id AND pr.created_at = latest.max_created_at

-- VIEW: vw_risk_hotspots
CREATE VIEW vw_risk_hotspots AS
SELECT
    file_path,
    COUNT(*) AS finding_count,
    MAX(severity) AS max_severity,
    GROUP_CONCAT(DISTINCT scan_tool) AS tools
FROM sec_sarif_findings
WHERE status = 'open' AND file_path IS NOT NULL
GROUP BY file_path
HAVING finding_count >= 3
ORDER BY finding_count DESC

-- VIEW: vw_security_summary
-- Unified security view (rewritten in migration 062 to remove activity_log reference)
CREATE VIEW vw_security_summary AS
SELECT
    'telemetry_security' AS source_type,
    finding_id,
    COALESCE(scan_id, category, 'telemetry_security') AS tool,
    severity, file_path, start_line AS line_number, description AS message, status, created_at
FROM security_findings
UNION ALL
SELECT
    'sarif' AS source_type,
    CAST(sarif_finding_id AS TEXT) AS finding_id,
    scan_tool AS tool, severity, file_path, line_number, message, status, created_at
FROM sec_sarif_findings
ORDER BY created_at DESC

-- VIEW: vw_task_details
CREATE VIEW vw_task_details AS
SELECT
    t.task_id, t.task_name, t.description, t.status, t.phase,
    t.prd_id, p.title AS prd_title, p.status AS prd_status,
    t.wave_id, t.depends_on, t.started_at, t.completed_at, t.created_at
FROM prd_tasks t
JOIN prd_documents p ON t.prd_id = p.prd_id
```

**Retired views (dropped permanently in migration 062, not recreated):**
- `vw_graph_edges` — broken since initial publication commit 790965e; no production readers
- `vw_component_stats` — broken since initial publication commit 790965e; no production readers

---

### All Non-Auto Indexes (248 total; representative selection)

Key composite and partial indexes:

```
idx_execution_events_canonical_link: PARTIAL INDEX ON execution_events(_built_from_event_id) WHERE _built_from_event_id IS NOT NULL
idx_execution_events_scope: ON execution_events(project_id, milestone_id, task_id)
idx_execution_events_process: ON execution_events(process_run_id)
idx_token_usage_scope: ON token_usage_records(project_id, milestone_id, task_id, agent_id, skill_id, workflow_id, hook_id, model_id)
idx_security_findings_scope: ON security_findings(project_id, milestone_id, task_id, severity)
idx_security_findings_file: ON security_findings(project_id, file_path, severity)
idx_audit_severity: PARTIAL ON audit_runs(critical_count DESC, high_count DESC) WHERE status = 'completed'
idx_prd_version_records_current: UNIQUE PARTIAL ON prd_version_records — (unique index on current flag)
idx_legacy_event_import_map_target: UNIQUE INDEX ON legacy_canonical_event_import_map
idx_ai_usage_operational_scope: ON ai_usage_operational_records(project_id, milestone_id, task_id, work_order_id, adapter_id)
idx_ai_accounting_profiles_adapter: ON ai_adapter_accounting_profiles(adapter_id, provider, model_id, active)
idx_ds_milestones_project: ON ds_milestones(project_id)
idx_ds_work_orders_project: ON ds_work_orders(project_id)
idx_ds_work_orders_milestone: ON ds_work_orders(milestone_id)
idx_ds_tasks_work_order: ON ds_tasks(work_order_id)
idx_ds_tasks_project: ON ds_tasks(project_id)
idx_canonical_events_timestamp: ON canonical_events(timestamp)
idx_canonical_events_event_type: ON canonical_events(event_type)
idx_ds_documents_source_path: ON ds_documents(source_path)
```

---

## Gap 4: Migration Analysis

**Source directory:** `C:\Users\Dannis Seay\builds\dream-studio-clean\core\event_store\migrations\`
**Migration files found:** 61 `.sql` files
**Migrations applied (_schema_version rows):** 61

---

### Applied Migrations (from _schema_version)

| Version | Applied At |
|---------|-----------|
| 1 | 2026-05-16T21:01:02.848654+00:00 |
| 2 | 2026-05-16T21:01:02.868753+00:00 |
| 3 | 2026-05-16T21:01:02.893666+00:00 |
| 4 | 2026-05-16T21:01:03.238725+00:00 |
| 5 | 2026-05-16T21:01:03.258648+00:00 |
| 6 | 2026-05-16T21:01:03.300404+00:00 |
| 7 | 2026-05-16T21:01:03.388772+00:00 |
| 8 | 2026-05-16T21:01:03.408865+00:00 |
| 9 | 2026-05-16T21:01:03.433653+00:00 |
| 10 | 2026-05-16T21:01:03.438655+00:00 |
| 12 | 2026-05-16T21:01:03.458659+00:00 |
| 13 | 2026-05-16T21:01:03.458659+00:00 |
| 14 | 2026-05-16T21:01:03.465785+00:00 |
| 15 | 2026-05-16T21:01:03.468671+00:00 |
| 16 | 2026-05-16T21:01:03.468671+00:00 |
| 17 | 2026-05-16T21:01:03.468671+00:00 |
| 18 | 2026-05-16T21:01:03.481882+00:00 |
| 19 | 2026-05-16T21:01:03.488652+00:00 |
| 20 | 2026-05-16T21:01:03.503656+00:00 |
| 21 | 2026-05-16T21:01:03.511179+00:00 |
| 22 | 2026-05-16T21:01:03.523559+00:00 |
| 23 | 2026-05-16T21:01:03.529706+00:00 |
| 24 | 2026-05-16T21:01:03.550996+00:00 |
| 25 | 2026-05-16T21:01:03.550996+00:00 |
| 26 | 2026-05-16T21:01:03.550996+00:00 |
| 27 | 2026-05-16T21:01:03.561294+00:00 |
| 28 | 2026-05-16T21:01:03.561294+00:00 |
| 29 | 2026-05-16T21:01:03.568984+00:00 |
| 30 | 2026-05-16T21:01:03.568984+00:00 |
| 31 | 2026-05-16T21:01:03.582652+00:00 |
| 32 | 2026-05-16T21:01:03.582652+00:00 |
| 33 | 2026-05-16T21:01:03.591971+00:00 |
| 34 | 2026-05-16T21:01:03.611371+00:00 |
| 37 | 2026-05-16T21:01:03.638676+00:00 |
| 38 | 2026-05-16T21:01:03.658696+00:00 |
| 39 | 2026-05-16T21:01:03.658696+00:00 |
| 40 | 2026-05-16T21:01:03.678664+00:00 |
| 41 | 2026-05-16T21:01:03.678664+00:00 |
| 42 | 2026-05-16T21:01:03.690083+00:00 |
| 43 | 2026-05-16T21:01:03.721794+00:00 |
| 44 | 2026-05-16T21:01:03.748733+00:00 |
| 45 | 2026-05-16T21:01:03.753503+00:00 |
| 46 | 2026-05-16T21:01:03.768743+00:00 |
| 47 | 2026-05-16T21:01:03.784366+00:00 |
| 48 | 2026-05-16T21:01:03.788647+00:00 |
| 49 | 2026-05-16T21:01:03.798654+00:00 |
| 50 | 2026-05-16T21:01:03.800399+00:00 |
| 51 | 2026-05-16T22:42:30.108572+00:00 |
| 52 | 2026-05-16T22:42:30.118597+00:00 |
| 53 | 2026-05-17T00:40:09.657739+00:00 |
| 54 | 2026-05-17T00:46:33.379367+00:00 |
| 55 | 2026-05-17T12:16:55.093167+00:00 |
| 56 | 2026-05-19T00:42:17.151551+00:00 |
| 57 | 2026-05-19T22:27:54.994882+00:00 |
| 58 | 2026-05-21T20:55:11.307883+00:00 |
| 59 | 2026-05-21T20:57:05.445711+00:00 |
| 60 | 2026-05-21T20:58:35.669542+00:00 |
| 61 | 2026-05-21T23:35:02.897739+00:00 |
| 62 | 2026-05-22T01:49:27.488683+00:00 |
| 63 | 2026-05-22T01:49:27.495737+00:00 |
| 64 | 2026-05-22T02:29:03.504372+00:00 |

**Total applied:** 61 rows. File count: 61 `.sql` files.

---

### Missing Migration Numbers (gaps in the sequence)

The migration files use sequential numbering. The applied sequence jumps at several points.

| Gap | Status |
|-----|--------|
| 011 | No file in migrations directory; not in _schema_version. Missing. |
| 035 | No file in migrations directory; not in _schema_version. Missing. |
| 036 | No file in migrations directory; not in _schema_version. Missing. |

Version numbers 35 and 36 are absent from both the filesystem and the applied record. Version 11 likewise. These are permanent gaps — the runner skips numbers it has no file for.

**Internal header/number mismatches observed:**
- File `020_security_findings.sql` has header `-- Migration 019:` (number mismatch: file=020, header=019)
- File `021_risk_register.sql` has header `-- Migration 020:` (file=021, header=020)
- File `022_workflow_connections.sql` has header `-- Migration 021:` (file=022, header=021)
- File `023_research_connections.sql` has header `-- Migration 022:` (file=023, header=022)
- File `024_learning_connections.sql` has header `-- Migration 023:` (file=024, header=023)
- File `025_audit_tracking.sql` has header `-- Migration 024:` (file=025, header=024)
- File `026_consolidate_databases.sql` has header `-- Migration 021:` (file=026, header=021)
- File `027_guardrail_metadata.sql` has header `-- Migration 022:` (file=027, header=022)
- File `028_create_automation_checkpoints.sql` has header `-- Migration 023:` (file=028, header=023)
- File `029_analytics_views.sql` has no numeric header — header says `Migration: Analytics Views`

These mismatches suggest a renumbering pass occurred after initial file creation (files 020-029 were renumbered, headers not updated). The file names are the authoritative numbers (used by the migration runner).

---

### Migration File Analysis

#### 001_initial.sql
- **Size:** 3,330 bytes
- **Description:** Initial schema (workflow runs, telemetry, analytics)
- **Creates tables:** raw_workflow_runs, raw_workflow_nodes, raw_skill_telemetry, cor_skill_corrections, sum_skill_summary, log_batch_imports, raw_pulse_snapshots, raw_planning_specs, sum_analytics_run, raw_operational_snapshots (10 tables)
- **Creates views:** effective_skill_runs
- **Creates indexes:** none
- **Alters:** none
- **Drops:** none
- **Backfills:** none
- **Data updates:** none
- **Applied:** YES (version 1)

#### 002_approaches.sql
- **Size:** 932 bytes
- **Description:** Approach capture (tracks what works vs fails per skill)
- **Creates tables:** raw_approaches
- **Creates views:** vw_approach_patterns
- **Creates indexes:** none
- **Alters:** none
- **Applied:** YES (version 2)

#### 003_registry.sql
- **Size:** 1,144 bytes
- **Description:** Skill registry (skills, gotchas, workflows, dependencies)
- **Creates tables:** reg_skills, reg_gotchas, reg_workflows, reg_skill_deps
- **Applied:** YES (version 3)

#### 004_operations.sql
- **Size:** 8,015 bytes
- **Description:** Operational tables, indexes, FTS5, column additions
- **Creates tables:** reg_projects, raw_sessions, raw_handoffs, raw_specs, raw_tasks, raw_lessons, raw_sentinels, raw_token_usage
- **Creates indexes:** 31 indexes covering approaches, telemetry, corrections, workflow runs, gotchas, skills, workflows, operational snapshots, pulse, specs, projects, sessions, handoffs, tasks, lessons, sentinels, tokens
- **Alters:** raw_approaches (2 ADD COLUMN), raw_skill_telemetry (2 ADD COLUMN)
- **Applied:** YES (version 4)

#### 005_automation_tables.sql
- **Size:** 1,344 bytes
- **Description:** Create automation tracking tables (long-running script tracking)
- **Creates tables:** automation_log
- **Creates indexes:** idx_automation_log_started_at, idx_automation_log_status
- **Applied:** YES (version 5)

#### 006_alerts.sql
- **Size:** 1,467 bytes
- **Description:** Alert system tables
- **Creates tables:** alert_rules, alert_history
- **Creates indexes:** idx_alert_rules_enabled, idx_alert_history_triggered, idx_alert_history_rule
- **Applied:** YES (version 6)

#### 007_document_system.sql
- **Size:** 7,469 bytes
- **Description:** Document system and analyzed repos registry
- **Creates tables:** ds_documents, reg_analyzed_repos, reg_repo_extractions, reg_repo_research_links
- **Creates indexes:** 17 indexes covering document type/project/skill/session/created/expires/parent, repo framework/trust/language/last_analyzed, extractions (repo/type/document/effectiveness), research (repo/research/relevance)
- **Applied:** YES (version 7)

#### 008_research_and_waves.sql
- **Size:** 5,906 bytes
- **Description:** Research caching and wave execution tracking
- **Creates tables:** raw_research, reg_research_sources, pi_waves, pi_wave_tasks
- **Creates indexes:** idx_research_query_hash, idx_research_expires, idx_research_validation, idx_wave_session, idx_wave_tasks_wave, idx_wave_tasks_status
- **Applied:** YES (version 8)

#### 009_project_intelligence.sql
- **Size:** 9,032 bytes
- **Description:** Project Intelligence Wave 2 - Core Analysis Capabilities
- **Creates tables:** pi_components, pi_dependencies, pi_violations, pi_bugs, pi_improvements, pi_analysis_runs
- **Creates indexes:** 9 indexes on components (project/type), dependencies (project), violations (project/severity), bugs (project/severity), improvements (project), analysis runs (project)
- **Alters:** reg_projects — 10 ADD COLUMN operations
- **Applied:** YES (version 9)

#### 010_workflow_learning.sql
- **Size:** 733 bytes
- **Description:** Workflow Learning System - Project Intelligence Wave 6
- **Creates indexes:** idx_workflows_success_rate, idx_workflows_category_success (plus 2 apparent false positives from regex: `for`)
- **Alters:** reg_workflows — 4 ADD COLUMN operations
- **Applied:** YES (version 10)

**[GAP: 011 — Missing. No file, not applied.]**

#### 012_prd_schema.sql
- **Size:** 6,969 bytes
- **Description:** PRD Schema Refactor (FR-009 from unified-discovery spec)
- **Creates tables:** prd_documents, prd_plans, prd_tasks, prd_sessions, session_tasks, prd_handoffs
- **Creates views:** vw_prd_progress, vw_task_details
- **Creates indexes:** 12 indexes covering prd/plan/task/session/handoff by status/project/created/wave/plan/started
- **Applied:** YES (version 12)

#### 013_discovery_tables.sql
- **Size:** 2,401 bytes
- **Description:** Discovery System Tables — tool registry and research cache
- **Creates tables:** tool_registry, research_cache
- **Creates indexes:** idx_tool_category, idx_tool_tags, idx_research_topic, idx_research_expires
- **Applied:** YES (version 13)

#### 014_graph_views.sql
- **Size:** 1,627 bytes
- **Description:** Graph Analysis Views (FR-001 from unified-discovery spec)
- **Creates views:** vw_graph_edges, vw_component_stats
- **Note:** Both views were dropped permanently in migration 062 (broken since initial commit, no production readers)
- **Applied:** YES (version 14)

#### 015_performance_indexes.sql
- **Size:** 1,201 bytes
- **Description:** Performance Indexes for pi_components and pi_dependencies
- **Creates indexes:** idx_pi_components_project, idx_pi_dependencies_source, idx_pi_dependencies_target
- **Applied:** YES (version 15)

#### 016_tool_embeddings.sql
- **Size:** 1,302 bytes
- **Description:** Tool Embeddings Cache for sentence-transformers semantic search
- **Creates tables:** tool_embeddings_cache
- **Creates indexes:** idx_embeddings_model
- **Applied:** YES (version 16)

#### 017_activity_log.sql
- **Size:** 2,949 bytes
- **Description:** Central Activity Log (Hub Table) — foundational hub for hub-and-spoke architecture
- **Creates tables:** activity_log
- **Creates indexes:** idx_activity_type_time, idx_activity_stream, idx_activity_status_severity, idx_activity_anomaly
- **Note:** activity_log was retired in migrations 062/063. The table no longer exists in the live DB.
- **Applied:** YES (version 17)

#### 018_hook_tracking.sql
- **Size:** 4,276 bytes
- **Description:** Hook Execution Tracking (Spoke Tables) — linked to activity_log hub
- **Creates tables:** hook_executions, hook_findings
- **Creates indexes:** 7 indexes on hook exec (activity/name+status/duration/started) and findings (activity/exec/status+severity)
- **Note:** Tables recreated in migration 062 with activity_id made nullable.
- **Applied:** YES (version 18)

#### 019_update_project_paths.sql
- **Size:** 961 bytes
- **Description:** Update project paths — adds planning_path and sessions_path, updates to relative paths
- **Alters:** reg_projects — 2 ADD COLUMN
- **Data updates:** reg_projects
- **Applied:** YES (version 19)

#### 020_security_findings.sql
- **Size:** 7,495 bytes
- **Description:** Security Findings Tracking (Spoke Tables) — sec_sarif_findings, sec_manual_reviews, sec_cve_matches, sec_hook_checks
- **Header mismatch:** File is 020, header says Migration 019
- **Creates tables:** sec_sarif_findings, sec_manual_reviews, sec_cve_matches, sec_hook_checks
- **Creates indexes:** 14 indexes covering sarif (activity/status/severity/rule+file), reviews (activity/status/risk), cve (activity/status/severity/package), hook checks (activity/exec/result)
- **Note:** Tables recreated in migration 062 with activity_id made nullable.
- **Applied:** YES (version 20)

#### 021_risk_register.sql
- **Size:** 5,232 bytes
- **Description:** Risk Register (Spoke Tables) — risks and mitigations linked to activities/PRDs/tasks/skills
- **Header mismatch:** File is 021, header says Migration 020
- **Creates tables:** risk_register, risk_mitigations
- **Creates indexes:** 8 indexes on risk (score/status+type/prd/task/skill) and mitigations (risk/task/status)
- **Applied:** YES (version 21)

#### 022_workflow_connections.sql
- **Size:** 4,076 bytes
- **Description:** Workflow Connections — FK columns linking workflows to activity_log, PRDs, tasks
- **Header mismatch:** File is 022, header says Migration 021
- **Creates tables:** raw_workflow_runs_temp, raw_workflow_runs, raw_workflow_nodes_temp, raw_workflow_nodes (recreate pattern)
- **Creates indexes:** 6 indexes
- **Alters:** raw_workflow_runs (3 ADD COLUMN), raw_workflow_nodes (1 ADD COLUMN)
- **Drops:** raw_workflow_runs, raw_workflow_runs_temp, raw_workflow_nodes, raw_workflow_nodes_temp
- **Backfills:** raw_workflow_runs, raw_workflow_nodes (INSERT ... SELECT from _temp tables)
- **Applied:** YES (version 22)

#### 023_research_connections.sql
- **Size:** 5,143 bytes
- **Description:** Research Connections — FK columns linking research to activity_log, PRDs, tasks
- **Header mismatch:** File is 023, header says Migration 022
- **Recreate pattern:** research_cache_temp/research_cache, raw_research_temp/raw_research
- **Alters:** research_cache (3 ADD COLUMN), raw_research (3 ADD COLUMN)
- **Drops + Backfills:** both tables recreated via temp copy
- **Applied:** YES (version 23)

#### 024_learning_connections.sql
- **Size:** 3,271 bytes
- **Description:** Learning Connections — FK columns added to raw_lessons
- **Header mismatch:** File is 024, header says Migration 023
- **Creates tables:** temp_fk_constraint (temporary helper)
- **Creates indexes:** 6 indexes on raw_lessons (activity/task/prd/skill combinations)
- **Alters:** raw_lessons — 4 ADD COLUMN
- **Drops:** temp_fk_constraint
- **Applied:** YES (version 24)

#### 025_audit_tracking.sql
- **Size:** 3,331 bytes
- **Description:** Audit Run Tracking
- **Header mismatch:** File is 025, header says Migration 024
- **Creates tables:** audit_runs
- **Creates indexes:** idx_audit_target, idx_audit_type_status, idx_audit_started, idx_audit_severity (partial)
- **Applied:** YES (version 25)

#### 026_consolidate_databases.sql
- **Size:** 5,106 bytes
- **Description:** Consolidate Databases — prepared schema for merging dream-studio.db → studio.db
- **Header mismatch:** File is 026, header says Migration 021 (Track A, Task TA-003)
- **Actual DDL:** Only creates 2 indexes (IF NOT EXISTS) on automation_log — no table creation, no data copy
- **Creates indexes:** idx_automation_log_started_at, idx_automation_log_status (both already exist from migration 005)
- **Note:** The merge itself (data copy) was documented as handled by a separate TA-004 script, not by this migration.
- **Applied:** YES (version 26)
- **Full content:** Pre-merge validation (SELECT statements), index creation for merge performance, post-merge validation templates (commented out), rollback instructions

#### 027_guardrail_metadata.sql
- **Size:** 1,468 bytes
- **Description:** Guardrail metadata tables
- **Header mismatch:** File is 027, header says Migration 022
- **Creates tables:** guardrail_decisions, guardrail_rules_audit
- **Creates indexes:** idx_guardrail_decisions_rule_id, idx_guardrail_decisions_evaluated_at, idx_guardrail_decisions_action, idx_guardrail_rules_audit_rule_id
- **Applied:** YES (version 27)

#### 028_create_automation_checkpoints.sql
- **Size:** 1,067 bytes
- **Description:** Create automation_checkpoints table (fix: migration 021/026 referenced it but it was never created)
- **Header mismatch:** File is 028, header says Migration 023
- **Creates tables:** automation_checkpoints
- **Creates indexes:** idx_checkpoint_run, idx_checkpoint_created, idx_checkpoint_run_created
- **Applied:** YES (version 28)

#### 029_analytics_views.sql
- **Size:** 3,641 bytes
- **Description:** Analytics Views (Track B Phase 2: SQL Views Creation)
- **Creates views:** vw_security_summary, vw_activity_timeline, vw_risk_hotspots, vw_hook_performance, vw_guardrail_decisions
- **Drops views:** All 5 above (drops then recreates — idempotent pattern)
- **Note:** These views were rewritten again in migration 062 to remove activity_log references.
- **Applied:** YES (version 29)

#### 030_adapter_metadata.sql
- **Size:** 1,972 bytes
- **Description:** Adapter Metadata Tables — AI adapter layer execution tracking
- **Creates tables:** adapter_executions
- **Creates indexes:** idx_adapter_executions_type, idx_adapter_executions_time, idx_adapter_executions_perf, idx_adapter_executions_activity
- **Note:** Table recreated in migration 062 with activity_id made nullable.
- **Applied:** YES (version 30)

#### 031_decision_log.sql
- **Size:** 1,442 bytes
- **Description:** Decision log and causal link tables
- **Creates tables:** decision_log, decision_event_link
- **Creates indexes:** 7 indexes (decision type/subsystem/timestamp/confidence; link decision/event/relation)
- **Applied:** YES (version 31)

#### 032_semantic_memory.sql
- **Size:** 1,130 bytes
- **Description:** Semantic memory convergence — Phase 3B schema extension
- **Creates indexes:** idx_memory_provenance, idx_memory_lifecycle
- **Alters:** memory_entries — 8 ADD COLUMN operations (provenance tracking, lifecycle state)
- **Applied:** YES (version 32)

#### 033_memory_fts.sql
- **Size:** 341 bytes
- **Description:** FTS5 retrieval index for memory_entries — standalone FTS5, no content= sync
- **Applied:** YES (version 33)

#### 034_execution_graph.sql
- **Size:** 7,269 bytes
- **Description:** Execution Graph Layer (persistent DAG for project → prd → plan → phase → wave → task)
- **Creates tables:** execution_nodes, execution_dependencies, execution_outputs, execution_event_links
- **Creates views:** v_active_execution, v_blocked_nodes, v_completion_rate
- **Creates indexes:** 13 indexes
- **Applied:** YES (version 34)

**[GAP: 035 — Missing. No file, not applied.]**
**[GAP: 036 — Missing. No file, not applied.]**

#### 037_execution_telemetry_traceability_spine.sql
- **Size:** 14,531 bytes
- **Description:** Execution telemetry traceability spine — local-first execution telemetry, module registry, attribution facts, dashboard attention, authority projection records
- **Creates tables (20):** execution_events, process_runs, telemetry_module_registry, telemetry_entity_registry, agent_invocations, skill_invocations, workflow_invocations, hook_invocations, tool_invocations, token_usage_records, security_findings, decision_records, research_evidence_records, blocker_resolution_records, validation_results, artifact_records, outcome_records, route_decision_records, dashboard_attention_items, authority_projection_records
- **Creates indexes:** 22 indexes (all scope/process/module/entity combinations)
- **Applied:** YES (version 37)
- **Full schema:** Included verbatim above in Gap 7 table section.

#### 038_shared_intelligence_authority.sql
- **Size:** 9,262 bytes
- **Description:** Shared intelligence SQLite authority foundation — artifacts, learning, adapters, model/provider profiles, context packets, normalized adapter results
- **Creates tables (8):** artifact_authority_records, learning_event_records, hardening_candidate_records, adapter_authority_profiles, model_provider_profiles, shared_context_packets, adapter_result_records, capability_route_records
- **Creates indexes:** 7 scope indexes
- **Applied:** YES (version 38)

#### 039_dashboard_authority_reconciliation.sql
- **Size:** 5,515 bytes
- **Description:** Dashboard Authority Reconciliation
- **Creates tables:** raw_sessions (IF NOT EXISTS), alert_rules (IF NOT EXISTS), alert_history (IF NOT EXISTS), dashboard_authority_reconciliation_records, security_findings (IF NOT EXISTS), sec_sarif_findings (IF NOT EXISTS)
- **Creates views:** vw_security_summary (drop then recreate)
- **Creates indexes:** idx_sessions_project, idx_sessions_started, idx_alert_rules_enabled, idx_alert_history_triggered, idx_alert_history_rule, idx_dashboard_authority_reconciliation_scope
- **Alters:** raw_sessions (11 ADD COLUMN), alert_rules (6 ADD COLUMN), alert_history (5 ADD COLUMN)
- **Drops views:** vw_security_summary
- **Applied:** YES (version 39)

#### 040_production_readiness_authority.sql
- **Size:** 6,973 bytes
- **Description:** Production Readiness Authority
- **Creates tables (9):** production_readiness_assessment_runs, production_readiness_control_results, production_readiness_findings, production_readiness_remediation_work_orders, production_readiness_skill_control_mappings, project_readiness_scorecards, project_health_scorecards, release_readiness_records, compliance_review_flags
- **Creates views:** vw_project_readiness_latest (drop then recreate)
- **Creates indexes:** 10 indexes
- **Applied:** YES (version 40)

#### 041_legacy_canonical_event_import_map.sql
- **Size:** 1,719 bytes
- **Description:** Legacy canonical event reconciliation import map — import ledger tracking row-level reconciliation from old backup canonical_events
- **Creates tables:** legacy_canonical_event_import_map
- **Creates indexes:** idx_legacy_event_import_map_target (UNIQUE), idx_legacy_event_import_map_status, idx_legacy_event_import_map_type
- **Applied:** YES (version 41)

#### 042_token_usage_source_refs.sql
- **Size:** 1,000 bytes
- **Description:** Token usage source references — source/evidence provenance for reconciled legacy rows
- **Creates tables:** token_usage_records (IF NOT EXISTS — safe guard)
- **Alters:** token_usage_records — 2 ADD COLUMN (source_refs_json, evidence_refs_json)
- **Applied:** YES (version 42)

#### 043_ai_usage_accounting.sql
- **Size:** 6,476 bytes
- **Description:** AI adapter usage accounting and operational value telemetry
- **Creates tables:** token_usage_records (IF NOT EXISTS), ai_adapter_accounting_profiles, ai_usage_operational_records
- **Creates indexes:** idx_ai_accounting_profiles_adapter, idx_ai_usage_operational_scope, idx_ai_usage_operational_process
- **Alters:** token_usage_records — 7 ADD COLUMN (adapter_id, billing_mode, token_visibility, cost_visibility, usage_source, cost_source, accounting_confidence)
- **Applied:** YES (version 43)

#### 044_career_capability_agent_github_authority.sql
- **Size:** 19,872 bytes
- **Description:** Career Ops, Capability Center, scoped agents, and GitHub repo intake authority — additive only, does not enable capabilities by default
- **Creates tables (28):** career_profiles, career_profile_fields, career_role_targets, career_resume_versions, career_cover_letter_versions, career_portfolio_artifacts, career_case_studies, career_job_opportunities, career_applications, career_application_events, career_application_field_mappings, career_browser_automation_runs, career_interview_story_bank, career_evidence_refs, career_scorecards, capability_center_records, agent_registry_records, agent_context_scope_policies, workflow_agent_skill_mappings, agent_result_records, github_repo_evaluations, github_repo_license_findings, github_repo_security_findings, github_repo_dependency_findings, github_repo_integration_candidates, github_repo_pattern_references, github_repo_adoption_decisions, github_repo_attribution_records
- **Creates indexes:** 5 indexes
- **Applied:** YES (version 44)

#### 045_task_attribution_authority.sql
- **Size:** 3,638 bytes
- **Description:** Task Attribution And Execution Outcome Authority
- **Creates tables:** task_attribution_records
- **Creates indexes:** 5 indexes (project/work_order/process/adapter/outcome)
- **Applied:** YES (version 45)

#### 046_platform_hardening_authority.sql
- **Size:** 6,120 bytes
- **Description:** Dream Studio platform hardening authority records — additive only, policy-backed
- **Creates tables (8):** skill_evaluation_runs, policy_decision_records, connector_ingestion_runs, privacy_redaction_export_records, local_watch_schedule_records, team_rollup_records, installer_distribution_checks, demo_case_study_packets
- **Creates indexes:** 5 indexes
- **Applied:** YES (version 46)

#### 047_prd_lifecycle_authority.sql
- **Size:** 12,981 bytes
- **Description:** PRD Lifecycle And Route Authority
- **Creates tables (9):** project_intake_records, project_intake_questions, project_assumption_records, prd_version_records, project_milestone_records, project_work_order_authority_records, project_change_order_records, prd_amendment_records, prd_route_reconciliation_records
- **Creates indexes:** 10 indexes
- **Applied:** YES (version 47)

#### 048_project_spine.sql
- **Size:** 2,941 bytes
- **Description:** Project Spine — ds_projects / ds_milestones / ds_work_orders / ds_tasks (Slice 4 Workstream 3, 2026-05-16)
- **Creates tables (4):** ds_projects, ds_milestones, ds_work_orders, ds_tasks
- **Creates indexes:** idx_ds_milestones_project, idx_ds_work_orders_project, idx_ds_work_orders_milestone, idx_ds_tasks_work_order, idx_ds_tasks_project
- **Applied:** YES (version 48)
- **Full schema:** Included verbatim above in Gap 7.

#### 049_work_order_type.sql
- **Size:** 1,636 bytes
- **Description:** Work order type routing key for the SDLC pipeline (Slice 5b/5e)
- **Creates tables:** ds_work_order_types
- **Alters:** ds_work_orders — ADD COLUMN work_order_type
- **Applied:** YES (version 49)

#### 050_documents_source_path.sql
- **Size:** 405 bytes
- **Description:** Add source_path to ds_documents for idempotent memory ingest (Slice 5d)
- **Creates indexes:** idx_ds_documents_source_path
- **Alters:** ds_documents — ADD COLUMN source_path
- **Applied:** YES (version 50)

#### 051_work_order_block.sql
- **Size:** 611 bytes
- **Description:** Add block_reason column and extend ds_work_orders.status to include 'blocked'
- **Alters:** ds_work_orders — ADD COLUMN block_reason
- **Data updates:** sqlite_master (writable_schema trick to patch CHECK constraint in-place)
- **Applied:** YES (version 51)

#### 052_invocation_mode.sql
- **Size:** 501 bytes
- **Description:** Add invocation_mode column to canonical_events — canonical_events is created lazily by the ingestor; migration guards for safe replay
- **Alters:** canonical_events — ADD COLUMN invocation_mode
- **Applied:** YES (version 52)

#### 053_design_brief.sql
- **Size:** 870 bytes
- **Description:** Design brief persistence for UI work orders (Slice 7a)
- **Creates tables:** ds_design_briefs
- **Creates indexes:** idx_ds_design_briefs_project
- **Applied:** YES (version 53)

#### 054_ui_gate_update.sql
- **Size:** 314 bytes
- **Description:** Add anti_slop_passed to post_build_gate for UI work order types (Slice 7c)
- **Data updates:** ds_work_order_types
- **Applied:** YES (version 54)

#### 055_technology_signals.sql
- **Size:** 445 bytes
- **Description:** Technology signals table for session intelligence harvest (Slice 8c) — stores file extension counts derived from Claude Code session history; privacy: extension counts only
- **Creates tables:** ds_technology_signals
- **Applied:** YES (version 55)

#### 056_milestone_order_index.sql
- **Size:** 530 bytes
- **Description:** Backfill order_index for Dream Command milestones — uses rowid as insertion order proxy
- **Alters:** ds_milestones — ADD COLUMN order_index
- **Data updates:** ds_milestones
- **Applied:** YES (version 56)

#### 057_work_order_type_extensions.sql
- **Size:** 1,231 bytes
- **Description:** Extend ds_work_order_types with workflow routing and gate resolution (Slice 8c)
- **Alters:** ds_work_order_types — 4 ADD COLUMN (workflow_template, precondition_skill, task_generator, resolution_instructions)
- **Data updates:** ds_work_order_types — 4 UPDATE statements
- **Applied:** YES (version 57)

#### 058_ta0b_domain_field_validation.sql
- **Size:** 725 bytes
- **Description:** TA0b — Domain field validation requirement. No schema change. Documents the requirement that canonical event trace JSON must include a `domain` field. Registers version for traceability.
- **Creates tables:** none
- **Creates indexes:** none
- **Alters:** none
- **Data updates:** none
- **Applied:** YES (version 58)

#### 059_ta0b_execution_events_projection_link.sql
- **Size:** 559 bytes
- **Description:** TA0b — Add projection link column to execution_events so each row can be traced back to the canonical_events record that produced it
- **Creates indexes:** idx_execution_events_canonical_link (partial, WHERE _built_from_event_id IS NOT NULL)
- **Alters:** execution_events — ADD COLUMN _built_from_event_id
- **Applied:** YES (version 59)

#### 060_ta0b_backfill_execution_events_from_canonical.sql
- **Size:** 4,140 bytes
- **Description:** TA0b — Backfill domain field and execution_events projection
  - Part 1a: UPDATE canonical_events SET trace = json_set(..., '$.domain', 'telemetry') for telemetry event types missing domain
  - Part 1b: UPDATE canonical_events SET trace = json_set(..., '$.domain', 'sdlc') for SDLC event types missing domain
  - Part 2: INSERT OR IGNORE INTO execution_events from canonical_events for execution.started/completed/failed events not yet projected
- **Data updates:** canonical_events (2 UPDATE statements)
- **Backfills:** execution_events (INSERT ... SELECT from canonical_events)
- **Applied:** YES (version 60)

#### 061_backfill_sdlc_creation_events.sql
- **Size:** 2,627 bytes
- **Description:** TA0: Backfill SDLC entity creation events — inserts synthetic project.created, milestone.created, work_order.created events into canonical_events using deterministic prefixed event_ids for idempotency
- **Backfills:** canonical_events — 3 INSERT OR IGNORE ... SELECT FROM (ds_projects, ds_milestones, ds_work_orders)
- **Applied:** YES (version 61)

#### 062_nullify_activity_id_backfill_and_replace_views.sql
- **Size:** 20,625 bytes
- **Description:** TA0c — Retire activity_log: nullify activity_id FKs, backfill activity_log → canonical_events, replace all views that referenced activity_log
  - Part 0: Drop leftover _new temp tables (idempotency)
  - Part 1: Drop ALL 15 views before any table recreation (SQLite limitation — broken view aborts RENAME)
  - Part 2: Recreate 7 tables with activity_id made nullable (hook_executions, hook_findings, sec_sarif_findings, sec_manual_reviews, sec_cve_matches, sec_hook_checks, adapter_executions) — PRAGMA foreign_keys OFF/ON wraps the recreations
  - Part 3: Recreate 13 valid views (vw_graph_edges and vw_component_stats permanently retired)
  - Part 4: INSERT OR IGNORE backfill of 159 activity_log rows → canonical_events
- **Creates tables (7):** _new variants of recreated tables
- **Creates views (13):** effective_skill_runs, v_active_execution, v_blocked_nodes, v_completion_rate, vw_activity_timeline, vw_approach_patterns, vw_guardrail_decisions, vw_hook_performance, vw_prd_progress, vw_project_readiness_latest, vw_risk_hotspots, vw_security_summary, vw_task_details
- **Creates indexes (24):** full recreation of all indexes for the 7 rebuilt tables
- **Alters (RENAME TO):** 7 tables renamed from _new to final names
- **Drops tables (14):** 7 _new temp + 7 original tables
- **Drops views (15+):** all live views before recreation
- **Backfills (7):** INSERT ... SELECT from _new tables
- **Applied:** YES (version 62)

#### 063_drop_activity_log.sql
- **Size:** 661 bytes
- **Description:** Drop activity_log table (prerequisite: migration 062 must have run)
- **Drops tables:** activity_log
- **Drops indexes:** idx_activity_type_time, idx_activity_stream, idx_activity_status_severity, idx_activity_anomaly
- **Applied:** YES (version 63)
- **Note:** audit_runs still has a declared FK to activity_log (ON DELETE SET NULL). The table no longer exists. SQLite does not enforce FK existence at schema definition time, so this is a dangling FK declaration.

#### 064_backfill_task_creation_events.sql
- **Size:** 1,451 bytes
- **Description:** TA1: Backfill task.created events — inserts synthetic task.created events into canonical_events for the 9 task records that predate event emission
- **Backfills:** canonical_events — INSERT OR IGNORE ... SELECT FROM ds_tasks
- **Applied:** YES (version 64)

---

### Summary Table — All 61 Migration Files

| File | Size | Applied | DDL Category |
|------|------|---------|-------------|
| 001_initial.sql | 3,330 | YES (v1) | CREATE TABLE ×10, CREATE VIEW ×1 |
| 002_approaches.sql | 932 | YES (v2) | CREATE TABLE ×1, CREATE VIEW ×1 |
| 003_registry.sql | 1,144 | YES (v3) | CREATE TABLE ×4 |
| 004_operations.sql | 8,015 | YES (v4) | CREATE TABLE ×8, CREATE INDEX ×31, ALTER ×4 |
| 005_automation_tables.sql | 1,344 | YES (v5) | CREATE TABLE ×1, CREATE INDEX ×2 |
| 006_alerts.sql | 1,467 | YES (v6) | CREATE TABLE ×2, CREATE INDEX ×3 |
| 007_document_system.sql | 7,469 | YES (v7) | CREATE TABLE ×4, CREATE INDEX ×17 |
| 008_research_and_waves.sql | 5,906 | YES (v8) | CREATE TABLE ×4, CREATE INDEX ×6 |
| 009_project_intelligence.sql | 9,032 | YES (v9) | CREATE TABLE ×6, CREATE INDEX ×9, ALTER ×10 |
| 010_workflow_learning.sql | 733 | YES (v10) | CREATE INDEX ×2, ALTER ×4 |
| [011 — MISSING] | — | NO | — |
| 012_prd_schema.sql | 6,969 | YES (v12) | CREATE TABLE ×6, CREATE VIEW ×2, CREATE INDEX ×12 |
| 013_discovery_tables.sql | 2,401 | YES (v13) | CREATE TABLE ×2, CREATE INDEX ×4 |
| 014_graph_views.sql | 1,627 | YES (v14) | CREATE VIEW ×2 (both retired in 062) |
| 015_performance_indexes.sql | 1,201 | YES (v15) | CREATE INDEX ×3 |
| 016_tool_embeddings.sql | 1,302 | YES (v16) | CREATE TABLE ×1, CREATE INDEX ×1 |
| 017_activity_log.sql | 2,949 | YES (v17) | CREATE TABLE ×1, CREATE INDEX ×4 (table dropped in 063) |
| 018_hook_tracking.sql | 4,276 | YES (v18) | CREATE TABLE ×2, CREATE INDEX ×7 (recreated in 062) |
| 019_update_project_paths.sql | 961 | YES (v19) | ALTER ×2, UPDATE ×1 |
| 020_security_findings.sql | 7,495 | YES (v20) | CREATE TABLE ×4, CREATE INDEX ×14 (recreated in 062) |
| 021_risk_register.sql | 5,232 | YES (v21) | CREATE TABLE ×2, CREATE INDEX ×8 |
| 022_workflow_connections.sql | 4,076 | YES (v22) | CREATE TABLE ×4 (temp+final), CREATE INDEX ×6, ALTER ×4, DROP ×4, BACKFILL ×2 |
| 023_research_connections.sql | 5,143 | YES (v23) | CREATE TABLE ×4 (temp+final), CREATE INDEX ×6, ALTER ×6, DROP ×4, BACKFILL ×2 |
| 024_learning_connections.sql | 3,271 | YES (v24) | CREATE TABLE ×1 (temp), CREATE INDEX ×6, ALTER ×4, DROP ×1 |
| 025_audit_tracking.sql | 3,331 | YES (v25) | CREATE TABLE ×1, CREATE INDEX ×4 |
| 026_consolidate_databases.sql | 5,106 | YES (v26) | CREATE INDEX ×2 (IF NOT EXISTS), SELECT statements only |
| 027_guardrail_metadata.sql | 1,468 | YES (v27) | CREATE TABLE ×2, CREATE INDEX ×4 |
| 028_create_automation_checkpoints.sql | 1,067 | YES (v28) | CREATE TABLE ×1, CREATE INDEX ×3 |
| 029_analytics_views.sql | 3,641 | YES (v29) | CREATE VIEW ×5, DROP VIEW ×5 (idempotent) |
| 030_adapter_metadata.sql | 1,972 | YES (v30) | CREATE TABLE ×1, CREATE INDEX ×4 (recreated in 062) |
| 031_decision_log.sql | 1,442 | YES (v31) | CREATE TABLE ×2, CREATE INDEX ×7 |
| 032_semantic_memory.sql | 1,130 | YES (v32) | CREATE INDEX ×2, ALTER ×8 |
| 033_memory_fts.sql | 341 | YES (v33) | CREATE VIRTUAL TABLE |
| 034_execution_graph.sql | 7,269 | YES (v34) | CREATE TABLE ×4, CREATE VIEW ×3, CREATE INDEX ×13 |
| [035 — MISSING] | — | NO | — |
| [036 — MISSING] | — | NO | — |
| 037_execution_telemetry_traceability_spine.sql | 14,531 | YES (v37) | CREATE TABLE ×20, CREATE INDEX ×22 |
| 038_shared_intelligence_authority.sql | 9,262 | YES (v38) | CREATE TABLE ×8, CREATE INDEX ×7 |
| 039_dashboard_authority_reconciliation.sql | 5,515 | YES (v39) | CREATE TABLE ×6 (IF NOT EXISTS), CREATE VIEW ×1, CREATE INDEX ×6, ALTER ×22, DROP VIEW ×1 |
| 040_production_readiness_authority.sql | 6,973 | YES (v40) | CREATE TABLE ×9, CREATE VIEW ×1, CREATE INDEX ×10, DROP VIEW ×1 |
| 041_legacy_canonical_event_import_map.sql | 1,719 | YES (v41) | CREATE TABLE ×1, CREATE INDEX ×3 (1 UNIQUE) |
| 042_token_usage_source_refs.sql | 1,000 | YES (v42) | CREATE TABLE IF NOT EXISTS (guard), ALTER ×2 |
| 043_ai_usage_accounting.sql | 6,476 | YES (v43) | CREATE TABLE ×3 (1 IF NOT EXISTS guard), CREATE INDEX ×3, ALTER ×7 |
| 044_career_capability_agent_github_authority.sql | 19,872 | YES (v44) | CREATE TABLE ×28, CREATE INDEX ×5 |
| 045_task_attribution_authority.sql | 3,638 | YES (v45) | CREATE TABLE ×1, CREATE INDEX ×5 |
| 046_platform_hardening_authority.sql | 6,120 | YES (v46) | CREATE TABLE ×8, CREATE INDEX ×5 |
| 047_prd_lifecycle_authority.sql | 12,981 | YES (v47) | CREATE TABLE ×9, CREATE INDEX ×10 |
| 048_project_spine.sql | 2,941 | YES (v48) | CREATE TABLE ×4, CREATE INDEX ×5 |
| 049_work_order_type.sql | 1,636 | YES (v49) | CREATE TABLE ×1, ALTER ×1 |
| 050_documents_source_path.sql | 405 | YES (v50) | CREATE INDEX ×1, ALTER ×1 |
| 051_work_order_block.sql | 611 | YES (v51) | ALTER ×1, UPDATE sqlite_master (writable_schema) |
| 052_invocation_mode.sql | 501 | YES (v52) | ALTER ×1 (canonical_events) |
| 053_design_brief.sql | 870 | YES (v53) | CREATE TABLE ×1, CREATE INDEX ×1 |
| 054_ui_gate_update.sql | 314 | YES (v54) | UPDATE ×1 (ds_work_order_types) |
| 055_technology_signals.sql | 445 | YES (v55) | CREATE TABLE ×1 |
| 056_milestone_order_index.sql | 530 | YES (v56) | ALTER ×1, UPDATE ×1 |
| 057_work_order_type_extensions.sql | 1,231 | YES (v57) | ALTER ×4, UPDATE ×4 |
| 058_ta0b_domain_field_validation.sql | 725 | YES (v58) | Documentation only — no DDL |
| 059_ta0b_execution_events_projection_link.sql | 559 | YES (v59) | CREATE INDEX ×1 (partial), ALTER ×1 |
| 060_ta0b_backfill_execution_events_from_canonical.sql | 4,140 | YES (v60) | UPDATE ×2, INSERT OR IGNORE ×1 (backfill) |
| 061_backfill_sdlc_creation_events.sql | 2,627 | YES (v61) | INSERT OR IGNORE ×3 (backfill from ds_*) |
| 062_nullify_activity_id_backfill_and_replace_views.sql | 20,625 | YES (v62) | DROP VIEW ×15, DROP TABLE ×14, CREATE TABLE ×7, RENAME ×7, CREATE INDEX ×24, CREATE VIEW ×13, INSERT OR IGNORE ×7 (backfill), INSERT OR IGNORE ×1 (activity_log → canonical_events) |
| 063_drop_activity_log.sql | 661 | YES (v63) | DROP TABLE ×1, DROP INDEX ×4 |
| 064_backfill_task_creation_events.sql | 1,451 | YES (v64) | INSERT OR IGNORE ×1 (task.created events → canonical_events) |

---

### Notable Observations (structural, no judgment)

1. **Three permanent sequence gaps:** Numbers 011, 035, 036 are absent from both the migrations directory and _schema_version. The runner skips numbers with no corresponding file.

2. **Header/file number mismatches in files 020–029:** Files were renumbered (to insert migration 017 and 018) after initial creation. Comment headers still reference old numbers. The file names are authoritative for the runner.

3. **Largest migrations by size:** 044 (19,872 bytes — career+agent+github), 062 (20,625 bytes — activity_log retirement), 047 (12,981 bytes — PRD lifecycle), 037 (14,531 bytes — telemetry spine).

4. **activity_log lifecycle:** Created in 017, populated by spokes 018–030, backfilled to canonical_events in 062, dropped in 063. audit_runs retains a dangling FK declaration to the now-dropped table.

5. **Two retired views:** vw_graph_edges and vw_component_stats were created in migration 014 but declared broken since initial publication (commit 790965e). Permanently dropped in migration 062, not recreated.

6. **Data-only migrations:** 058 registers a documentation requirement with no DDL. 060, 061, 064 are pure backfill operations on canonical_events.

7. **writable_schema usage:** Migration 051 uses PRAGMA writable_schema to patch a CHECK constraint in sqlite_master in-place without table recreation.

8. **Applied timestamp clustering:** Migrations 1–50 all applied at 2026-05-16T21:01 (single session, fresh DB init). Migrations 51–52 applied same day at 22:42. Migrations 53–57 applied across 2026-05-17 to 2026-05-19. Migrations 58–64 applied 2026-05-21 to 2026-05-22.

---

*Raw schema dump:* `_db_schema_raw.txt` (4,309 lines, UTF-8)
*Raw migration parse:* `_migrations_raw.txt` (314 lines, UTF-8)

---

# Gap 5: Discovered Subsystems — Deep Dive

Phase 0c mechanical inventory. Pure observation — no judgment words.
Generated: 2026-05-22

---

## guardrails/

**Description:** Deterministic policy enforcement layer. Loads YAML rule files from `guardrails/rules/`, evaluates them against `activity_log` trigger conditions, and returns allow/block/require_approval decisions. Logs decisions to `guardrail_decisions`. Also contains three pattern-based scanner stubs (giskard, llm_guard, rebuff) and a content-level enforcement module (`enforcement.py`) that detects placeholder text and policy violations in response text via pure string functions (no DB, no IO).

**File listing:**
| File | Size |
|------|------|
| guardrails/__init__.py | 0 |
| guardrails/enforcement.py | 3,279 |
| guardrails/evaluator.py | 12,166 |
| guardrails/loader.py | 3,668 |
| guardrails/models.py | 3,320 |
| guardrails/rules/quality.yaml | 2,393 |
| guardrails/rules/security.yaml | 2,148 |
| guardrails/scanners/__init__.py | 0 |
| guardrails/scanners/giskard_scanner.py | 17,790 |
| guardrails/scanners/llm_guard_scorer.py | 15,324 |
| guardrails/scanners/rebuff_validator.py | 16,020 |

**Entry points:** `guardrails/evaluator.py` has `def main()` (CLI entrypoint, called as script with `--event-id` arg); exit codes 0=allow, 1=block, 2=require_approval.

**DB reads:** `activity_log` (query trigger conditions)
**DB writes:** `guardrail_decisions`

**Events emitted:** `EventType.GUARDRAIL_DECISION`

**Referenced by:**
- `hooks/on-commit.py` (imports `guardrails.evaluator.evaluate`)
- `runtime/hooks/meta/on-prompt-validate.py`
- `core/storage/document_store.py`
- `guardrails/loader.py` (self)
- Test files: `tests/evals/test_guardrail_enforcement_evals.py`, `tests/unit/test_governance_privacy_boundaries.py`, `tests/unit/test_rebuff_validator.py`, `tests/unit/test_llm_guard_scorer.py`, `tests/unit/test_giskard_scanner.py`

**Tests:**
- `tests/evals/test_guardrail_enforcement_evals.py` (1 file, under evals/)
- Unit tests scattered: test_rebuff_validator, test_llm_guard_scorer, test_giskard_scanner, test_governance_privacy_boundaries
- No dedicated `tests/unit/guardrails/` directory

**Notes on scanners:** All three scanner modules (`giskard_scanner.py`, `llm_guard_scorer.py`, `rebuff_validator.py`) are stub implementations with pattern-based detection. Giskard stub comment notes the real library requires Python <3.12; current runtime is Python 3.12.

---

## emitters/

**Description:** Claude Code hook event emitter layer. Translates raw Claude Code hook payloads (UserPromptSubmit, Stop, PostToolUse, PostCompact) into `CanonicalEventEnvelope` objects and writes them to the spool directory via `emitters/shared/spool_writer.py`. Two sub-packages: `claude_code/` (hook-specific normalizers + enforcement check) and `shared/` (generic spool write helper).

**File listing:**
| File | Size |
|------|------|
| emitters/__init__.py | 0 |
| emitters/claude_code/__init__.py | 0 |
| emitters/claude_code/emitter.py | 4,770 |
| emitters/claude_code/project.py | 2,229 |
| emitters/claude_code/run.py | 5,377 |
| emitters/claude_code/session.py | 876 |
| emitters/shared/__init__.py | 0 |
| emitters/shared/spool_writer.py | 616 |

**Entry points:**
- `emitters/claude_code/run.py` — called as `__main__` by `hooks/hooks.json` commands; dispatches by argv[1] (event name). Also handles enforcement check for missing active work order.

**DB reads:** `ds_projects` (reads active project ID via flat `.dream-studio-project` marker file, not DB direct)
**DB writes:** None directly (all output goes to spool filesystem)

**Events emitted:**
- `EventType.PROMPT_LIFECYCLE_SUBMITTED`
- `EventType.TOKEN_CONSUMPTION_RECORDED`
- `EventType.TOOL_EXECUTION_COMPLETED`
- `EventType.CONTEXT_THRESHOLD_CROSSED`

**Referenced by:** 38 files including `core/telemetry/token_capture.py`, `core/skills/invocation.py`, `projections/scoring/engine.py`, `projections/parsers/sarif_parser.py`, `guardrails/evaluator.py`, `control/analysis/engine.py`, `control/execution/workflow/wave_executor.py`, `control/execution/workflow/wave_executor_enhanced.py`, `control/session/manager.py`, `control/analysis/repo_analyzer.py`, various core/* and tests/* files.

**Tests:**
- `tests/unit/emitters/` — 4 files
- `tests/integration/emitters/` — 2 files

**Notes:** `run.py` is explicitly non-fatal (always exits 0); spool emission must not interrupt the hook chain. Windows-specific SIGINT handler is in `spool/ingestor.py`, not here.

---

## spool/

**Description:** Event spool pipeline — filesystem-based staging queue for canonical events before SQLite ingest. Events are written as JSON files under `~/.dream-studio/events/` (or `$DS_SPOOL_ROOT`) into four state directories: `spool/`, `processing/`, `processed/`, `failed/`. `ingestor.py` moves events through the pipeline and writes to SQLite. `session_harvester.py` extracts derived metadata from Claude Code JSONL session files.

**File listing:**
| File | Size |
|------|------|
| spool/__init__.py | 0 |
| spool/config.py | 243 |
| spool/ingestor.py | 10,088 |
| spool/session_harvester.py | 17,928 |
| spool/states.py | 792 |
| spool/writer.py | 1,076 |

**Entry points:** No `__main__.py`. `ingestor.py` has `def ingest_pending()` called from CLI (`interfaces/cli/ds_spool.py`). `session_harvester.py` has standalone `def main()`.

**DB reads:** `ds_documents`, `reg_gotchas`, `projections` (via ingestor context checks)
**DB writes:** `canonical_events`, `ds_documents`, `ds_technology_signals`, `raw_approaches`, `reg_gotchas`

**Events emitted:** None (spool is the transport layer, not an emitter)

**Referenced by:** 41 files including `emitters/claude_code/run.py`, `emitters/shared/spool_writer.py`, `emitters/claude_code/session.py`, `core/work_orders/mutations.py`, `core/projects/mutations.py`, `core/skills/invocation.py`, `core/work_orders/start.py`, `core/work_orders/close.py`, `control/execution/workflow/runner.py`, `scripts/requeue_failed.py`, `interfaces/cli/ds_spool.py`, and many test files.

**Tests:**
- `tests/unit/spool/` — 6 files (test_ingestor, test_states, test_writer, test_ingest_pending, test_session_cleanup, and more)
- `tests/integration/spool/` — 9 files (test_minimal_pair, test_spool_end_to_end, test_ingestor_sqlite, test_decoupled_pipeline, test_cli_event_chain, test_ta6_e2e_attribution, and more)

**Notes:**
- `spool/writer.py` defensively injects `schema_version: 1` if missing; this was added as A0 fix.
- `spool/ingestor.py` contains Windows-specific `SetConsoleCtrlHandler` to absorb phantom SIGINT during filesystem + SQLite operations.
- `session_harvester.py` privacy guarantee: raw prompts/responses never stored; only derived metadata (error patterns, skill usage, timestamps, tool types, tech signals).
- `spool/config.py`: spool root = `$DS_SPOOL_ROOT` or `~/.dream-studio/events/`.

---

## integrations/

**Description:** Integration management layer — detects, compiles, installs, and health-checks Dream Studio integrations into target AI tools (currently only Claude Code). Three sub-packages: `compiler/` (reads `canonical/` + `packs.yaml` to produce a deterministic install plan), `installer/` (applies file operations to user/project scope), `targets/` (target-specific settings merge logic). Top-level modules: `detector.py`, `health.py` (nine-state machine), `manifest.py`.

**File listing:**
| File | Size |
|------|------|
| integrations/__init__.py | 0 |
| integrations/compiler/__init__.py | 0 |
| integrations/compiler/claude_code.py | 11,251 |
| integrations/detector.py | 1,382 |
| integrations/health.py | 5,602 |
| integrations/installer/__init__.py | 0 |
| integrations/installer/base.py | 1,808 |
| integrations/installer/claude_code.py | 34,269 |
| integrations/installer/file_ops.py | 1,591 |
| integrations/manifest.py | 2,734 |
| integrations/targets/__init__.py | 0 |
| integrations/targets/claude_code/__init__.py | 0 |
| integrations/targets/claude_code/hooks_template.json | 1,657 |
| integrations/targets/claude_code/settings_merge.py | 9,055 |

**Entry points:** No `__main__.py`. Called via `interfaces/cli/ds.py` through `ds integrate install/status/doctor` commands.

**DB reads:** `ds_projects` (project identity lookup)
**DB writes:** None directly (writes to filesystem: `settings.json`, `SKILL.md`, hooks)

**Events emitted:** None (integration events emitted via spool from health state transitions; `integrations/health.py` has nine-state machine: `NOT_DETECTED` → `DETECTED_NOT_INTEGRATED` → `PLAN_AVAILABLE` → `INSTALLED_UNVERIFIED` → `INSTALLED_VERIFIED` → `INSTALLED_DRIFTED` → `EVENTS_EMITTING` → `INGEST_VERIFIED` → `BROKEN`)

**Referenced by:** 27 files including `interfaces/cli/ds.py`, `core/health/doctor.py`, `core/shared_intelligence/integration_alignment.py`, `core/shared_intelligence/integration_health.py`, and tests in `tests/unit/integrations/` (12 files) and `tests/integration/integrations/` (5 files).

**Tests:**
- `tests/unit/integrations/` — 12 files (test_installer_complete, test_settings_merge, test_health, test_installer_claude_code, test_integration_agent_contract, test_manifest, test_compiler_claude_code, test_detector, test_file_ops, test_installer_base, and more)
- `tests/integration/integrations/` — 5 files (test_install_chain_complete, test_doctor, test_installer_dry_run, test_status, and more)

---

## control/

**Description:** Control plane — mutation and orchestration. Seven sub-packages: `analysis/` (5-phase project intelligence pipeline), `context/` (context compilation, handoff writing, pack loading, repo context, team context, context7 manager), `execution/` (workflow runner, wave executor, model selector, dispatch helpers), `research/` (web research, tool search with TF-IDF/embeddings, memory), `review/` (session retrospective engine), `session/` (session cache, manager, JSONL parser), `skills/` (skill router, calibration, loader, metrics).

**File listing (selected — 87 .py files total, 37 subdirectories):**

| Sub-package | Key files | Total size |
|-------------|-----------|------------|
| control/analysis/ | engine.py (22,773), repo_analyzer.py (25,392), audit.py (16,521), bugs.py (13,158), discovery.py (14,192), synthesis.py (9,563), findings_summarizer.py (7,796), quality_scoring.py (7,960), research.py (7,283), security_patterns.py (2,941) + stacks/ (detector, nextjs, astro, python_generic, base) | ~157 KB |
| control/context/ | compiler.py (17,527), context7_manager.py (14,713), handoff.py (11,887), repo.py (13,001), monitor.py (8,038), team.py (6,574), pack.py (973) | ~73 KB |
| control/execution/ | workflow/runner.py (20,797), workflow/state.py (19,860), workflow/wave_executor_enhanced.py (14,914), workflow/wave_executor.py (13,568), workflow/engine.py (13,373), workflow/validate.py (9,816), workflow/learning.py (9,201), workflow/cost.py (6,482), workflow/tracking.py (2,435), workflow/registry.py (3,760), models/selector.py (12,245), dispatch_helpers.py (1,088), dispatch_tracking.py (2,547) | ~130 KB |
| control/research/ | tools.py (40,552), web.py (22,341), engine.py (18,179), memory.py (12,433), methods.py (6,205) | ~100 KB |
| control/review/ | engine.py (9,048) | ~9 KB |
| control/session/ | parser.py (18,096), manager.py (5,694), cache.py (4,129) | ~28 KB |
| control/skills/ | router.py (15,950), completion.py (11,339), calibration.py (5,415), loader.py (3,316), metrics.py (3,226) | ~39 KB |

**Entry points:**
- `control/skills/router.py` — `def main()` (CLI: progressive disclosure gate check)
- `control/context/compiler.py` — `def main()` + module API `compile_context(skill, pack, ...)`
- `control/analysis/engine.py` — orchestrates 5-phase pipeline (no standalone `main()`)

**DB reads (significant):** `activity_log`, `ds_documents`, `memory_fts`, `memory_meta`, `pi_improvements`, `pi_violations`, `pi_wave_tasks`, `pi_waves`, `pi_analysis_runs`, `pi_bugs`, `raw_research`, `raw_sessions`, `raw_skill_telemetry`, `reg_analyzed_repos`, `reg_projects`, `reg_workflows`, `research_cache`, `tool_embeddings_cache`, `tool_registry`, `lessons_this_session`

**DB writes (significant):** `memory_fts`, `memory_meta`, `pi_analysis_runs`, `pi_bugs`, `pi_improvements`, `pi_violations`, `pi_wave_tasks`, `pi_waves`, `raw_metrics`, `raw_research`, `reg_analyzed_repos`, `reg_projects`, `reg_repo_extractions`, `reg_workflows`, `research_cache`, `tool_embeddings_cache`

**Events emitted:**
- Analysis: `ANALYSIS_STARTED`, `ANALYSIS_COMPLETED`, `ANALYSIS_FAILED`, `ANALYSIS_DISCOVERY_COMPLETED`, `ANALYSIS_RESEARCH_COMPLETED`, `ANALYSIS_AUDIT_COMPLETED`, `ANALYSIS_BUG_ANALYSIS_COMPLETED`, `ANALYSIS_SYNTHESIS_COMPLETED`
- Audit: `AUDIT_VIOLATION_FOUND`, `AUDIT_VIOLATIONS_CLEARED`, `AUDIT_IMPROVEMENT_FOUND`, `AUDIT_IMPROVEMENTS_CLEARED`
- Projects: `PROJECT_REGISTERED`, `PROJECT_UPDATED`, `REPO_ANALYZED`, `REPO_EXTRACTION_STORED`
- Research: `RESEARCH_CACHE_STORED`, `RESEARCH_CACHE_CLEARED`, `RESEARCH_COMPLETED`, `RESEARCH_VALIDATED`
- Workflow/wave: `WAVE_STARTED`, `WAVE_COMPLETED`, `WAVE_FAILED`, `WAVE_TASK_UPDATED`, `WORKFLOW_NODE_COMPLETED`, `WORKFLOW_PROGRESS_UPDATED`, `WORKFLOW_LEARNED`

**Referenced by:** 80 files — runtime hooks (`runtime/hooks/meta/`, `runtime/hooks/core/`, `runtime/hooks/quality/`), interfaces (`interfaces/cli/ds_workflow.py`, `interfaces/cli/analyze_project.py`, `interfaces/cli/session_analytics.py`), projections API routes (`projections/api/routes/discovery_research.py`, `discovery_external.py`), and ~30 test files.

**Tests:** No dedicated `tests/unit/control/` directory. Tests scattered across `tests/unit/` (test_workflow_runner, test_workflow_state_archive, test_workflow_registry, test_workflow_cost, test_workflow_engine_coverage, test_repo_context, test_research_source_contract, test_pack_context, test_context7_manager, test_memory_search, test_model_selector, test_on_stop_handoff, test_on_skill_complete, test_lib_context_handoff) and `tests/test_*` top-level (test_tool_search, test_web_research, test_think_integration, test_think_research, test_discovery_integration).

### control/ Sub-package Summaries

#### control/analysis/
**Purpose:** 5-phase project intelligence pipeline (Discovery → Research → Audit → Bug Analysis → Synthesis). `engine.py` orchestrates all phases. `repo_analyzer.py` analyzes external GitHub repos for pattern extraction. Stack adapters (nextjs, astro, python_generic) provide framework-specific analysis rules.
**DB tables:** reads `reg_projects`, `reg_analyzed_repos`; writes `pi_analysis_runs`, `pi_bugs`, `pi_improvements`, `pi_violations`, `pi_waves`, `pi_wave_tasks`, `reg_analyzed_repos`, `reg_repo_extractions`
**Tests:** No dedicated directory; covered by `tests/test_discovery_integration.py`, `tests/test_api_discovery.py`

#### control/context/
**Purpose:** Context compilation for skill prompts. `compiler.py` produces deterministic prompts from SKILL.md files (enables Claude prompt caching). `handoff.py` writes session handoff files at context threshold events (threshold constants: WARN=55%, COMPACT=70%, HANDOFF=75%, URGENT=82%). `context7_manager.py` manages context7 library lookups. `repo.py` assembles repo context packets. `monitor.py` monitors context usage.
**DB tables:** reads `raw_sessions`, `lessons_this_session`; writes `write_session_handoff`
**Tests:** `tests/unit/test_context7_manager.py`, `tests/unit/test_repo_context.py`, `tests/unit/test_lib_context_handoff.py`, `tests/unit/test_pack_context.py`

#### control/execution/
**Purpose:** Workflow execution engine. `workflow/runner.py` bridges workflow state to skill invocation via direct `core.skills.invocation` imports (no subprocess respawn since A3). `workflow/wave_executor.py` and `wave_executor_enhanced.py` execute dependency-wave task groups. `models/selector.py` selects AI models per skill mode. `dispatch_helpers.py` and `dispatch_tracking.py` support hook dispatch.
**DB tables:** reads `pi_waves`, `pi_wave_tasks`; writes `pi_waves`, `pi_wave_tasks`, `reg_workflows`
**Tests:** `tests/unit/test_workflow_runner.py`, `tests/unit/test_workflow_state_archive.py`, `tests/unit/test_workflow_registry.py`, `tests/unit/test_workflow_cost.py`, `tests/unit/test_workflow_engine_coverage.py`, `tests/unit/test_model_selector.py`, integration tests

#### control/research/
**Purpose:** Web research and tool discovery. `tools.py` (40 KB) provides TF-IDF and sentence-transformer semantic search over `tool_registry` DB table; includes 1-hour query cache via `cachetools`. `web.py` handles web research pipelines. `engine.py` orchestrates research phases. `memory.py` manages research memory with FTS.
**DB tables:** reads `tool_registry`, `research_cache`, `memory_fts`, `memory_meta`; writes `research_cache`, `tool_embeddings_cache`, `memory_fts`, `memory_meta`, `raw_research`
**Tests:** `tests/test_tool_search.py`, `tests/test_web_research.py`, `tests/test_api_research.py`

#### control/review/
**Purpose:** Session retrospective analysis for meta-review hook. `engine.py` reads recent handoff/recap files, extracts themes and blockers, and suggests escalation candidates via `core/learning/lesson_threshold.py`.
**DB tables:** reads via `core/learning/lesson_threshold`
**Tests:** `tests/unit/test_on_meta_review.py` (inferred from runtime hook)

#### control/session/
**Purpose:** Session management. `parser.py` parses `.sessions/YYYY-MM-DD/handoff-*.json` and `recap-*.md` files with event store bridge integration. `manager.py` tracks active sessions. `cache.py` provides session-level caching.
**DB tables:** reads `raw_sessions`; writes session records
**Tests:** `tests/unit/test_session_harvester.py`, `tests/integration/test_session_analytics.py`

#### control/skills/
**Purpose:** Skill lifecycle management. `router.py` (15,950 bytes) implements progressive disclosure gate — checks if user is in progressive mode and whether requested skill/mode is unlocked. `loader.py` loads skill definitions. `calibration.py` calibrates skill parameters. `completion.py` handles skill completion events. `metrics.py` records skill execution metrics.
**DB tables:** reads `raw_skill_telemetry`, `reg_projects`; writes `raw_skill_telemetry`
**Tests:** `tests/unit/test_on_skill_complete.py`, `tests/unit/test_skill_invoke.py`

---

## shared/

**Description:** Shared utilities and cross-cutting concerns. Two primary modules: `config.py` (deprecated `DreamStudioConfig` class — delegates to `core.config.paths`; only non-delegated feature is `project_roots` management) and `paths.py`. Sub-packages: `mcp-integrations/` (test scripts and docs for MCP browser testing) and `repo_analysis/` (SKILL.md analyzer that extracts patterns from skill files for organizational intelligence).

**File listing:**
| File | Size |
|------|------|
| shared/config.py | 3,621 |
| shared/paths.py | 3,067 |
| shared/mcp-integrations/agent-browser.md | 12,733 |
| shared/mcp-integrations/EXECUTE_TEST.md | 2,812 |
| shared/mcp-integrations/README.md | 2,998 |
| shared/mcp-integrations/run-browser-test.md | 2,819 |
| shared/mcp-integrations/test-agent-browser.py | 6,323 |
| shared/mcp-integrations/test-agent-browser.sh | 1,711 |
| shared/repo_analysis/analyzer.py | 16,973 |
| shared/repo_analysis/cli.py | 5,556 |
| shared/repo_analysis/formatters/__init__.py | 222 |
| shared/repo_analysis/formatters/json_formatter.py | 1,855 |
| shared/repo_analysis/formatters/markdown_formatter.py | 8,093 |
| shared/repo_analysis/pattern_extractors/cicd_patterns.py | 5,786 |
| shared/repo_analysis/pattern_extractors/code_quality_patterns.py | 5,955 |
| shared/repo_analysis/pattern_extractors/decision_tables.py | 2,612 |
| shared/repo_analysis/pattern_extractors/do_dont_examples.py | 2,682 |
| shared/repo_analysis/pattern_extractors/docs_patterns.py | 5,782 |
| shared/repo_analysis/pattern_extractors/frontmatter.py | 3,293 |
| shared/repo_analysis/pattern_extractors/progressive_disclosure.py | 2,271 |
| shared/repo_analysis/pattern_extractors/response_contracts.py | 2,738 |
| shared/repo_analysis/pattern_extractors/testing_patterns.py | 4,826 |
| shared/repo_analysis/pattern_extractors/version_guards.py | 2,825 |
| shared/version-detection.sh | 3,140 |

**Entry points:** `shared/repo_analysis/cli.py` has CLI entry point for SKILL.md batch analysis.

**DB reads:** None
**DB writes:** None (outputs to stdout/files)

**Events emitted:** None

**Referenced by:** 3 files — `canonical/skills/analyze/repo-analyzer.py`, `tests/test_tool_search.py`, `core/shared_intelligence/capability_routing.py`

**Tests:** No dedicated test directory.

**Notes:**
- `shared/config.py` is explicitly marked DEPRECATED. Path resolution should use `core.config.paths` directly.
- `shared/mcp-integrations/` contains test scripts for MCP browser automation; `.sh` script is not executable on Windows.
- `shared/version-detection.sh` is a bash script (cross-platform concern on Windows).

---

## packs/

**Description:** Runtime content for skill packs. Contains agent markdown files, context documents, rule sets, and project template scaffolding. Three sub-directories: `core/` (chief-of-staff agent, director agent, engineering agent, context documents), `domains/` (client and game domain agents, game rules, project-standards template), `quality/` (structure/architecture rules, FSC rules). The `analyze/hooks/.gitkeep` and `career/hooks/.gitkeep` indicate placeholder hook directories.

**File listing:**
| File | Size |
|------|------|
| packs/analyze/hooks/.gitkeep | 0 |
| packs/career/hooks/.gitkeep | 0 |
| packs/core/agents/chief-of-staff.md | 11,329 |
| packs/core/agents/director.md | 1,458 |
| packs/core/agents/engineering.md | 3,113 |
| packs/core/agents/README.md | 1,179 |
| packs/core/context/director-corrections.md | 750 |
| packs/core/context/director-preferences.md | 2,963 |
| packs/core/context/fullstack-standards.md | 6,489 |
| packs/core/context/session-context.md | 1,013 |
| packs/core/context/session-primer.md | 1,963 |
| packs/domains/agents/client.md | 2,796 |
| packs/domains/agents/game.md | 1,932 |
| packs/domains/domain_lib/__pycache__/game_validate.cpython-312.pyc | 24,573 (pyc only — no source .py present) |
| packs/domains/rules/game/*.md | 6 files, 1,407–1,808 each |
| packs/domains/templates/project-standards/* | Full project scaffold (Makefile, pyproject.toml, requirements, hooks/lib/, scripts/, docs) |
| packs/quality/rules/structure/architecture.md | 8,303 |
| packs/quality/rules/structure/fsc.md | 3,848 |

**Entry points:** None (content-only; no Python entry points)
**DB reads:** None
**DB writes:** None
**Events emitted:** None
**Referenced by:** No Python imports of `packs` found in the codebase.
**Tests:** No dedicated test directory.

**Notes:**
- `packs/domains/domain_lib/game_validate.cpython-312.pyc` exists without a corresponding `.py` source file — the source may have been deleted, leaving an orphaned `.pyc`.
- `packs/domains/templates/project-standards/` is a full project template scaffold including `hooks/lib/` modules (`audit.py`, `models.py`, `telemetry.py`, `time_utils.py`).

---

## hooks/ (repo root — git hooks, NOT runtime/hooks/)

**Description:** Git hook infrastructure and Claude Code hook dispatch configuration. Contains: `hooks.json` (canonical hook configuration — Claude Code reads this for UserPromptSubmit, Stop, PostCompact, PostToolUse hook commands), `on-commit.py` (git commit-time guardrail evaluator), `run.sh` (bash hook launcher for macOS/Linux), `run.cmd` (Windows cmd hook launcher), and `git/pre-push` (git pre-push gate that runs `ds workflow run pre-push`).

**File listing:**
| File | Size |
|------|------|
| hooks/git/pre-push | 717 |
| hooks/hooks.json | 4,420 |
| hooks/on-commit.py | 2,977 |
| hooks/run.cmd | 2,834 |
| hooks/run.sh | 2,100 |

**Entry points:**
- `hooks/on-commit.py` — `def main()` (guardrail evaluation at commit time; advisory mode by default)
- `hooks/git/pre-push` — bash script calling `py -m interfaces.cli.ds workflow run pre-push --non-interactive`
- `hooks/run.sh` and `hooks/run.cmd` — dispatcher scripts that search `runtime/hooks/{pack}/` for named handler

**DB reads:** None directly (delegates to `guardrails/evaluator.py`)
**DB writes:** None directly

**Events emitted:** None (delegates to guardrails)

**`hooks/hooks.json` structure:** Defines four hook types:
- `UserPromptSubmit`: runs `emitters/claude_code/run.py UserPromptSubmit` + `runtime/dispatch/hooks.py UserPromptSubmit`
- `Stop`: same pattern for Stop
- `PostCompact`: same pattern for PostCompact
- `PostToolUse`: matcher entries for Skill (empty hooks), Edit|Write (empty hooks), Read (empty hooks), then catch-all running both emitter and dispatcher

**Referenced by:** No Python imports. Referenced by Claude Code settings.json (installed by `integrations/installer/`).

**Tests:** `tests/unit/hooks/` — 3 test files

---

## examples/

**Description:** Single usage example for the adapter normalization system.

**File listing:**
| File | Size |
|------|------|
| examples/adapter_usage_example.py | 3,366 |

**Entry points:** `def main()` in `examples/adapter_usage_example.py` — demonstrates `EventNormalizer` with `GPTAdapter` and `DefaultAdapter` from `core.adapters.normalizers`.

**DB reads:** None
**DB writes:** None
**Events emitted:** None
**Referenced by:** No imports found.
**Tests:** No dedicated tests.

---

## scripts/

**Description:** Development utilities, CI helpers, and operational scripts. No application logic — these are operator-facing tools.

**File listing:**
| File | Size |
|------|------|
| scripts/backfill_components.py | 701 |
| scripts/benchmark_tokens.py | 692 |
| scripts/common.py | 1,131 |
| scripts/dashboard_smoke_harness.py | 3,654 |
| scripts/dev.ps1 | 10,661 |
| scripts/docker_runtime_check.py | 1,967 |
| scripts/ds_dashboard.py | 831 |
| scripts/lesson_queue.py | 457 |
| scripts/requeue_failed.py | 5,377 |
| scripts/runtime_state_hash_guard.py | 4,959 |
| scripts/setup.py | 676 |

**Entry points:**
- `scripts/dev.ps1` — PowerShell wrapper for all dev commands: `test`, `lint`, `fmt`, `typecheck`, `verify`, `verify-guarded`, `test-guarded`, `product-readiness`, `runtime-check`, `docker-runtime-check`, `run-api`, `run-ui`, `clean`, and Makefile-parity targets
- `scripts/ds_dashboard.py` — **compatibility shim only**; canonical location is `interfaces/cli/ds_dashboard.py`
- `scripts/requeue_failed.py` — recovers stuck events from `failed/` back to `spool/` (A0 fix for missing `schema_version`)
- `scripts/runtime_state_hash_guard.py` — read-only diagnostic: observes file metadata before/after a command to detect mutations; exit code 90 on mutation
- `scripts/dashboard_smoke_harness.py` — smoke test for dashboard API
- `scripts/docker_runtime_check.py` — validates Docker runtime environment

**DB reads:** None directly
**DB writes:** None
**Events emitted:** None
**Referenced by:** No Python imports.
**Tests:** No dedicated tests.

**Notes:**
- `scripts/ds_dashboard.py` is explicitly labeled a DUPLICATE/shim; canonical is `interfaces/cli/ds_dashboard.py`.
- `scripts/dev.ps1` is the Windows equivalent of a Makefile — primary dev entrypoint on Windows.

---

## templates/

**Description:** Jinja2 templates, compliance mapping YAMLs, ETL pipeline scripts, and a Power BI dashboard spec — all for the `ds-security` pack. Two root-level files: `templates/security/` directory (main content) and `templates/traceability-registry.yaml` (traceability template for `ds-core plan` skill).

**File listing:**
| File | Size |
|------|------|
| templates/traceability-registry.yaml | 990 |
| templates/security/README.md | 2,795 |
| templates/security/binary/analyze.sh.j2 | 4,965 |
| templates/security/binary/checksec-config.yaml.j2 | 3,134 |
| templates/security/binary/yara-rules.yar.j2 | 4,763 |
| templates/security/compliance/cwe-top25-mapping.yaml | 20,366 |
| templates/security/compliance/nist-csf-mapping.yaml | 13,646 |
| templates/security/compliance/owasp-asvs-mapping.yaml | 23,074 |
| templates/security/compliance/soc2-mapping.yaml | 9,041 |
| templates/security/dast/nuclei-config.yaml.j2 | 1,857 |
| templates/security/dast/zap-config.yaml.j2 | 2,916 |
| templates/security/etl/analyze_netcompat.py | 22,966 |
| templates/security/etl/export_dataset.py | 20,571 |
| templates/security/etl/generate_mitigations.py | 18,373 |
| templates/security/etl/map_compliance.py | 13,586 |
| templates/security/etl/parse_binary.py | 21,113 |
| templates/security/etl/parse_dast.py | 20,844 |
| templates/security/etl/parse_sarif.py | 22,751 |
| templates/security/etl/score_findings.py | 9,103 |
| templates/security/github-actions/binary-scan.yml.j2 | 5,510 |
| templates/security/github-actions/dast-scan.yml.j2 | 4,575 |
| templates/security/github-actions/security-scan.yml.j2 | 10,853 |
| templates/security/mitigations/auth-fixes.yaml | 7,708 |
| templates/security/mitigations/encryption-fixes.yaml | 9,450 |
| templates/security/mitigations/injection-fixes.yaml | 6,108 |
| templates/security/mitigations/netcompat-fixes.yaml | 9,890 |
| templates/security/mitigations/secrets-fixes.yaml | 7,726 |
| templates/security/powerbi/dashboard-spec.md | 95,471 |
| templates/security/semgrep-rules/access-control.yaml.j2 | 17,265 |
| templates/security/semgrep-rules/data-protection.yaml.j2 | 8,957 |
| templates/security/semgrep-rules/injection.yaml.j2 | 10,652 |
| templates/security/semgrep-rules/netcompat.yaml.j2 | 9,606 |
| templates/security/semgrep-rules/secrets.yaml.j2 | 6,881 |
| templates/security/semgrep-rules/transport.yaml.j2 | 5,373 |

**Entry points:** ETL scripts in `templates/security/etl/` are standalone executables called with client config args (e.g., `py templates/security/etl/parse_sarif.py --client {client} --scans-dir {dir}`). None have `def main()` in the standard sense — they are invoked directly.

**DB reads:** None (operate on filesystem scan outputs)
**DB writes:** None directly (produce parsed output files)
**Events emitted:** None

**Skill-to-template mapping (from README):**
| Skill | Templates Used |
|-------|----------------|
| binary-scan | binary/, github-actions/binary-scan.yml.j2, etl/parse_binary.py |
| dast | dast/, github-actions/dast-scan.yml.j2, etl/parse_dast.py |
| scan | semgrep-rules/, github-actions/security-scan.yml.j2, etl/parse_sarif.py |
| mitigate | mitigations/, etl/generate_mitigations.py |
| comply | compliance/, etl/map_compliance.py |
| netcompat | semgrep-rules/netcompat.yaml.j2, etl/analyze_netcompat.py |
| security-dashboard | powerbi/dashboard-spec.md, etl/ (full pipeline) |

**Referenced by:** No Python imports of `templates` from repo code.
**Tests:** No dedicated tests.

**Notes:** `templates/security/powerbi/dashboard-spec.md` at 95,471 bytes is the largest file in this subsystem — a detailed Power BI dashboard specification for the Kroger security dashboard client work.

---

## adapter-projections/

**Description:** Frozen static projections of Dream Studio adapter configuration — one per supported AI tool. Marked SUPERSEDED by `integrations/` + `emitters/`. Status note in `_SUPERSEDED.md`: retained for reference during Slice 1–2 transition, scheduled for deletion in Slice 3. The `claude/CLAUDE.md` contains a routing table placeholder (`<!-- ROUTING TABLE GENERATED BY COMPILER -->`) that is populated by `integrations/compiler/claude_code.py`.

**File listing:**
| File | Size |
|------|------|
| adapter-projections/_SUPERSEDED.md | 687 |
| adapter-projections/chatgpt/context_packet.md | 643 |
| adapter-projections/claude/CLAUDE.md | 1,350 |
| adapter-projections/codex/AGENTS.md | 682 |
| adapter-projections/copilot/instructions.md | 650 |
| adapter-projections/cursor/rules | 658 |
| adapter-projections/local-model/context_packet.md | 647 |
| adapter-projections/mcp/server-policy.json | 447 |
| adapter-projections/shell/command-policy.json | 452 |

**Entry points:** None
**DB reads:** None
**DB writes:** None
**Events emitted:** None
**Referenced by:** `integrations/compiler/claude_code.py` reads `adapter-projections/claude/CLAUDE.md` as the base template for compiler output.
**Tests:** None.

**Adapters covered:** chatgpt, claude, codex, copilot, cursor, local-model, mcp, shell

---

## projections/ (209 files — broken into sub-packages)

**Overall description:** FastAPI-based analytics and reporting platform. Serves the Dream Studio intelligence dashboard (`dashboard.html`). Reads from studio.db and presents metrics, insights, security findings, project intelligence, and exportable reports. Contains collectors (pull data from DB), analyzers (detect trends/anomalies), generators (produce dashboard data), exporters (CSV, Excel, PDF, PowerBI, PPTX), and a scheduler (APScheduler-backed cron jobs for report delivery via email).

---

### projections/api/

**Description:** FastAPI application root. `main.py` creates the app, registers CORS middleware (localhost-only per PD-1), CacheControlMiddleware (5-minute cache on `/api/*`), and mounts all routers. Serves `projections/frontend/dashboard.html` at `/` and `/dashboard`.

**File listing:**
| File | Size |
|------|------|
| projections/api/__init__.py | 32 |
| projections/api/main.py | 6,139 |
| projections/api/safety.py | 2,933 |
| projections/api/test_api_integration.py | 11,450 |
| projections/api/models/__init__.py | 32 |
| projections/api/models/insights.py | 1,991 |
| projections/api/models/metrics.py | 2,663 |
| projections/api/models/reports.py | 6,006 |
| projections/api/queries/__init__.py | 0 |
| projections/api/queries/token_attribution.py | 12,808 |
| projections/api/routes/__init__.py | 32 |
| projections/api/routes/alerts.py | 17,803 |
| projections/api/routes/analytics.py | 11,908 |
| projections/api/routes/audits.py | 20,691 |
| projections/api/routes/discovery_external.py | 8,379 |
| projections/api/routes/discovery_internal.py | 19,562 |
| projections/api/routes/discovery_research.py | 13,214 |
| projections/api/routes/exports.py | 27,881 |
| projections/api/routes/frontend.py | 1,445 |
| projections/api/routes/hooks.py | 19,236 |
| projections/api/routes/insights.py | 11,351 |
| projections/api/routes/intelligence.py | 36,438 |
| projections/api/routes/metrics.py | 18,663 |
| projections/api/routes/ml.py | 4,060 |
| projections/api/routes/prd.py | 9,224 |
| projections/api/routes/project_intelligence.py | 109,882 |
| projections/api/routes/realtime.py | 5,403 |
| projections/api/routes/reports.py | 10,603 |
| projections/api/routes/schedules.py | 16,086 |
| projections/api/routes/security.py | 24,690 |
| projections/api/routes/shared_intelligence.py | 31,435 |
| projections/api/routes/sqlite_schema.py | 2,628 |
| projections/api/routes/telemetry.py | 4,590 |
| projections/api/websocket/__init__.py | 32 |
| projections/api/websocket/connection_manager.py | 8,563 |

**Entry points:** `projections/api/main.py` — `def start_api(host, port, reload)` + `if __name__ == "__main__": start_api(...)`. Also callable via `scripts/dev.ps1 run-api`.

#### projections/api/routes/ — Route Prefix Map

| Route File | Prefix (from main.py) | Notes |
|------------|----------------------|-------|
| metrics.py | `/api/v1/metrics` | |
| insights.py | `/api/v1/insights` | |
| reports.py | `/api/v1/reports` | |
| exports.py | `/api/v1/export` | |
| schedules.py | `/api/v1/schedules` | |
| realtime.py | `/api/v1` | WebSocket streaming |
| alerts.py | `/api/v1/alerts` | |
| ml.py | `/api/v1/ml` | |
| analytics.py | `/api/v1/analytics` | |
| project_intelligence.py | `/api/v1/projects` | Largest route file: 109,882 bytes; includes WebSocket |
| prd.py | (no prefix — mounted at root) | |
| discovery_internal.py | `/api/discovery/internal` | |
| discovery_external.py | (no prefix) | |
| discovery_research.py | (no prefix) | |
| hooks.py | `/api/v1` | |
| security.py | `/api/v1` | |
| audits.py | `/api/v1` | |
| intelligence.py | `/api/v1/intelligence` | |
| telemetry.py | `/api/telemetry` | |
| shared_intelligence.py | `/api/shared-intelligence` | |
| frontend.py | (not mounted as router; served via FileResponse) | |
| sqlite_schema.py | (utility module — not a router) | Helper functions `object_exists`, `table_columns` |

#### projections/api/models/

**Purpose:** Pydantic response models for API endpoints.
| File | Size |
|------|------|
| projections/api/models/insights.py | 1,991 |
| projections/api/models/metrics.py | 2,663 |
| projections/api/models/reports.py | 6,006 |

#### projections/api/websocket/

**Purpose:** WebSocket connection manager for real-time metric streaming. Thread-safe; tracks active connections by client_id; supports topic-based subscriptions; provides broadcast and targeted messaging.
| File | Size |
|------|------|
| projections/api/websocket/connection_manager.py | 8,563 |

---

### projections/config/

**Description:** Settings management for the projections platform. Loads from `projections.yaml` config file with typed defaults. Classes: `RealtimeSettings`, `AlertSettings`, `NotificationSettings`, `EmailSettings`, `ExportSettings`, `DashboardSettings`, `ProjectionsSettings`.

**File listing:**
| File | Size |
|------|------|
| projections/config/__init__.py | 32 |
| projections/config/settings.py | 9,258 |
| projections/config/test_settings.py | 2,554 |

**DB reads:** None
**DB writes:** None

---

### projections/core/

**Description:** Core analytics business logic. Seven sub-packages: `alerts/` (rule evaluation), `analyzers/` (trend, anomaly, performance, prediction), `collectors/` (DB-reading data collectors), `config/` (runtime paths), `email/` (SMTP email delivery), `insights/` (insight and recommendation engines), `notifications/` (multi-channel dispatch), `reports/` (report generation), `scheduler/` (APScheduler-backed cron jobs), `sla/` (SLA compliance tracking), `streaming/` (metric streaming).

**File listing (selected):**
| File | Size |
|------|------|
| projections/core/alerts/alert_evaluator.py | 6,746 |
| projections/core/alerts/rule_manager.py | 9,326 |
| projections/core/analyzers/anomaly_detector.py | 10,799 |
| projections/core/analyzers/performance_analyzer.py | 9,456 |
| projections/core/analyzers/predictor.py | 12,441 |
| projections/core/analyzers/trend_analyzer.py | 9,072 |
| projections/core/collectors/authority_sources.py | 4,400 |
| projections/core/collectors/lesson_collector.py | 8,232 |
| projections/core/collectors/model_collector.py | 7,986 |
| projections/core/collectors/session_collector.py | 9,934 |
| projections/core/collectors/skill_collector.py | 9,159 |
| projections/core/collectors/token_collector.py | 14,401 |
| projections/core/collectors/workflow_collector.py | 9,378 |
| projections/core/email/sender.py | 15,000 |
| projections/core/email/template_renderer.py | 4,170 |
| projections/core/insights/insight_engine.py | 31,166 |
| projections/core/insights/recommendations.py | 9,858 |
| projections/core/insights/root_cause.py | 15,028 |
| projections/core/notifications/dispatcher.py | 10,281 |
| projections/core/reports/generator.py | 14,394 |
| projections/core/scheduler/job_scheduler.py | 24,392 |
| projections/core/scheduler/storage.py | 12,574 |
| projections/core/scheduler/cli.py | 11,530 |
| projections/core/sla/tracker.py | 19,615 |
| projections/core/streaming/metric_streamer.py | 10,043 |
| projections/core/execution_events_projection.py | 2,800 |

#### projections/core/scheduler/

**Purpose:** APScheduler-backed report scheduling. `job_scheduler.py` manages cron-expression jobs with email delivery. `storage.py` persists job definitions. `cli.py` provides CLI management. Falls back to simple loop-based scheduling if `apscheduler` not installed.

**Entry points:**
- `projections/core/scheduler/__main__.py` — `from projections.core.scheduler.cli import main; main()` — runnable as `python -m projections.core.scheduler`
- `projections/core/scheduler/cli.py` has `def main()`

**DB reads:** `scheduled_reports`
**DB writes:** `scheduled_reports`

---

### projections/exporters/

**Description:** Multi-format export pipeline. Exporters for CSV, Excel (with templates), PDF, PowerBI (.pbix-compatible JSON), and PPTX. Also includes chart rendering and template systems. Many files contain their own test suites inline.

**File listing:**
| File | Size |
|------|------|
| projections/exporters/chart_renderer.py | 12,179 |
| projections/exporters/csv_exporter.py | 14,947 |
| projections/exporters/excel_exporter.py | 26,966 |
| projections/exporters/excel_templates.py | 39,160 |
| projections/exporters/pdf_exporter.py | 16,723 |
| projections/exporters/powerbi_exporter.py | 27,295 |
| projections/exporters/pptx_exporter.py | 20,539 |
| projections/exporters/pptx_template_loader.py | 17,741 |
| projections/exporters/pptx_templates/__init__.py | 32 |
| projections/exporters/pptx_templates/example_usage.py | 5,245 |
| (+ demo_*, example_*, test_* files) | various |

**DB reads:** None (consume pre-collected data objects)
**DB writes:** None
**Events emitted:** None

---

### projections/frontend/

**Description:** Single-file dashboard HTML application.

| File | Size |
|------|------|
| projections/frontend/dashboard.html | 501,683 bytes (~490 KB) |
| projections/frontend/integrate_improvements.py | 15,513 |

`dashboard.html` is the primary UI artifact — a single-file self-contained HTML/JS dashboard served at `/` and `/dashboard` by the FastAPI app. `integrate_improvements.py` is a build-time script for merging improvements into the dashboard HTML.

---

### projections/generators/

**Description:** Production dashboard data generator. `production_dashboard.py` (53,859 bytes) orchestrates all collectors and analyzers to produce a full dashboard data payload. Has optional enterprise ML features (`dream_studio_enterprise.ml.*`) that gracefully degrade if not installed.

**File listing:**
| File | Size |
|------|------|
| projections/generators/__init__.py | 32 |
| projections/generators/production_dashboard.py | 53,859 |

**DB reads:** All major `raw_*` and `reg_*` tables via collectors
**DB writes:** None

---

### projections/graph/

**Description:** AST-based Python component extraction for unified-discovery. `component_extractor.py` parses Python source files to extract functions, classes, and imports and stores them in `pi_components` for graph analysis.

**File listing:**
| File | Size |
|------|------|
| projections/graph/__init__.py | 0 |
| projections/graph/component_extractor.py | 17,459 |

**DB reads:** `pi_components`
**DB writes:** `pi_components`, `pi_dependencies`
**Events emitted:** None

---

### projections/models/

**Description:** Pydantic models for canonical event representations used by the projections layer.

**File listing:**
| File | Size |
|------|------|
| projections/models/__init__.py | 32 |
| projections/models/events.py | 3,149 |

---

### projections/parsers/

**Description:** SARIF 2.1.0 format parser. Reads SARIF files from security scanning tools (Semgrep, Bandit, Trivy, etc.) and writes findings to `sec_sarif_findings` in studio.db; also emits canonical `SECURITY_FINDING_RECORDED` events to spool.

**File listing:**
| File | Size |
|------|------|
| projections/parsers/__init__.py | 32 |
| projections/parsers/sarif_parser.py | 12,542 |

**DB reads:** None
**DB writes:** `sec_sarif_findings`
**Events emitted:** `EventType.SECURITY_FINDING_RECORDED`

---

### projections/scoring/

**Description:** Risk scoring engine for security findings. `engine.py` processes `activity_log` events and computes risk scores based on file-level, project-level, and temporal risk factors. Emits canonical events to spool.

**File listing:**
| File | Size |
|------|------|
| projections/scoring/__init__.py | 32 |
| projections/scoring/cli.py | 1,854 |
| projections/scoring/engine.py | 9,063 |

**DB reads:** `activity_log`, `sec_sarif_findings`
**DB writes:** `execution_events` (risk score records)
**Events emitted:** `EventType.RISK_SCORE_COMPUTED`

**Entry points:** `projections/scoring/cli.py` — CLI wrapper for `RiskScoringEngine`

---

### projections/ DB Table Summary

**Reads (significant):** `activity_log`, `alert_history`, `alert_rules`, `audit_runs`, `canonical_events`, `decision_log`, `ds_projects`, `execution_events`, `hook_executions`, `hook_findings`, `hook_invocations`, `pi_analysis_runs`, `pi_bugs`, `pi_components`, `pi_dependencies`, `pi_improvements`, `pi_violations`, `prd_documents`, `prd_handoffs`, `raw_lessons`, `raw_sessions`, `raw_skill_telemetry`, `raw_workflow_nodes`, `raw_workflow_runs`, `reg_projects`, `research_cache`, `route_decision_records`, `scheduled_reports`, `sec_cve_matches`, `sec_manual_reviews`, `sec_sarif_findings`, `security_findings`, `skill_invocations`, `sla_definitions`, `sqlite_master`, `token_usage_records`, `tool_registry`, `validation_results`, `vw_security_summary`, `web_research`

**Writes:** `alert_history`, `alert_rules`, `audit_runs`, `execution_events`, `pi_components`, `pi_dependencies`, `raw_lessons`, `raw_sessions`, `raw_skill_telemetry`, `raw_token_usage`, `raw_workflow_nodes`, `raw_workflow_runs`, `scheduled_reports`, `sec_sarif_findings`, `sla_definitions`, `token_usage_records`

**Events emitted:** `RISK_SCORE_COMPUTED`, `SECURITY_FINDING_RECORDED`

**Referenced by:** 99 files — the most widely imported subsystem in the repo. Key importers: `interfaces/cli/ds_dashboard.py`, `interfaces/cli/generate-dashboard.py`, `core/events/canonical.py`, `core/events/__init__.py`, `spool/ingestor.py`, and all projections-internal cross-imports.

**Tests:**
- `projections/tests/` — 11 test files (test_alerts, test_analyzers, test_api, test_collectors, test_email, test_exporters, test_insights, test_realtime, test_reports, test_scheduler, test_realtime) + validate_tests.py
- Inline test files in `projections/exporters/` (test_chart_renderer, test_csv_exporter, test_excel_templates, etc.)
- `projections/core/scheduler/test_scheduler.py` (inline)
- External test coverage in `tests/unit/` (test_dashboard_*, test_projection_service_db_paths, test_analytics_only_ingestion, etc.)

---

*End of Gap 5: Discovered Subsystems — Deep Dive*

---

# Phase 0c Audit — Gaps 6, 8, 9, 10
**Generated:** 2026-05-22
**Repo:** `C:\Users\Dannis Seay\builds\dream-studio-clean`
**Runtime DB:** `C:\Users\Dannis Seay\.dream-studio\state\studio.db`

---

## Gap 6: Event Taxonomy Reconciliation

**Taxonomy file:** `docs/canonical/event_taxonomy_v1.json`
**Schema version:** 1.0.0
**Total defined event types:** 112 across 29 namespaces

---

### Live Event Types (emitted in canonical_events)

22 distinct event types appear in the live DB. All dates are 2026.

| Event Type | Row Count | First Seen | Last Seen |
|-----------|-----------|------------|-----------|
| tool.execution.completed | 822 | 2026-05-17 | 2026-05-22 |
| prompt.lifecycle.submitted | 249 | 2026-05-16 | 2026-05-22 |
| hook.tool_activity | 247 | 2026-05-21 | 2026-05-22 |
| token.consumption.recorded | 180 | 2026-05-16 | 2026-05-22 |
| event.validation.failed | 57 | 2026-05-17 | 2026-05-19 |
| system.session.recorded | 51 | 2026-05-17 | 2026-05-22 |
| system.hook.execution.logged | 45 | 2026-05-17 | 2026-05-19 |
| system.session.closed | 33 | 2026-05-17 | 2026-05-22 |
| system.handoff.created | 26 | 2026-05-17 | 2026-05-22 |
| workflow.node.completed | 25 | 2026-05-18 | 2026-05-18 |
| skill.invoked | 21 | 2026-05-17 | 2026-05-20 |
| context.threshold.crossed | 19 | 2026-05-17 | 2026-05-22 |
| work_order.started | 15 | 2026-05-17 | 2026-05-19 |
| work_order.created | 14 | 2026-05-17 | 2026-05-17 |
| task.created | 9 | 2026-05-17 | 2026-05-19 |
| token.consumed | 7 | 2026-05-22 | 2026-05-22 |
| milestone.created | 4 | 2026-05-17 | 2026-05-17 |
| task.completed | 4 | 2026-05-19 | 2026-05-19 |
| work_order.closed | 4 | 2026-05-17 | 2026-05-19 |
| gate.bypassed | 3 | 2026-05-17 | 2026-05-17 |
| project.created | 3 | 2026-05-17 | 2026-05-22 |
| workflow.completed | 2 | 2026-05-18 | 2026-05-18 |

**Total rows in canonical_events:** 1,840

---

### Defined in Taxonomy but Never Emitted

Of 112 defined types, 109 have never been emitted. 3 live types match taxonomy entries (`event.validation.failed`, `task.created`, `task.completed`).

The remaining 109 are grouped by namespace below. Each entry is classified as either **Referenced in code** (string literal appears in at least one .py file) or **Not in code** (no .py file contains the string literal).

#### Namespace: research
- `research.query.created` — Not in code
- `research.source.fetched` — Referenced in: `core/event_store/legacy_bridge.py`
- `research.source.ranked` — Not in code

#### Namespace: prd
- `prd.created` — Referenced in: `core/events/criticality.py`, `core/event_store/legacy_bridge.py`
- `prd.updated` — Referenced in: `core/events/criticality.py`, `core/event_store/legacy_bridge.py`
- `prd.scope.modified` — Not in code
- `prd.requirement.proposed` — Not in code
- `prd.requirement.approved` — Not in code
- `prd.architecture.defined` — Not in code
- `prd.approved` — Not in code

#### Namespace: decision
- `decision.proposed` — Not in code
- `decision.pending_review` — Not in code
- `decision.prd.approved` — Not in code
- `decision.translation.approved` — Not in code
- `decision.research.approved` — Not in code

#### Namespace: task
- `task.updated` — Referenced in: `core/event_store/legacy_bridge.py`
- `task.decomposition.suggested` — Not in code

#### Namespace: skill
- `skill.execution.started` — Referenced in: `control/skills/loader.py`, `control/skills/router.py`, `core/event_store/legacy_bridge.py`
- `skill.execution.completed` — Referenced in: `control/skills/completion.py`, `core/event_store/legacy_bridge.py`, `core/projections/consumers.py`
- `skill.execution.failed` — Referenced in: `core/event_store/legacy_bridge.py`

#### Namespace: workflow
- `workflow.execution.started` — Referenced in: `core/event_store/legacy_bridge.py`, `core/projections/workflow_consumer.py`, `core/upgrade/canonical_event_reconciliation.py`
- `workflow.execution.completed` — Referenced in: `core/event_store/legacy_bridge.py`, `core/projections/workflow_consumer.py`, `core/upgrade/canonical_event_reconciliation.py`
- `workflow.execution.failed` — Referenced in: `core/event_store/legacy_bridge.py`, `core/projections/workflow_consumer.py`

#### Namespace: agent
- `agent.execution.started` — Not in code
- `agent.execution.completed` — Not in code
- `agent.execution.failed` — Not in code

#### Namespace: ingestion
- `ingestion.source.detected` — Not in code
- `ingestion.session.created` — Referenced in: `control/session/parser.py`
- `ingestion.event.normalized` — Referenced in: `core/event_store/legacy_bridge.py`, `core/telemetry/processor.py`

#### Namespace: reconstruction
- `reconstruction.event.inferred` — Not in code
- `reconstruction.graph.built` — Not in code

#### Namespace: business
- `business.intent.created` — Not in code
- `business.requirement.stated` — Not in code

#### Namespace: contract
- `contract.generated` — Not in code
- `contract.validated` — Not in code
- `contract.breaking_change.detected` — Not in code

#### Namespace: security
- `security.finding.created` — Referenced in: `tests/unit/test_event_emission_reliability.py`
- `security.finding.detected` — Referenced in: `core/upgrade/canonical_event_reconciliation.py`, `tests/unit/test_event_emission_reliability.py`
- `security.dependency.outdated` — Not in code
- `security.cve.detected` — Not in code
- `security.scan.started` — Referenced in: `tests/unit/test_event_emission_reliability.py`
- `security.scan.completed` — Referenced in: `canonical/events/types.py`, `tests/unit/test_event_emission_reliability.py`
- `security.scan.failed` — Referenced in: `tests/unit/test_event_emission_reliability.py`

#### Namespace: usage
- `usage.tokens.input` — Referenced in: `core/event_store/legacy_bridge.py`
- `usage.tokens.output` — Not in code
- `usage.cost` — Not in code

#### Namespace: execution
- `execution.started` — Referenced in: `canonical/events/types.py`, `control/skills/loader.py`, `control/skills/router.py`
- `execution.completed` — Referenced in: `canonical/events/types.py`, `control/session/cache.py`, `control/session/manager.py`
- `execution.failed` — Referenced in: `canonical/events/types.py`, `core/events/criticality.py`, `core/events/types.py`
- `execution.retrying` — Not in code

#### Namespace: analysis
- `analysis.started` — Referenced in: `canonical/events/types.py`, `core/events/types.py`, `tests/unit/test_event_type_advisory.py`
- `analysis.completed` — Referenced in: `canonical/events/types.py`, `core/events/types.py`, `tests/unit/test_event_type_advisory.py`
- `finding.created` — Referenced in: `guardrails/models.py`, `canonical/events/types.py`, `core/events/types.py`
- `finding.resolved` — Referenced in: `core/events/types.py`

#### Namespace: repo
- `repo.analyzed` — Referenced in: `canonical/events/types.py`, `core/events/types.py`
- `repo.extraction.stored` — Referenced in: `canonical/events/types.py`, `core/events/types.py`
- `repo.pattern.extracted` — Referenced in: `core/events/types.py`
- `repo.building_block.extracted` — Referenced in: `core/events/types.py`

#### Namespace: model
- `model.selected` — Referenced in: `core/events/types.py`
- `model.invoked` — Referenced in: `core/events/types.py`
- `model.response.received` — Referenced in: `core/events/types.py`

#### Namespace: session
- `session.started` — Referenced in: `core/events/types.py`, `core/projections/consumers.py`, `tests/unit/test_event_type_advisory.py`
- `session.resumed` — Referenced in: `core/events/types.py`
- `session.compacted` — Referenced in: `core/events/types.py`, `core/projections/consumers.py`
- `session.ended` — Referenced in: `core/events/types.py`, `core/projections/consumers.py`, `tests/unit/test_event_type_advisory.py`

#### Namespace: tool
- `tool.invoked` — Referenced in: `core/events/types.py`
- `tool.completed` — Referenced in: `core/events/types.py`
- `tool.failed` — Referenced in: `core/events/types.py`

#### Namespace: hook
- `hook.triggered` — Referenced in: `core/events/types.py`
- `hook.completed` — Referenced in: `core/events/types.py`
- `hook.failed` — Referenced in: `core/events/types.py`

#### Namespace: backfill
- `backfill.started` — Referenced in: `core/events/types.py`
- `backfill.completed` — Referenced in: `core/events/types.py`

#### Namespace: migration
- `migration.applied` — Referenced in: `core/events/types.py`

#### Namespace: database
- `database.merged` — Referenced in: `core/events/types.py`

#### Namespace: alert
- `alert.created` — Referenced in: `core/events/types.py`
- `alert.acknowledged` — Referenced in: `core/events/types.py`
- `alert.resolved` — Referenced in: `core/events/types.py`

#### Namespace: scan
- `scan.started` — Referenced in: `core/events/types.py`, `core/security/event_emitter.py`, `tests/unit/test_event_emission_reliability.py`
- `scan.completed` — Referenced in: `canonical/events/types.py`, `core/events/types.py`, `core/security/event_emitter.py`

#### Namespace: vulnerability
- `vulnerability.found` — Referenced in: `core/events/types.py`
- `vulnerability.mitigated` — Referenced in: `core/events/types.py`

#### Namespace: memory
- `memory.stored` — Referenced in: `core/events/types.py`
- `memory.retrieved` — Referenced in: `core/events/types.py`

#### Namespace: plan
- `plan.created` — Referenced in: `core/events/criticality.py`
- `plan.updated` — Referenced in: `core/events/criticality.py`
- `plan.activated` — Referenced in: `core/events/criticality.py`
- `plan.completed` — Referenced in: `core/events/criticality.py`
- `plan.abandoned` — Not in code
- `plan.paused` — Not in code
- `plan.resumed` — Not in code

#### Namespace: phase
- `phase.started` — Referenced in: `core/events/criticality.py`
- `phase.completed` — Referenced in: `core/events/criticality.py`, `core/projections/workflow_consumer.py`, `core/upgrade/canonical_event_reconciliation.py`
- `phase.failed` — Referenced in: `core/events/criticality.py`
- `phase.skipped` — Not in code

#### Namespace: wave
- `wave.created` — Not in code
- `wave.started` — Referenced in: `canonical/events/types.py`, `core/events/criticality.py`, `core/events/types.py`
- `wave.completed` — Referenced in: `canonical/events/types.py`, `core/events/criticality.py`, `core/events/types.py`
- `wave.failed` — Referenced in: `canonical/events/types.py`, `core/events/criticality.py`, `core/events/types.py`

#### Namespace: system
- `system.startup` — Referenced in: `core/decisions/coverage_model.py`, `core/decisions/integrity.py`
- `system.shutdown` — Referenced in: `core/decisions/coverage_model.py`, `core/decisions/integrity.py`
- `system.health_check` — Not in code
- `system.error` — Not in code
- `system.warning` — Not in code

#### Namespace: test
- `test.started` — Not in code
- `test.completed` — Not in code
- `test.failed` — Not in code
- `test.runtime_verification` — Referenced in: `tests/runtime_verification/test_write_paths.py`
- `test.write_audit` — Not in code

---

### Event Types Emitted but NOT in Taxonomy

All 22 live event types are NOT present in the taxonomy's `allowed_event_types`. The taxonomy defines canonical namespaces using dot-notation sub-namespaces (e.g. `tool.invoked`, `tool.completed`, `tool.failed`) but the live system emits compound types using different patterns.

| Event Type | Count | Notes |
|-----------|-------|-------|
| tool.execution.completed | 822 | Taxonomy has `tool.invoked`, `tool.completed`, `tool.failed` — not `tool.execution.completed` |
| prompt.lifecycle.submitted | 249 | Namespace `prompt` not in taxonomy |
| hook.tool_activity | 247 | Taxonomy has `hook.triggered`, `hook.completed`, `hook.failed` — not `hook.tool_activity` |
| token.consumption.recorded | 180 | Namespace `token` not in taxonomy; taxonomy has `usage.tokens.*` |
| event.validation.failed | 57 | Taxonomy has `validation` namespace with `event.validation.failed` — this one matches |
| system.session.recorded | 51 | Taxonomy has `system.*` but not `system.session.recorded` |
| system.hook.execution.logged | 45 | Not in taxonomy `system` namespace |
| system.session.closed | 33 | Not in taxonomy `system` namespace |
| system.handoff.created | 26 | Not in taxonomy `system` namespace |
| workflow.node.completed | 25 | Taxonomy has `workflow.execution.*` — not `workflow.node.completed` |
| skill.invoked | 21 | Taxonomy has `skill.execution.*` — not `skill.invoked` |
| context.threshold.crossed | 19 | Namespace `context` not in taxonomy |
| work_order.started | 15 | Namespace `work_order` not in taxonomy |
| work_order.created | 14 | Namespace `work_order` not in taxonomy |
| task.created | 9 | In taxonomy — matches |
| token.consumed | 7 | Namespace `token` not in taxonomy |
| milestone.created | 4 | Namespace `milestone` not in taxonomy |
| task.completed | 4 | In taxonomy — matches |
| work_order.closed | 4 | Namespace `work_order` not in taxonomy |
| gate.bypassed | 3 | Namespace `gate` not in taxonomy |
| project.created | 3 | Namespace `project` not in taxonomy |
| workflow.completed | 2 | Taxonomy has `workflow.execution.completed` — not `workflow.completed` |

**Summary:** 3 of 22 live event types match taxonomy entries exactly. 19 are not in the taxonomy. 109 of 112 taxonomy-defined types have never been emitted. Primary pattern divergence: live system uses operational-domain prefixes (`work_order.*`, `token.*`, `hook.tool_activity`, `prompt.*`) not represented in the taxonomy.

---

## Gap 8: Tests — Source Module Coverage

**Test directory:** `tests/`
**Total test files scanned:** 338 (all `test_*.py` files)
**Source modules loaded:** 1,067 .py files across the codebase

---

### Test Directory to Source Module Mapping

| Test Directory | Source Modules Covered (representative) |
|---------------|----------------------------------------|
| tests/core/ | core.event_store |
| tests/evals/ | core.config.sqlite_bootstrap, core.work_orders.close, guardrails.enforcement |
| tests/integration/emitters/ | (no project imports — subprocess-based) |
| tests/integration/integrations/ | integrations.health, integrations.installer.claude_code, integrations.detector |
| tests/integration/spool/ | (no project imports — subprocess/file-based) |
| tests/integration/ (root) | core.event_store.studio_db, core.config, core.config.state, control.execution, control.analysis, core.telemetry, core.validation, core.research.store, control.session.parser, control.execution.workflow.* |
| tests/runtime_verification/ | core.config.database, core.config, core.observability.trace_logger |
| tests/ (root) | control.research.tools, core.graph.query, projections.api.main, control.research, core.memory.retrieval |
| tests/unit/canonical/ | (no project imports — contract/schema checks) |
| tests/unit/emitters/ | (no project imports — subprocess/file-based) |
| tests/unit/gates/ | core.gates.pre_push, canonical.events.types, canonical.events.envelope, interfaces.cli |
| tests/unit/health/ | core.health.doctor |
| tests/unit/hooks/ | (no project imports — subprocess-based) |
| tests/unit/integrations/ | integrations.compiler.claude_code, integrations.detector, integrations.installer.*, integrations.manifest, integrations.targets.claude_code.settings_merge, integrations.health |
| tests/unit/spool/ | (no project imports — file/subprocess-based) |
| tests/unit/ (root) | core.config.*, core.event_store.*, core.shared_intelligence.*, projections.api.main, core.telemetry.*, control.execution.*, core.work_orders.*, core.memory.*, core.ontology.*, core.upgrade.*, core.release.*, core.projects.*, interfaces.cli.*, guardrails.scanners.*, emitters.claude_code.*, control.context.*, control.skills, spool.session_harvester |

---

### Fixture Documentation (tests/conftest.py)

Single conftest.py file at tests root. No subdirectory conftest files exist.

#### Global behavior: `pytest_configure` (not a fixture)
- **Purpose:** Reinstalls SIGINT handler on Windows after pytest installs its own. Prevents phantom SIGINT signals from reaching pytest machinery during SQLite/filesystem operations.
- **Platform:** Windows only.

#### `handler` (function scope)
- **Provides:** The `load_handler` callable. Tests call `handler(name)` to dynamically load a hook handler module from `runtime/hooks/*/` or legacy `hooks/handlers/`.
- **Creates:** In-process module loaded via `importlib.util`.

#### `isolated_home` (function scope)
- **Provides:** A `tmp_path` redirected as `HOME`, `USERPROFILE`, `Path.home()`, with `CLAUDE_PLUGIN_ROOT` and `CLAUDE_PROJECTS_DIR` deleted.
- **Creates:** Nothing on disk beyond the pytest `tmp_path`.

#### `reset_warnings` (function scope, autouse)
- **Provides:** Resets Python warnings filters before each test.
- **Creates:** Nothing.

#### `spool_root` (function scope)
- **Provides:** Isolated per-test spool directory at `tmp_path/events/`. Sets `DS_SPOOL_ROOT` env var via monkeypatch so subprocess emitters inherit it.
- **Creates:** `tmp_path/events/` directory. Cleans up `.sessions/*.json` files individually on teardown (avoids Windows + Python 3.12 `rmtree` SIGINT issue).

#### `ds_home` (function scope)
- **Provides:** Isolated per-test dream-studio home at `tmp_path/ds_home/`. Sets `DS_DREAM_STUDIO_HOME` so `integrations/manifest.py` never reaches real `~/.dream-studio`.
- **Creates:** `tmp_path/ds_home/` directory.

#### `guard_real_homedir` (function scope, autouse)
- **Provides:** Hermetic fallback env vars for all path-sensitive env vars not already set by other fixtures. Guards against test-induced writes to the operator's real `~/.dream-studio` and `~/.claude`.
- **Sets (if not already set):**
  - `DS_SPOOL_ROOT` → `tmp_path/guard_spool/`
  - `DS_DREAM_STUDIO_HOME` → `tmp_path/guard_ds_home/`
  - `DREAM_STUDIO_DB_PATH` → `tmp_path/guard_state/studio.db`
  - `DS_PLATFORM_PROFILE_PATH` → `tmp_path/guard_platform/platform.json`
  - `DS_ACTIVE_TASK_PATH` → `tmp_path/guard_active_task/active_task.json`
  - `DS_MACHINE_ID_PATH` → `tmp_path/guard_machine_id/machine_id`
  - `DS_CWD_RESOLVER_ROOT` → `tmp_path`
  - `DS_DIAGNOSTICS_DIR` → `tmp_path/guard_diagnostics/`
- **Post-yield assertion:** Counts files in real `~/.dream-studio/events` and `~/.dream-studio/integrations` before and after; asserts no new files were created.
- **Also:** Calls `core.telemetry.machine_id._reset_cache()` to prevent machine_id caching across tests.

---

### Source Modules Without Test Coverage

The following source modules have no test file that directly imports them (by module path matching). This list excludes `__init__.py` files. Note: some modules may be exercised indirectly via integration tests that do not import them by name.

**131 modules identified as not directly imported by any test file:**

#### canonical/
- `canonical.adapters.claude.statusline`
- `canonical.skills.analyze.*` (9 files: base_analyzer, domains/career, domains/design, domains/finance, domains/real_estate, domains/registry, modes/repo/analyze-repos, repo-analyzer, test_analyzer, test_domains, test_remaining_domains)
- `canonical.skills.domains.modes.website.scripts.*` (brand-compliance, cip-brief, generate-tokens, lint-artifact)
- `canonical.skills.domains.scripts.*` (search-anti-patterns, search-font-pairings)

#### control/
- `control.review.engine`

#### core/
- `core.adapters.models`
- `core.adapters.normalizers`
- `core.design_briefs.mutations`
- `core.design_briefs.queries`
- `core.dispatch.bus`
- `core.milestones.close`
- `core.milestones.mutations`
- `core.milestones.queries`
- `core.monitoring.validation_monitor`
- `core.pricing.claude_models`
- `core.projections.consumers`
- `core.projections.framework`
- `core.projections.workflow_consumer`
- `core.projections.workflow_metrics`
- `core.repo_actions.*` (executor, feedback, formatter, generator, model, planner, priority, runner — 8 files)
- `core.sdlc.active_task`
- `core.sdlc.cwd_resolver`
- `core.skills.invocation`
- `core.skills.queries`
- `core.storage.document_store`

#### emitters/
- `emitters.shared.spool_writer`

#### projections/ (largest uncovered block)
- `projections.api.models.*` (insights, metrics, reports)
- `projections.api.queries.token_attribution`
- `projections.api.routes.*` (alerts, analytics, audits, discovery_external, discovery_internal, discovery_research, exports, frontend, hooks, insights, intelligence, metrics, ml, prd, project_intelligence, realtime, reports, schedules, security, shared_intelligence, sqlite_schema, telemetry — 21 route files)
- `projections.api.websocket.connection_manager`
- `projections.config.settings`
- `projections.config.test_settings`
- `projections.core.analyzers.*` (anomaly_detector, performance_analyzer, predictor, trend_analyzer)
- `projections.core.config.runtime_paths`
- `projections.core.email.*` (example_usage, sender, template_renderer, test_import)
- `projections.core.insights.*` (insight_engine, recommendations, root_cause)
- `projections.core.notifications.dispatcher`
- `projections.core.reports.*` (example_usage, generator)
- `projections.core.sla.tracker`
- `projections.core.streaming.metric_streamer`
- `projections.exporters.*` (chart_renderer, csv_exporter, demo_chart_renderer, demo_powerbi_export, excel_exporter, excel_templates, pdf_exporter, powerbi_exporter, pptx_exporter, pptx_template_loader — 10+ files)
- `projections.frontend.integrate_improvements`
- `projections.generators.production_dashboard`
- `projections.models.events`
- `projections.parsers.sarif_parser`
- `projections.tests.*` (internal test runner files)

---

### Test File Sample by Directory

#### tests/core/ (1 file)
`test_dual_write.py`

#### tests/evals/ (6 files)
`test_context_budget_evals.py`, `test_database_grounding_evals.py`, `test_dependency_chain.py`, `test_gate_evals.py`, `test_guardrail_enforcement_evals.py`, `test_round_trip_evals.py`, `test_skill_contract_evals.py`

#### tests/integration/ (37 files)
Covers: emitters dispatch, integrations install chain, spool pipeline (7 files), hook dispatch chains (12 hook-specific files), workflow execution (5 files), migration, schema, session analytics, operational tables, research pipeline, cloud backup, daily learning pipeline, execution graph

#### tests/runtime_verification/ (1 file)
`test_write_paths.py` — validates runtime write paths for DB and spool

#### tests/ root (8 files)
API discovery, research, graph query, retrieval capability, think integration

#### tests/unit/ (232 files)
Covers: adapters, analytics, archive, artifact format, audit export, canonical events, career ops, compiler, contract atlas, dashboard (12 files), database governance, design brief, docker, emitters (3 files), envelope, gates (4 files), health, hooks (2 files), integrations (11 files), memory (5 files), milestone, model selector, module contracts, ontology, operator decisions, performance, platform, PRD authority, projects, prompt assembler, release (6 files), security (10 files), session harvester, shared intelligence (15 files), skill (5 files), spool (5 files), task attribution, telemetry (5 files), token attribution, upgrade (4 files), validation, work orders (28 files), workflow (8 files)

---

## Gap 9: Configuration Completeness

---

### Environment Variables (comprehensive)

The following variables are read via `os.environ.get`, `os.getenv`, or `os.environ[]` in the codebase. Variables found only as string literals (not in `os.*` calls) are noted separately.

| Variable | Default | Primary Files | Controls |
|---------|---------|---------------|---------|
| ANALYTICS_SMTP_PASS | None | `projections/config/settings.py` | SMTP credentials for analytics email |
| ANALYTICS_SMTP_USER | None | `projections/config/settings.py` | SMTP credentials for analytics email |
| ANTHROPIC_API_KEY | None | `interfaces/cli/ci_gate.py` | Anthropic API authentication |
| CLAUDE_CODE | None | `core/work_orders/mutations.py` | Detects Claude Code adapter context |
| CLAUDE_FILE_PATH | `""` | `runtime/hooks/quality/on-agent-correction.py`, `runtime/hooks/domains/on-game-validate.py` | Hook context — current file path |
| CLAUDE_MODEL | None | `runtime/hooks/meta/on-skill-complete.py` | Model name from Claude Code environment |
| CLAUDE_PLUGIN_ROOT | None | `runtime/hooks/meta/on-skill-telemetry.py` | Root path of Claude Code plugin |
| CLAUDE_PROJECTS_DIR | None | `control/context/monitor.py`, `core/utils/compact_utils.py` | Claude projects directory |
| CLAUDE_SESSION_ID | None | `runtime/hooks/meta/on-session-start.py`, `runtime/hooks/meta/on-skill-load.py` | Active Claude Code session ID |
| CLAUDE_USER_MESSAGE_TEXT | `""` | `core/utils/milestone.py` | User message text from hook context |
| COMSPEC | `""` | `core/config/platform.py` | Windows shell path (platform detection) |
| DREAM_STUDIO_BASE_REF | None | `interfaces/cli/contract_atlas_lifecycle_gate.py`, `interfaces/cli/contract_docs_drift_gate.py` | Git base ref for CI drift gates |
| DREAM_STUDIO_CHANGED_FILES | None | `interfaces/cli/contract_atlas_lifecycle_gate.py`, `interfaces/cli/contract_docs_drift_gate.py` | CI-injected changed file list for drift gates |
| DREAM_STUDIO_CORRECTIONS_PATH | None | `core/learning/correction_patterns.py` | Path to operator correction patterns file |
| DREAM_STUDIO_DEBUG | `""` | `core/telemetry/debug.py` | Enables debug telemetry output |
| DREAM_STUDIO_HOME | `/tmp/dream-studio-home` | `core/config/paths.py`, `scripts/docker_runtime_check.py` | Dream Studio home directory (Docker default) |
| DREAM_STUDIO_MODEL | None | `runtime/hooks/meta/on-skill-complete.py` | Overrides model selection for skill completion |
| DREAM_STUDIO_RUNTIME_WRITE_VERIFY | None | `tests/runtime_verification/test_write_paths.py` | Enables runtime write path verification in tests |
| DREAM_STUDIO_RUN_LEGACY_API_INTEGRATION | None | `projections/api/test_api_integration.py` | Enables legacy API integration tests |
| DREAM_STUDIO_TELEMETRY_DB | None | `core/work_orders/evals.py` | Alternate telemetry DB path for evals |
| DS_ACTIVE_TASK_PATH | None | `core/sdlc/active_task.py` | Path to active_task.json state file |
| DS_CWD_RESOLVER_ROOT | None | `core/sdlc/cwd_resolver.py` | Root for CWD resolution |
| DS_DIAGNOSTICS_DIR | None | `runtime/hooks/core/on-post-tool-use.py`, `core/telemetry/diagnostics.py` | Diagnostics output directory |
| DS_DREAM_STUDIO_HOME | None | `integrations/manifest.py` | Dream Studio home for integration manifest writes |
| DS_MACHINE_ID_PATH | None | `core/telemetry/machine_id.py` | Path to machine_id file |
| DS_PLATFORM_PROFILE_PATH | None | `core/config/platform.py` | Path to platform profile JSON |
| DS_SPOOL_ROOT | None | `spool/config.py`, `emitters/claude_code/run.py` | Spool root directory for event files |
| EMAIL_PASSWORD | None | `projections/core/email/sender.py` | Email sender password |
| EMAIL_USERNAME | `"your-email@gmail.com"` | `projections/core/email/sender.py` | Email sender username |
| GITHUB_BASE_REF | None | `interfaces/cli/contract_atlas_lifecycle_gate.py`, `interfaces/cli/contract_docs_drift_gate.py` | GitHub Actions base ref for drift gates |
| GITHUB_PERSONAL_ACCESS_TOKEN | `""` | `interfaces/cli/pulse_collector.py` | GitHub API token for pulse collector |
| HOME | `/tmp/dream-studio-user` | `core/config/paths.py`, `emitters/claude_code/run.py` | User home directory (Docker default) |
| ITERM_SESSION_ID | None | `core/config/platform.py` | iTerm session detection (platform) |
| JINA_API_KEY | None | `control/research/web.py` | Jina AI API key for web research |
| POWERSHELL_DISTRIBUTION_CHANNEL | None | `core/config/platform.py` | PowerShell distribution detection |
| PSModulePath | None | `core/config/platform.py` | PowerShell module path (Windows detection) |
| PULSE_COOLDOWN_SEC | `"60"` | `interfaces/cli/pulse_collector.py` | Cooldown seconds between pulse collections |
| SENTRY_DSN | None | `core/telemetry/telemetry.py` | Sentry error reporting DSN |
| SHELL | `""` | `core/config/platform.py` | Shell path (platform detection) |
| TERM | `""` | `core/config/platform.py` | Terminal type (platform detection) |
| TERM_PROGRAM | `""` | `core/config/platform.py` | Terminal program name (platform detection) |
| USERPROFILE | None | `interfaces/cli/ds_memory.py`, `emitters/claude_code/run.py` | Windows user profile path |
| WT_SESSION | None | `core/config/platform.py` | Windows Terminal session detection |

**Additional variables referenced as string literals only (not in os.* calls):**

| Variable | Files | Controls |
|---------|-------|---------|
| DREAM_STUDIO_CONFIG | `core/installed_runtime.py` | Installed adapter config path |
| DREAM_STUDIO_DB_PATH | `core/config/database.py`, `interfaces/cli/ci_gate.py`, `interfaces/cli/ds.py` | Primary SQLite DB path override |
| DREAM_STUDIO_ENABLE_WORK_ORDER_EVAL_TELEMETRY | `core/work_orders/evals.py` | Enables eval telemetry |
| DREAM_STUDIO_RUN_LEGACY_RESEARCH_DIAGNOSTICS | `interfaces/cli/debug_trust_score.py` | Enables legacy research diagnostics |
| DREAM_STUDIO_SOURCE_ROOT | `core/installed_productization.py`, `interfaces/cli/ds.py` | Source root for installed productization |
| DREAM_STUDIO_TELEMETRY_DISABLED | `core/telemetry/emitters.py` | Disables all telemetry emission |
| DREAM_STUDIO_WORK_ORDER_ROOT | `core/work_orders/models.py` | Work order root directory override |

---

### pyproject.toml Tool Configurations

#### [tool.black]
- `line-length = 100`

#### [project.scripts]
- `ds = "interfaces.cli.ds:main"` — CLI entry point

#### [tool.flake8]
- `max-line-length = 100`
- `per-file-ignores`: `tests/*` → E501, F401

#### [tool.pytest.ini_options]
- `testpaths = ["tests", "analytics/tests"]`
- `asyncio_mode = "auto"`
- `addopts = "-v --color=no"`
- `filterwarnings`: ignores DeprecationWarning and PendingDeprecationWarning
- `markers`: `runtime_reliability` — Phase 5 runtime reliability gate marker

#### [tool.coverage.run]
- `source = ["hooks/lib", "packs/domains/domain_lib"]`
- `omit`: 14 files (legacy wave 0 infrastructure, wave 6 learning systems, progressive disclosure systems — all in `hooks/lib/`)

#### [tool.coverage.report]
- `fail_under = 70`

---

### Dependencies

#### requirements.txt (production)

| Package | Version Constraint | Purpose |
|---------|-------------------|---------|
| pydantic | >=2.0 | Data validation and settings |
| jsonschema | >=4.0 | JSON schema validation |
| sentry-sdk | (unpinned) | Error tracking |
| pandas | >=2.0 | Data analysis |
| Jinja2 | >=3.1 | Template rendering |
| PyYAML | >=6.0 | YAML parsing |
| psutil | >=5.9 | System process utilities |
| networkx | >=3.0 | Graph queries (Unified Discovery System) |
| cachetools | >=5.0 | Caching utilities (Unified Discovery System) |
| fastapi | >=0.100 | Analytics API server |
| uvicorn | >=0.23 | ASGI server |
| httpx | >=0.24 | Async HTTP client |
| python-multipart | >=0.0.6 | FastAPI file upload support |

**Commented-out / conditional:**
- `giskard>=2.0`, `rebuff>=0.1`, `llm-guard>=0.3` — security scanning libs, require Python <3.12, currently stubbed
- `tiktoken>=0.5` — precise token counting, optional
- `apscheduler>=3.10` — report scheduler, optional

#### requirements-dev.txt

| Package | Version | Purpose |
|---------|---------|---------|
| pytest | ==9.0.3 | Test runner |
| pytest-cov | ==7.1.0 | Coverage reporting |
| freezegun | >=1.5 | Time freezing for tests |
| factory-boy | >=3.3 | Test factory fixtures |
| black | >=24.0 | Code formatter |
| flake8 | >=7.0 | Linter |
| pip-audit | >=2.7 | Dependency vulnerability scanning |
| pre-commit | >=3.0 | Pre-commit hook runner |

#### requirements-semantic.txt (optional)

| Package | Version | Purpose |
|---------|---------|---------|
| sentence-transformers | >=2.2 | Embedding-based semantic search (not required for default TF-IDF/FTS5 operation) |

---

### Pre-commit Hooks (.pre-commit-config.yaml)

| Hook | Repo | Rev | Stages |
|------|------|-----|--------|
| black | `github.com/psf/black` | 24.0.0 | (default — pre-commit) |
| flake8 | `github.com/PyCQA/flake8` | 7.0.0 | (default — pre-commit) |
| conventional-commits | local (pygrep) | — | commit-msg |

**Conventional commit pattern:** `^(feat|fix|docs|chore|refactor|test|ci|style|perf|build|revert)(\(.+\))?: .{1,72}`

---

### Linting and Type Configuration

#### .flake8
- `max-line-length = 100`
- `extend-ignore = E501` (line length delegated to black)
- **Excluded directories:** `.venv`, `.git`, `.claude`, `.codex`, `.adapter-scratch`, `.ai-scratch`, `__pycache__`, `.planning`, `templates`, `packs/domains/templates`, `packs/domains/domain_lib/game_validate.py`
- **per-file-ignores:**
  - `tests/*` → F401 (unused imports allowed in tests)
  - `packs/core/hooks/on-stop-handoff.py` → F401
  - `packs/domains/hooks/on-game-validate.py` → F401

#### pyrightconfig.json
- `include`: `["hooks", "tests"]` — type checking scoped to hooks and tests only; does not include `core/`, `control/`, `canonical/`, `projections/`, etc.
- `extraPaths`: `["hooks"]`
- `pythonVersion`: `"3.10"` — targets 3.10 but repo runs on 3.12+
- `typeCheckingMode`: `"basic"`
- `reportMissingModuleSource`: `"none"`

---

## Gap 10: Documentation Depth

**docs/ root:** `C:\Users\Dannis Seay\builds\dream-studio-clean\docs`
**Total markdown files:** 124

---

### docs/ File Inventory with Outlines

#### docs/ (root-level files, 11 files)

##### ARCHITECTURE.md
- **Lines:** 62 | **Modified:** 2026-05-14
- **Headings:** Component Map, Data Flow, SQLite-First Direction, Safety Model, Publication Boundary
- **Aspirational markers:** NO

##### DATABASE.md
- **Lines:** 189 | **Modified:** 2026-05-22
- **Headings:** Paths, Authority Areas, Runtime Rules, Read Models, Publication Boundary
- **Aspirational markers:** NO

##### HOOK_RUNTIME.md
- **Lines:** 168 | **Modified:** 2026-05-22
- **Headings:** Hook Authority Model, Canonical hooks, Orphaned candidates, Removed hooks, Hook Execution Flow, Registered Hooks, Dispatcher Sub-Handler Mapping
- **Aspirational markers:** NO

##### MIGRATION_AUTHORITY.md
- **Lines:** 168 | **Modified:** 2026-05-22
- **Headings:** Canonical Migration Directory, Schema Version Authority, Root migrations/ Legacy, Migration 011 Gap, Database Connection Authority
- **Aspirational markers:** NO

##### PUBLICATION_BOUNDARY.md
- **Lines:** 167 | **Modified:** 2026-05-22
- **Headings:** Public Allowlist, Private By Default, Current Repo Hygiene, Git History Policy, Documentation Rule, Contract Atlas Export Rule, Release-Gate Runtime Boundary
- **Aspirational markers:** NO

##### RUNTIME_RELIABILITY_GATE.md
- **Lines:** 94 | **Modified:** 2026-05-14
- **Headings:** How to run (Via Makefile, Via pytest marker, Via explicit file list), What it covers, DB/Migration Authority, Event Emission
- **Aspirational markers:** NO

##### TRANSACTION_SAFETY_GUIDE.md
- **Lines:** 322 | **Modified:** 2026-05-14
- **Headings:** Problem, Solution Pattern (Before/After), Migration Checklist, Replace Direct Connections
- **Aspirational markers:** NO

##### UPGRADE_PLAN.md
- **Lines:** 635 | **Modified:** 2026-05-19
- **Headings:** Executive Summary, Current State, Phase 1–3 extraction plans, typography, color systems
- **Aspirational markers:** YES (design skill upgrade plan with phased aspirational roadmap)

##### WORKFLOW_RUNTIME.md
- **Lines:** 171 | **Modified:** 2026-05-22
- **Headings:** Workflow Authority Model, Canonical, Runtime Integration, Workflow Inventory (22 templates), Retry Behavior, Timeout Behavior, Gate/Pause/Resume Behavior
- **Aspirational markers:** NO

##### WORKFLOWS.md
- **Lines:** 69 | **Modified:** 2026-05-15
- **Headings:** Workflow Types, Route Decisions, Evidence Requirements, Approval Boundaries, CI/CD Workflow Strategy, Adapter Use, Publication Safety
- **Aspirational markers:** NO

##### README.md
- **Lines:** 174 | **Modified:** 2026-05-19
- **Headings:** Public Product Docs, Architecture And Contracts, Analytics-Only Profile, Installed Dashboard Command, Module Contracts, Expert Workflows, Career Ops And Capability Center
- **Aspirational markers:** NO

---

#### docs/contracts/ (34 files)

##### adapter-contract.md
- **Lines:** 97 (raw scan shows 134 with blank lines) | **Modified:** 2026-05-14
- **Headings:** Authority Principles, Adapter Responsibilities, Adapter Prohibitions, Current Adapter Status, Boundary Checklist, Import And Dependency Audit, Event And State Interactions
- **Aspirational markers:** NO

##### agent-contract.md
- **Lines:** 41 | **Modified:** 2026-05-14
- **Headings:** Required Fields, Authority, Relationships, Portable Rendering, Validation Expectations
- **Aspirational markers:** NO

##### approval-contract.md
- **Lines:** 82 | **Modified:** 2026-05-14
- **Headings:** Authority Principles, Approval Modes, Approval States, Future/File-Backed Record Names, Mandatory Approval Actions, Human Decision Semantics, Non-Delegable Decisions
- **Aspirational markers:** NO

##### artifact-format-policy.md
- **Lines:** 99 | **Modified:** 2026-05-14
- **Headings:** Purpose, Authority Model, Authoritative Source Formats, Generated And Rendered Projection Formats, Format Selection Rules, Generated Reports And Dashboards, Artifact-Specific Rules
- **Aspirational markers:** NO

##### dashboard-projection-model-contract.md
- **Lines:** 141 | **Modified:** 2026-05-14
- **Headings:** Purpose, Projection Artifact Roles, Authority Model, DashboardProjectionSnapshot, WorkOrderOverviewProjection, EvalProjection, ApprovalOperatorDecisionProjection
- **Aspirational markers:** NO

##### enterprise-aggregation-contract.md
- **Lines:** 95 | **Modified:** 2026-05-14
- **Headings:** Authority Principles, Allowed Enterprise Inputs, Forbidden Live DB Defaults, Redacted/Aggregate Projection Package Expectations, Explicit Operator-Selected Inputs, ML Artifact Classification, Org Graph And Report Classification
- **Aspirational markers:** NO

##### eval-artifact-contract.md
- **Lines:** 120 | **Modified:** 2026-05-14
- **Headings:** Authority Principles, Required Fields, Required File-Backed Eval Types, Mode-Aware Mutation Semantics, Handoff Prompt Semantics, Operator Decision Eval Semantics, Evaluator Semantics
- **Aspirational markers:** NO

##### event-contract.md
- **Lines:** 74 | **Modified:** 2026-05-14
- **Headings:** Authority, Event Envelope, Versioning Rules, Replay Expectations, Export Expectations, What Is Not An Event, Boundary Rules
- **Aspirational markers:** NO

##### execution-packet-contract.md
- **Lines:** 76 | **Modified:** 2026-05-14
- **Headings:** Authority Principles, Targets, Required Packet Fields, Render-Only Semantics, Target Mapping, Validation Expectations
- **Aspirational markers:** NO

##### file-structure-authority-policy.md
- **Lines:** 179 | **Modified:** 2026-05-14
- **Headings:** Purpose, Authority Model, Canonical Repo-Owned Locations, Generated Local Meta Locations, Work Order Artifact Structure, Audit Report And Handoff Locations, Evidence/Approval/Continuity/Security/Projection Locations
- **Aspirational markers:** YES (contains TODO)

##### governance-contract.md
- **Lines:** 49 | **Modified:** 2026-05-14
- **Headings:** Authority Principles, Signal Ownership, Privacy And Export Classes, Export And Backup Rules, Scanner And Guardrail Rules, Company And Org Boundaries, Active Hook Boundary
- **Aspirational markers:** NO

##### handoff-packet-contract.md
- **Lines:** 179 | **Modified:** 2026-05-14
- **Headings:** Purpose, Required Fields And Sections, Decision Taxonomies, Handoff Types, Operator Decision Gate, Recovery Decision Requirements, Fresh-Session Rule
- **Aspirational markers:** NO

##### hook-contract.md
- **Lines:** 47 | **Modified:** 2026-05-14
- **Headings:** Required Fields, Canonical Location, Authority, Portable Rendering, Governance And Privacy, Validation Expectations
- **Aspirational markers:** NO

##### human-in-the-loop-contract.md
- **Lines:** 62 | **Modified:** 2026-05-14
- **Headings:** Authority Principles, Roles, Human Decision Types, Non-Delegable Actions, Approval Responsibilities, Manual Execution Representation, Validation Expectations
- **Aspirational markers:** NO

##### operator-decision-contract.md
- **Lines:** 48 | **Modified:** 2026-05-14
- **Headings:** Purpose, Decision Request, Operator Decision, Rules, CLI
- **Aspirational markers:** NO

##### portable-execution-contract.md
- **Lines:** 57 | **Modified:** 2026-05-14
- **Headings:** Canonical Primitive Definition, Target-Specific Rendering, Target Expectations, Adapter Boundaries, Governance/Privacy Boundaries, Event And Telemetry Expectations, Prohibitions
- **Aspirational markers:** NO

##### projection-contract.md
- **Lines:** 88 | **Modified:** 2026-05-14
- **Headings:** Authority Principles, Projection Classes, Table Ownership Matrix, Route Ownership Matrix, Write Classification Rules, Dashboard Rules, Export Rules
- **Aspirational markers:** NO

##### research-source-contract.md
- **Lines:** 95 | **Modified:** 2026-05-14
- **Headings:** Purpose, Authority Principles, Research Artifact Contract, Source Record Contract, Source Quality Rules, Cache And Evidence Surfaces, API And Projection Boundaries
- **Aspirational markers:** NO

##### secure-production-readiness-gate.md
- **Lines:** 156 | **Modified:** 2026-05-15
- **Headings:** Authority, Control Families, Skill And Control Overlap, Run Policy, Scores, Findings And Remediation, Project Details Integration
- **Aspirational markers:** NO

##### security-by-default-development-lifecycle-gate.md
- **Lines:** 134 | **Modified:** 2026-05-15
- **Headings:** Canonical Framework, Lifecycle Policy, Finding Contract, Readiness Effect, Project Portfolio Hydration, AI Usage Accounting Impact, Task Attribution Impact
- **Aspirational markers:** NO

##### security-review-47-scan-crosswalk.md
- **Lines:** 80 | **Modified:** 2026-05-14
- **Headings:** Purpose, Source And Catalog References, Coverage Status Values, Source-To-Catalog Coverage Matrix, Coverage Summary, Recommended Revision Themes
- **Aspirational markers:** NO

##### security-review-catalog-governance.md
- **Lines:** 76 | **Modified:** 2026-05-15
- **Headings:** Purpose, Canonical Artifact Roles, Source-Of-Truth Rules, Synchronization Rules, Drift Prevention Checks, Allowed Edit Paths, Required Checks Before Acceptance
- **Aspirational markers:** NO

##### security-review-profile-pack-contract.md
- **Lines:** 281 | **Modified:** 2026-05-15
- **Headings:** Purpose, Authority Boundary, Relationship To Existing Contracts, Lifecycle Gate Integration, Security Taxonomy, ScanDefinition, Evidence Model
- **Aspirational markers:** NO

##### security-review-report-artifact-contract.md
- **Lines:** 164 | **Modified:** 2026-05-14
- **Headings:** Purpose, Artifact Roles, Storage Guidance, SecurityReviewReport, SecurityFindingRecord, SecurityEvidenceRecord, AcceptedRiskRecord
- **Aspirational markers:** NO

##### security-review-scan-catalog.md
- **Lines:** 137 | **Modified:** 2026-05-14
- **Headings:** Purpose, Relationship To The Profile Pack Contract, Tier Model, Valid Categories, Catalog Data Fields, Non-Execution Rules, Catalog Entries
- **Aspirational markers:** NO

##### security-review-scan-definition-schema.md
- **Lines:** 99 | **Modified:** 2026-05-14
- **Headings:** Purpose, Relationship To Existing Security Documents, Non-Execution Boundary, Top-Level Document Shape, ScanDefinition Shape, SourceItemRef Shape, Required Traceability Rules
- **Aspirational markers:** NO

##### security-review-source-47-enterprise-scans.md
- **Lines:** 63 | **Modified:** 2026-05-14
- **Headings:** Purpose, Source Provenance, Original 47 Enterprise Security Scan List
- **Aspirational markers:** NO

##### security-review-tier0-work-order-template.md
- **Lines:** 176 | **Modified:** 2026-05-14
- **Headings:** Purpose, Source Contracts, Template Identity, Required Target Intake Fields, Tier 0 Scan Selection Rules, Observe-only Review Boundary, Evidence Requirements
- **Aspirational markers:** NO

##### skill-contract.md
- **Lines:** 47 | **Modified:** 2026-05-14
- **Headings:** Required Fields, Authority, Identifier Rules, Relationships, Portable Rendering, Validation Expectations
- **Aspirational markers:** NO

##### state-contract.md
- **Lines:** 77 | **Modified:** 2026-05-14
- **Headings:** Authority Principles, State Classes, Ownership Matrix, Duplicate And Ambiguous State, Read-Only Projection Rules, Adapter Boundary Rules, Telemetry Boundary Rules
- **Aspirational markers:** NO

##### workflow-contract.md
- **Lines:** 43 | **Modified:** 2026-05-14
- **Headings:** Required Fields, Authority, Relationships, Portable Rendering, Validation Expectations
- **Aspirational markers:** NO

##### work-ledger-contract.md
- **Lines:** 55 | **Modified:** 2026-05-14
- **Headings:** Authority Principles, File-Backed Ledger Records, Future Event Names, Deferred DB/Event Integration, Prohibitions, Validation Expectations
- **Aspirational markers:** NO

##### work-order-contract.md
- **Lines:** 85 | **Modified:** 2026-05-14
- **Headings:** Authority Principles, Required Fields, Lifecycle States, Storage, Identifier Rules, Relationship To Other Contracts, Prohibitions
- **Aspirational markers:** NO

##### work-order-paused-work-contract.md
- **Lines:** 80 | **Modified:** 2026-05-14
- **Headings:** Purpose, Storage, Required Fields, Status Rules, Resolution Fields, Resume Gate Rules, Not Chat Memory
- **Aspirational markers:** NO

##### work-result-contract.md
- **Lines:** 71 | **Modified:** 2026-05-14
- **Headings:** Authority Principles, Required Fields, Status Meanings, Raw Output Preservation, Structured Extraction, Next Work Order Recommendation, Handoff Packet Relationship
- **Aspirational markers:** NO

---

#### docs/architecture/ (9 files)

##### canonical-event-reconciliation.md
- **Lines:** 19 | **Modified:** 2026-05-15
- **Headings:** (single top-level heading only)
- **Aspirational markers:** NO

##### contract-atlas.md
- **Lines:** 284 | **Modified:** 2026-05-22
- **Headings:** Authority Boundary, Registry Foundation, Maturity Ledger, AI Usage Accounting, Platform Hardening, Drift Gate, Lifecycle And Export Refresh
- **Aspirational markers:** NO

##### dream-studio-ai-orchestration-architecture.md
- **Lines:** 24 | **Modified:** 2026-05-14
- **Headings:** Orchestration Loop, Adapter Model, Operational Intelligence, Boundary
- **Aspirational markers:** NO

##### dream-studio-dashboard-projection-mapping.md
- **Lines:** 352 | **Modified:** 2026-05-22
- **Headings:** Purpose, Projection Domains, Required Mapping Fields, Dashboard Readiness, Operator Story Map, Contract Atlas Projection, Installed Adapter Router Projection
- **Aspirational markers:** NO

##### dream-studio-execution-telemetry-spine.md
- **Lines:** 85 | **Modified:** 2026-05-15
- **Headings:** Product Direction, Core Spine, Module Fact Tables, Dashboard Modules, Docker Boundary, Research And Blocker Routing, Additive Migration
- **Aspirational markers:** NO

##### dream-studio-structured-authority-projection-model.md
- **Lines:** 93 | **Modified:** 2026-05-14
- **Headings:** Purpose, Source Authority, Projection Record Shape, Domains, Lifecycle And Confidence, Stale And Superseded Detection, Stop-Gate Implications
- **Aspirational markers:** NO

##### event-store.md
- **Lines:** 211 | **Modified:** 2026-05-22
- **Headings:** Overview, canonical_events (Authoritative), Event Schema, Domain Field, execution_events (Projection), Projection Trigger, Projected Event Types
- **Aspirational markers:** NO

##### shared-authority-and-adapter-projections.md
- **Lines:** 191 | **Modified:** 2026-05-22
- **Headings:** Canonical Authority, Adapter Role, Convergence Rules, Cross-AI Continuity, Container Boundary, Platform Hardening Refresh
- **Aspirational markers:** NO

##### SYSTEM.md
- **Lines:** 238 | **Modified:** 2026-05-14
- **Headings:** Architectural Overview, Design Principles (Event Sourcing, Clear Responsibilities, Separation of Concerns, Minimal by Default), Directory Structure
- **Aspirational markers:** YES (contains TODO)

---

#### docs/operations/ (25 files)

All 25 files modified 2026-05-14 to 2026-05-22. No files contain aspirational markers. Line counts range from 29 (verified-legacy-purge-policy.md) to 361 (installed-platform-productization.md).

| File | Lines | Modified |
|------|-------|----------|
| adapter-workspace-hygiene.md | 61 | 2026-05-14 |
| career-ops-capability-center.md | 61 | 2026-05-15 |
| code-history-impact-guardrail.md | 34 | 2026-05-14 |
| docker-clean-room.md | 62 | 2026-05-14 |
| docker-module-profiles.md | 66 | 2026-05-22 |
| expert-workflow-systems.md | 158 | 2026-05-15 |
| external-project-validation-pipeline.md | 62 | 2026-05-22 |
| github-repo-intake-evaluation.md | 59 | 2026-05-15 |
| independent-configuration-model.md | 146 | 2026-05-22 |
| installed-adapter-runtime.md | 241 | 2026-05-22 |
| installed-platform-productization.md | 283 | 2026-05-22 |
| lightweight-github-ci-strategy.md | 41 | 2026-05-15 |
| lint-format-baseline-policy.md | 183 | 2026-05-22 |
| local-runtime.md | 118 | 2026-05-14 |
| long-run-multisession-operational-validation.md | 81 | 2026-05-22 |
| platform-hardening-sequence.md | 80 | 2026-05-22 |
| prd-authority-lifecycle.md | 119 | 2026-05-15 |
| product-authority-orchestration-hardening.md | 115 | 2026-05-19 |
| product-readiness.md | 200 | 2026-05-15 |
| repo-publication-privacy.md | 49 | 2026-05-22 |
| task-attribution-and-outcomes.md | 83 | 2026-05-15 |
| troubleshooting.md | 190 | 2026-05-22 |
| verified-legacy-purge-policy.md | 29 | 2026-05-14 |
| windows-dev-commands.md | 61 | 2026-05-14 |
| work-orders.md | 152 | 2026-05-14 |

---

#### docs/audits/ (2 files in 2026-05-22-full-stock/)

| File | Lines | Modified |
|------|-------|----------|
| 00-mechanical-inventory.md | 787 | 2026-05-22 |
| 00b-mechanical-inventory-depth.md | 1066 | 2026-05-22 |

---

#### docs/authoring/ (1 file)

| File | Lines | Modified |
|------|-------|----------|
| skills.md | 98 | 2026-05-19 |

---

#### docs/demo/sanitized/ (5 files)

| File | Lines | Modified |
|------|-------|----------|
| 15-minute-technical-walkthrough.md | 62 | 2026-05-15 |
| 5-minute-script.md | 49 | 2026-05-15 |
| fallback-plan.md | 41 | 2026-05-15 |
| README.md | 22 | 2026-05-15 |
| rehearsal-report.md | 49 | 2026-05-15 |

---

#### docs/pilot/company-internal-pilot/ (4 files)

| File | Lines | Modified |
|------|-------|----------|
| executive-summary.md | 36 | 2026-05-15 |
| feedback-template.md | 40 | 2026-05-15 |
| README.md | 197 | 2026-05-15 |
| technical-appendix.md | 111 | 2026-05-15 |

---

#### docs/product/ (6 files)

| File | Lines | Modified |
|------|-------|----------|
| dream-studio-architecture-brief.md | 75 | 2026-05-14 |
| dream-studio-artifact-requirements.md | 62 | 2026-05-14 |
| dream-studio-definition-of-done.md | 66 | 2026-05-14 |
| dream-studio-human-in-the-loop-policy.md | 56 | 2026-05-14 |
| dream-studio-prd.md | 184 | 2026-05-15 |
| dream-studio-research-and-verification-policy.md | 51 | 2026-05-14 |
| dream-studio-stack-and-runtime.md | 37 | 2026-05-14 |

---

#### docs/publication/ (4 files)

| File | Lines | Modified |
|------|-------|----------|
| docs_publication_readiness_report.md | 38 | 2026-05-15 |
| final_history_rewrite_branch_classification_report.md | 43 | 2026-05-14 |
| history_rewrite_force_push_plan.md | 53 | 2026-05-14 |
| history_rewrite_rehearsal_report.md | 19 | 2026-05-14 |

---

#### docs/schema/ (1 file)

| File | Lines | Modified |
|------|-------|----------|
| README.md | 68 | 2026-05-19 |

---

#### docs/setup/ (1 file)

| File | Lines | Modified |
|------|-------|----------|
| claude-code-hooks.md | 91 | 2026-05-22 |

---

#### docs/ (standalone reference files, 15 files)

| File | Lines | Modified | Aspirational |
|------|-------|----------|-------------|
| ARCHITECTURE.md | 48 | 2026-05-14 | NO |
| client-profile-schema.md | 53 | 2026-05-14 | NO |
| copilot-setup.md | 220 | 2026-05-14 | NO |
| coverage-report-phase6.md | 22 | 2026-05-14 | NO |
| cursor-setup.md | 119 | 2026-05-14 | NO |
| DECISION_QUERY_EXAMPLES.md | 159 | 2026-05-14 | NO |
| demo-disaster-prevention-scenario.md | 33 | 2026-05-14 | NO |
| demo-script.md | 206 | 2026-05-14 | NO |
| design-skills-guide.md | 206 | 2026-05-14 | NO |
| operator-guide.md | 26 | 2026-05-14 | NO |
| portfolio-case-study.md | 48 | 2026-05-14 | NO |
| quickstart.md | 39 | 2026-05-14 | NO |
| security-best-practices.md | 129 | 2026-05-14 | NO |
| security-orchestration-pattern.md | 178 | 2026-05-14 | NO |
| security-skills-redundancy-analysis.md | 292 | 2026-05-14 | NO |
| security-storage-layout.md | 97 | 2026-05-14 | NO |
| token-efficient-prompting.md | 432 | 2026-05-14 | NO |
| token-overhead.md | 21 | 2026-05-14 | NO |
| token-reduction-summary.md | 179 | 2026-05-14 | NO |
| UAT-Phase6-Checklist.md | 44 | 2026-05-14 | NO |

---

### Documentation Summary Statistics

| Category | File Count | Total Lines |
|---------|-----------|-------------|
| contracts/ | 34 | ~3,943 |
| architecture/ | 9 | ~1,303 |
| operations/ | 25 | ~2,933 |
| product/ | 7 | ~531 |
| audits/ | 2 | ~1,853 |
| demo/ | 5 | ~223 |
| pilot/ | 4 | ~384 |
| publication/ | 4 | ~153 |
| setup/ | 1 | 91 |
| authoring/ | 1 | 98 |
| schema/ | 1 | 68 |
| docs/ root standalone | 20+ | ~2,700+ |
| **Total** | **~124** | **~14,280+** |

**Files with aspirational markers (TODO/TBD/ASPIRATIONAL/NOT YET):** 3 confirmed
- `docs/contracts/file-structure-authority-policy.md`
- `docs/architecture/SYSTEM.md`
- `docs/UPGRADE_PLAN.md`

**Most recently modified (2026-05-22):** DATABASE.md, HOOK_RUNTIME.md, MIGRATION_AUTHORITY.md, PUBLICATION_BOUNDARY.md, WORKFLOW_RUNTIME.md, event-store.md, shared-authority-and-adapter-projections.md, contract-atlas.md, dream-studio-dashboard-projection-mapping.md, architecture/contract-atlas.md, operations/ (9 files), setup/claude-code-hooks.md

**Oldest unmodified files (2026-05-14):** Majority of docs/contracts/ (28 of 34), most docs/product/, docs/demo standalone files, security/*.md, token-*.md
