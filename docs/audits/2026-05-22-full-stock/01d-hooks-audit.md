# Pass 1d — Hooks Audit
*Phase 1 analysis | 2026-05-22*

---

## Stated Architectural Intents

| # | Intent |
|---|--------|
| 1 | **SQLite-first authority** — all runtime state must be SQLite-backed; file-based state is v1 rot |
| 2 | **Security audit during brownfield onboarding** — security skills run during project intake; findings stored in SQLite |
| 3 | **Security audit as SDLC lifecycle gate** — greenfield projects must pass security audit before going live |
| 4 | **Canonical events as the spine** — all state changes flow through `canonical_events`; direct table writes without event emission are anomalies |
| 5 | **Marker file authority for attribution** — `.dream-studio-project` markers are identity source; `ds_projects` is metadata storage |

---

## Dispatch Architecture

The 33 Python files in `runtime/hooks/` are NOT all registered directly with Claude Code. The actual hook chain is organized through four dispatcher entry points, plus two standalone hooks:

| Dispatcher / Hook | Trigger | Handlers dispatched |
|---|---|---|
| `.claude/hooks/run.py` | All 4 events | Emits canonical envelopes via `emitters.claude_code.emitter`; calls `spool.ingestor.ingest_pending` on Stop |
| `on-prompt-dispatch.py` | UserPromptSubmit | on-prompt-validate, on-session-start, on-first-run, on-memory-retrieve, on-milestone-start, on-context-threshold, on-pulse |
| `on-edit-dispatch.py` | PostToolUse Edit\|Write | on-agent-correction, on-game-validate, on-security-scan, on-structure-check |
| `on-stop-dispatch.py` | Stop | on-session-end, on-stop-handoff, on-quality-score, on-skill-telemetry, on-milestone-end, on-token-log, on-meta-review, on-workflow-progress, on-changelog-nudge |
| `on-tool-activity.py` | PostToolUse (all tools) | Standalone — not in any dispatcher |
| `on-post-tool-use.py` | PostToolUse (all tools) | Standalone shim → `core.telemetry.token_capture` |
| `on-post-compact.py` | PostCompact | Standalone |

Total individual handlers invoked: 22 unique handlers across 4 dispatcher chains + 3 standalones.

**Evidence from `hook-timing.jsonl` (3,636 entries, 2026-05-17 → 2026-05-22):**
- `on-tool-activity`: 1,202 invocations (PostToolUse)
- `on-session-start`: 241 | `on-first-run`: 241 | `on-milestone-start`: 241 (UserPromptSubmit chain)
- `on-prompt-validate`: 238 (UserPromptSubmit chain)
- `on-session-end`: 148 | `on-skill-telemetry`: 147 | `on-milestone-end`: 147 (Stop chain)
- `on-stop-handoff`: 146 | `on-quality-score`: 146 | `on-meta-review`: 146
- `on-changelog-nudge`: 147 | `on-workflow-progress`: 146
- `on-context-threshold`: 39 (UserPromptSubmit chain — rate-limited by threshold check)
- `on-post-compact`: 16 (PostCompact)
- Edit/Write chain handlers: 5 each (`on-agent-correction`, `on-game-validate`, `on-security-scan`, `on-structure-check`)

`hook_invocations` table: 917 rows, **all** attributed to `on-tool-activity` only — the `hook_invocations` table is written by the telemetry emitter in `core/telemetry/emitters.py`, not by the dispatcher chain. The other 22 handlers write timing to `hook-timing.jsonl` but not to `hook_invocations`.

---

## Hook Inventory and Assessment

### Meta Hooks (18)

#### `runtime/hooks/meta/on-prompt-dispatch.py`
- **Trigger:** UserPromptSubmit — dispatcher entry point
- **Purpose:** Replaces 6 subprocess invocations with one process; imports and calls 7 handlers sequentially via `execute_handlers`
- **Current state:** ACTIVE — 41 timing entries in `hook-timing.jsonl` (note: lower than the 241 entries for individual handlers because `on-prompt-dispatch` timing was added later than handlers it wraps)
- **Intent 1 (SQLite):** Does not write files directly; delegates to handlers
- **Intent 4 (Events):** Does not emit canonical events; emission is via `.claude/hooks/run.py` which runs independently for the same trigger
- **Output:** Timing entry in `hook-timing.jsonl` via `execute_handlers`
- **Notes:** The dispatch mechanism means `run.py` + `on-prompt-dispatch.py` both fire on UserPromptSubmit. `run.py` handles envelope emission; `on-prompt-dispatch.py` handles behavioral hooks. Separation is intentional but creates two code paths for the same trigger.

---

#### `runtime/hooks/meta/on-prompt-validate.py`
- **Trigger:** UserPromptSubmit (handler #1 in `on-prompt-dispatch`)
- **Purpose:** Validates user prompt for injection attempts; if `pending-handoff.json` exists and is fresh, injects the handoff skill instruction into the prompt and returns modified payload
- **Current state:** ACTIVE — 238 timing entries
- **Intent 1 (SQLite):** VIOLATE — reads and writes `pending-handoff.json` (file state). The pending handoff status (`pending` → `in_progress`) transitions are tracked in the JSON file, not in SQLite. No SQLite writes.
- **Intent 4 (Events):** SILENT — emits no canonical events
- **Output:** Modified prompt payload (stdout) when handoff pending; security warning text for injection attempts; file write to `pending-handoff.json`
- **Notes:** The `_VALIDATOR_AVAILABLE` flag — `rebuff_validator` import fails silently if not installed. The injection scanning is effectively dormant unless that optional dependency is present.

---

#### `runtime/hooks/meta/on-session-start.py`
- **Trigger:** UserPromptSubmit (handler #2 in `on-prompt-dispatch`)
- **Purpose:** Records new session row in `raw_sessions` on first prompt of a session; upserts project; writes `session_config` file for continuation spawner
- **Current state:** ACTIVE — 241 timing entries; 51 rows in `raw_sessions` (sentinel prevents double-write)
- **Intent 1 (SQLite):** PARTIAL ALIGN — writes to `raw_sessions` and `raw_sentinels` (SQLite). Also writes a `session_config` file via `write_session_config` (file-based). The session_config file is a transient coordination artifact for `on-context-threshold` continuation spawning — legitimate transient use, but file-based.
- **Intent 4 (Events):** DELEGATED — `system.session.recorded` events (51 in DB) are emitted by `core/event_store/studio_db.py::insert_session`, which calls `_write_envelopes` internally. The hook triggers the SQLite write which triggers the event — chain is intact but indirect.
- **Output:** SQLite rows in `raw_sessions` + `raw_sentinels` + `ds_projects`; session_config file
- **Notes:** `project_id = Path.cwd().name` — uses directory name as project ID, not the `ds_projects` UUID. This is a known loose attribution pattern.

---

#### `runtime/hooks/meta/on-first-run.py`
- **Trigger:** UserPromptSubmit (handler #3 in `on-prompt-dispatch`)
- **Purpose:** Checks if Director profile is configured; if not, prints onboarding prompt; always calls `hydrate_registry_once` to populate skill registry
- **Current state:** ACTIVE — 241 timing entries
- **Intent 1 (SQLite):** PARTIAL ALIGN — reads config JSON; `hydrate_registry_once` writes to SQLite registry tables (`reg_skills`, `reg_workflows`, etc.). No file writes from the hook body itself.
- **Intent 4 (Events):** SILENT — emits no canonical events
- **Output:** Console message if setup incomplete; registry hydration (SQLite side-effect via `hydrate_registry_once`)
- **Notes:** Fires every prompt for the full session lifetime — once `director_name` is set, it just sets `onboarding_mode` and returns. Cheap after first run.

---

#### `runtime/hooks/meta/on-memory-retrieve.py`
- **Trigger:** UserPromptSubmit (handler #4 in `on-prompt-dispatch`)
- **Purpose:** Searches `MEMORY.md` files for content relevant to the user prompt and injects matching snippets as `<relevant-context>` XML into context
- **Current state:** ACTIVE — 241 timing entries
- **Intent 1 (SQLite):** VIOLATE — writes `memory-last-score.json` (file state) containing the top relevance score from the last search. This score is used by `pulse_collector.py` but is not in SQLite.
- **Intent 4 (Events):** SILENT — emits no canonical events
- **Output:** Context injection (stdout XML); `memory-last-score.json` file
- **Notes:** Uses `MemorySearch` with FTS via `memory_fts` SQLite table. The search index is SQLite-backed, which is good. Only the result score escapes to a file.

---

#### `runtime/hooks/meta/on-context-threshold.py`
- **Trigger:** UserPromptSubmit (handler #6 in `on-prompt-dispatch`, after on-milestone-start)
- **Purpose:** At 75% context usage, writes `pending-handoff.json` and emits a harvest event to trigger continuation session spawning
- **Current state:** ACTIVE — 39 timing entries (rate-limited; only fires when threshold is crossed or bridge file exists)
- **Intent 1 (SQLite):** VIOLATE — writes `pending-handoff.json` (file). Spawn lock is written to `tempdir/claude-spawn-lock-{session_id}.json` (temp file). Bridge file read from `tempdir/claude-ctx-{session_id}.json` (temp file). None of these are SQLite.
- **Intent 4 (Events):** BROKEN — calls `spool.emitter.emit("ds_session_harvest", ...)` but `spool/emitter.py` does not exist in the repository. The `_emit_harvest` function silently fails every time. The `context.threshold.crossed` events in `canonical_events` (20 entries) are emitted by `.claude/hooks/run.py` → `emitters/claude_code/emitter.py::normalize_post_compact`, NOT by this hook.
- **Output:** `pending-handoff.json` file; spawn lock temp file; console message at threshold; no canonical events (broken emitter)
- **Notes:** This is a significant gap. The harvest event emission is completely silently broken. The handoff coordination depends entirely on file state.

---

#### `runtime/hooks/meta/on-pulse.py`
- **Trigger:** UserPromptSubmit (handler #7 in `on-prompt-dispatch`)
- **Purpose:** Runs `run_pulse_check()` (cross-project health check) and records the execution to `hook_executions`
- **Current state:** ACTIVE — 42 timing entries; 45 rows in `hook_executions` (the only hook writing to this table)
- **Intent 1 (SQLite):** ALIGN — writes to `hook_executions` table (SQLite). `run_pulse_check` also writes pulse files (`pulse-YYYY-MM-DD.md`, `pulse-latest.json`) to `~/.dream-studio/meta/` — those are file outputs.
- **Intent 4 (Events):** PARTIAL — `system.hook.execution.logged` (45 events in DB) are emitted by `insert_hook_execution` inside `on-pulse.py`. However, `hook_executions` is only populated by `on_pulse` — no other hook uses this table.
- **Output:** `hook_executions` row (SQLite); `system.hook.execution.logged` event (canonical); pulse MD + JSON files (meta/)
- **Notes:** `on_pulse` uses underscore name in `hook_executions` while all other hooks use hyphen names in `hook_invocations`. Minor inconsistency.

---

#### `runtime/hooks/meta/on-session-end.py`
- **Trigger:** Stop (handler #1 in `on-stop-dispatch`)
- **Purpose:** Closes the session row in `raw_sessions` with token counts; calls `validate_session_research` to check for unfiled research
- **Current state:** ACTIVE — 148 timing entries; 33 `system.session.closed` events in DB
- **Intent 1 (SQLite):** ALIGN — writes to `raw_sessions` via `end_session`; reads/writes `raw_sentinels` for dedup
- **Intent 4 (Events):** DELEGATED — `system.session.closed` (33 events) emitted by `studio_db.end_session` internally. Chain is intact.
- **Output:** `raw_sessions` close (SQLite); `system.session.closed` event
- **Notes:** `input_tokens` / `output_tokens` are only populated if `prompt_tokens` key is present in the payload. In practice the Stop event from Claude Code may not carry these — the `token_usage_records` table has 0 rows, suggesting token attribution at session-close is not landing.

---

#### `runtime/hooks/meta/on-token-log.py`
- **Trigger:** Stop (handler #6 in `on-stop-dispatch`)
- **Purpose:** Appends session token usage to `~/.dream-studio/meta/token-log.md`
- **Current state:** ACTIVE — 146 timing entries
- **Intent 1 (SQLite):** VIOLATE — writes exclusively to `token-log.md` file (markdown). No SQLite writes.
- **Intent 4 (Events):** SILENT — emits no canonical events. Prints a JSON status object to stdout.
- **Output:** `~/.dream-studio/meta/token-log.md` file append
- **Notes:** Pure file-based token accounting with no SQLite equivalent. `raw_token_usage` table exists and has 3 rows (written by `on-skill-metrics` via `insert_token_usage`), but `on-token-log` doesn't use it. Dual-track token logging exists with divergent persistence.

---

#### `runtime/hooks/meta/on-skill-load.py`
- **Trigger:** PostToolUse (Read tool on skill `.md` files) — watches for Read tool calls matching `skills/.../*.md`
- **Purpose:** Prints "Skill loaded: {name}" to context; logs to `skill-usage.log`; resolves `{{director_name}}` placeholder
- **Current state:** ACTIVE (conditional) — fires on PostToolUse events matching Read + skill path pattern. Not in any dispatcher; must be registered directly or via `on-tool-activity` routing (unclear)
- **Intent 1 (SQLite):** VIOLATE — writes to `~/.dream-studio/meta/skill-usage.log` (text file). No SQLite writes.
- **Intent 4 (Events):** SILENT — emits no canonical events
- **Output:** Console message; `skill-usage.log` file append
- **Notes:** There is no timing entry for `on-skill-load` in `hook-timing.jsonl`, meaning it is NOT being dispatched through the current dispatcher chain. It may be independently registered in `settings.json`, or it may be dead in practice. The `skill-usage.log` output is distinct from `skill-usage.jsonl` written by `on-skill-metrics`.

---

#### `runtime/hooks/meta/on-skill-metrics.py`
- **Trigger:** PostToolUse (Skill tool calls) — fires when `tool_name` matches the Skill tool
- **Purpose:** Appends skill usage record to `skill-usage.jsonl`; writes a zero-token row to `raw_token_usage`
- **Current state:** ACTIVE (conditional) — 3 rows in `raw_token_usage` matching; but no timing entry in `hook-timing.jsonl`. Same status as `on-skill-load` — either independently registered or dormant.
- **Intent 1 (SQLite):** PARTIAL ALIGN — calls `insert_token_usage` → `raw_token_usage` (SQLite). Also writes to `skill-usage.jsonl` (file).
- **Intent 4 (Events):** SILENT — no canonical events emitted
- **Output:** `skill-usage.jsonl` file append; `raw_token_usage` row (SQLite)
- **Notes:** The 3 `raw_token_usage` rows all have `input_tokens=0` and `output_tokens=0` — token values are hardcoded to 0 because the Skill tool payload does not carry token usage. Schema-inconsistency in `skill-usage.jsonl` noted in Pass 0b: the `session` field is empty string, `mode` is empty string, and `skill` is always "unknown" — indicating `skill_name` extraction from the payload fails in practice.

---

#### `runtime/hooks/meta/on-skill-complete.py`
- **Trigger:** PostToolUse (Skill tool) — fires after a skill invocation completes
- **Purpose:** Records skill execution to `activity_log` via `log_skill_execution`; calls `record_outcome` for calibration; calls `process_chain_suggests` to display next-step suggestions
- **Current state:** UNKNOWN — no timing entry in `hook-timing.jsonl`. Not in any dispatcher. Either independently registered or dead.
- **Intent 1 (SQLite):** ALIGN (intended) — `log_skill_execution` writes to SQLite. `record_outcome` writes to `outcome_records`.
- **Intent 4 (Events):** SILENT — no canonical events emitted
- **Output:** SQLite writes (when called); console chain suggestions
- **Notes:** `skill_invocations` table has 1 row — matches `on-skill-complete` being rarely or never active. The `skill.invoked` events (21) come from `core/skills/invocation.py`, not from this hook.

---

#### `runtime/hooks/meta/on-skill-telemetry.py`
- **Trigger:** Stop (handler #4 in `on-stop-dispatch`)
- **Purpose:** Reads `skill-usage.jsonl` for the current session; writes aggregated skill telemetry to `telemetry-buffer.jsonl`
- **Current state:** ACTIVE — 147 timing entries; 1 row in `telemetry-buffer.jsonl`
- **Intent 1 (SQLite):** VIOLATE — reads `skill-usage.jsonl` (file); writes `telemetry-buffer.jsonl` (file). The buffer is consumed by `pulse_collector.py` but has no SQLite ingest path.
- **Intent 4 (Events):** SILENT — emits no canonical events
- **Output:** `telemetry-buffer.jsonl` file append
- **Notes:** The telemetry buffer is a double file dependency: `skill-usage.jsonl` (input) → `telemetry-buffer.jsonl` (output). Neither is SQLite. `raw_skill_telemetry` table exists (0 rows) but is not used by this hook.

---

#### `runtime/hooks/meta/on-meta-review.py`
- **Trigger:** Stop (handler #7 in `on-stop-dispatch`)
- **Purpose:** Performs weekly retrospective across recent sessions; generates `review-YYYY-MM-DD.md`; drafts theme lessons; prints escalation candidates
- **Current state:** ACTIVE — 146 timing entries; 3 pulse `.md` files in `~/.dream-studio/meta/`
- **Intent 1 (SQLite):** VIOLATE — reads `token-log.md` via `parse_token_log` (file); reads session context from files; writes `review-YYYY-MM-DD.md` (file). No SQLite reads or writes.
- **Intent 4 (Events):** SILENT — emits no canonical events
- **Output:** `~/.dream-studio/meta/review-YYYY-MM-DD.md` (file); draft lessons in `~/.dream-studio/meta/draft-lessons/`
- **Notes:** Depends on `token-log.md` as primary input, which itself is a file-only artifact from `on-token-log`. This creates a file-dependency chain: `on-token-log` writes the log → `on-meta-review` reads it. Both are SQLite-free. `raw_sessions` is not used as input here despite having the same data.

---

#### `runtime/hooks/meta/on-post-compact.py`
- **Trigger:** PostCompact
- **Purpose:** Resets the context bridge file and clears sentinels so context warnings fire fresh after `/compact`
- **Current state:** ACTIVE — 16 timing entries
- **Intent 1 (SQLite):** PARTIAL ALIGN — `clear_sentinels` writes to `raw_sentinels` (SQLite). `reset_context_bridge` writes to `tempdir/claude-ctx-{session_id}.json` (temp file).
- **Intent 4 (Events):** SILENT — emits no canonical events. Prints a JSON status object. The `context.threshold.crossed` events in the DB come from `run.py::normalize_post_compact` independently.
- **Output:** `raw_sentinels` rows (SQLite); temp bridge file reset; JSON status stdout
- **Notes:** The `context.threshold.crossed` event emission happens in `run.py`, not here. These two hooks fire for the same PostCompact trigger but are completely uncoordinated — `on-post-compact` doesn't know `run.py` already emitted the event.

---

#### `runtime/hooks/meta/on-stop-dispatch.py`
- **Trigger:** Stop — dispatcher entry point
- **Purpose:** Dispatches 9 Stop handlers sequentially; writes timing via `write_timing`; calls `_dispatch_handoff_continuation` to spawn new session if handoff present
- **Current state:** ACTIVE — 141 timing entries
- **Intent 1 (SQLite):** Does not write files directly; delegates to handlers; reads `handoff-latest.json` and `pending-handoff.json` in `_dispatch_handoff_continuation`
- **Intent 4 (Events):** Does not emit directly; delegates to handlers
- **Output:** Timing entries in `hook-timing.jsonl` for each handler; session spawn if handoff present
- **Notes:** `_dispatch_handoff_continuation` reads both handoff JSON files and calls `_spawn_new_session`. If handoff coordination were SQLite-based, this function would not need to read files.

---

#### `runtime/hooks/meta/on-edit-dispatch.py`
- **Trigger:** PostToolUse Edit|Write — dispatcher entry point
- **Purpose:** Dispatches 4 Edit/Write handlers; guards against protected path writes (settings.json, CLAUDE.md)
- **Current state:** ACTIVE — 20 PostToolUse_Edit_Write timing entries
- **Intent 1 (SQLite):** Protected path guard is purely in-memory; delegates to handlers
- **Intent 4 (Events):** Does not emit directly
- **Output:** Delegates to 4 handlers
- **Notes:** Protected path guard runs before any handler — correct defensive pattern.

---

### Core Hooks (6)

#### `runtime/hooks/core/on-milestone-start.py`
- **Trigger:** UserPromptSubmit (handler #5 in `on-prompt-dispatch`)
- **Purpose:** Writes `milestone-active.txt` marker when a DCL command matching build/deploy pattern is detected in the user prompt
- **Current state:** ACTIVE — 241 timing entries (fires every prompt; returns early if no DCL command)
- **Intent 1 (SQLite):** VIOLATE — writes `~/.dream-studio/state/milestone-active.txt` (file marker). No SQLite writes.
- **Intent 4 (Events):** SILENT — emits no canonical events
- **Output:** `milestone-active.txt` file (conditional)
- **Notes:** This file marker is the trigger for `on-quality-score` and `on-milestone-end`. The milestone lifecycle (start → end) is entirely file-based. `ds_milestones` table exists in SQLite but is not used by this hook.

---

#### `runtime/hooks/core/on-milestone-end.py`
- **Trigger:** Stop (handler #5 in `on-stop-dispatch`)
- **Purpose:** Loads and clears `milestone-active.txt`; appends to `milestone-log.md`; prints checkpoint; drafts retrospective lesson if milestone ran long
- **Current state:** ACTIVE — 147 timing entries (fires every Stop; returns early if no marker)
- **Intent 1 (SQLite):** VIOLATE — reads/deletes `milestone-active.txt` (file); writes `~/.dream-studio/meta/milestone-log.md` (file). Lesson drafts go to `~/.dream-studio/meta/draft-lessons/` (files). No SQLite writes.
- **Intent 4 (Events):** SILENT — emits no canonical events
- **Output:** `milestone-active.txt` deletion; `milestone-log.md` append (file); draft lesson files
- **Notes:** Complete file-only lifecycle. `ds_milestones` table is populated by the CLI (`py -m interfaces.cli.ds milestone ...`), not by these hooks. The hook-tracked milestones and the CLI-tracked milestones are parallel, non-integrated systems.

---

#### `runtime/hooks/core/on-stop-handoff.py`
- **Trigger:** Stop (handler #2 in `on-stop-dispatch`)
- **Purpose:** Checks for session git activity; if active, writes a handoff markdown file and records the session to `raw_handoffs` (SQLite) via `record_session_to_db`
- **Current state:** ACTIVE — 146 timing entries; 26 rows in `raw_handoffs`; 26 `system.handoff.created` events
- **Intent 1 (SQLite):** ALIGN — `record_session_to_db` writes to `raw_handoffs`, `raw_sessions`, and `ds_projects` (SQLite). Also writes a `.sessions/handoff-{session}.md` file (markdown). The SQLite write is canonical; the markdown is a human-readable companion.
- **Intent 4 (Events):** DELEGATED — `system.handoff.created` (26 events) are emitted inside `studio_db.insert_handoff`. The 26 rows in `raw_handoffs` exactly match the 26 canonical events — chain is intact.
- **Output:** `raw_handoffs` row (SQLite); `system.handoff.created` event; `.sessions/handoff-*.md` file
- **Notes:** Best-aligned core hook with Intent #1 and #4. The `.sessions/handoff-*.md` markdown file is a secondary artifact from the SQLite-primary write.

---

#### `runtime/hooks/core/on-workflow-progress.py`
- **Trigger:** Stop (handler #8 in `on-stop-dispatch`)
- **Purpose:** Read-only reporter — loads `workflows.json` and prints active workflow status
- **Current state:** ACTIVE — 146 timing entries
- **Intent 1 (SQLite):** N/A (read-only). Reads `~/.dream-studio/state/workflows.json` — explicitly documented as written by Chief-of-Staff, not by this hook.
- **Intent 4 (Events):** SILENT — emits no canonical events (intentional — read-only)
- **Output:** Console status message (conditional); no writes
- **Notes:** `workflows.json` itself is file state (Intent #1 violation). The `workflow.node.completed` events (25) and `workflow.completed` (2) in `canonical_events` come from `control/execution/workflow/runner.py`, not from this hook.

---

#### `runtime/hooks/core/on-changelog-nudge.py`
- **Trigger:** Stop (handler #9 in `on-stop-dispatch`)
- **Purpose:** Checks `git status`; if source files changed but `CHANGELOG.md` was not touched, prints an advisory nudge
- **Current state:** ACTIVE — 147 timing entries
- **Intent 1 (SQLite):** N/A — advisory only, no state writes
- **Intent 4 (Events):** SILENT — emits no canonical events (advisory by design)
- **Output:** Console nudge (conditional); no writes
- **Notes:** Clean advisory hook. No state concerns.

---

#### `runtime/hooks/core/on-post-tool-use.py`
- **Trigger:** PostToolUse (standalone shim, all tools)
- **Purpose:** Delegates to `core.telemetry.token_capture.handle_post_tool_use`; emits `token.consumed` canonical events via spool; logs to `token-capture.jsonl` diagnostic on failure
- **Current state:** ACTIVE — no timing entry (not in dispatcher chain; must be independently registered). 7 `token.consumed` events in `canonical_events`. `token-capture.jsonl` has 14 performance diagnostic entries.
- **Intent 1 (SQLite):** ALIGN — `token.consumed` events land in `canonical_events` (SQLite) via spool ingestor. `token-capture.jsonl` is a diagnostic log only.
- **Intent 4 (Events):** ALIGN — `token.consumed` (7 events) are the target canonical event type for token attribution. Events carry `hook_id`, `tool_id`, `session_id` trace.
- **Output:** `canonical_events` rows (SQLite via spool); `token-capture.jsonl` diagnostic
- **Notes:** This is the most Intent #4-aligned hook in the codebase. The 7 events are recent (2026-05-22), suggesting this hook was added or activated recently during the token attribution workstream (ta3/ta6). `token_usage_records` table (0 rows) is a different table — not written by this path.

---

### Quality Hooks (4)

#### `runtime/hooks/quality/on-security-scan.py`
- **Trigger:** PostToolUse Edit|Write (handler #3 in `on-edit-dispatch`)
- **Purpose:** Scans newly written/edited file content for high-signal security anti-patterns; prints advisory warning
- **Current state:** ACTIVE (rarely triggered) — 5 timing entries; `security_findings` table: 0 rows; `sec_hook_checks` table: 0 rows; `hook_findings` table: 0 rows
- **Intent 1 (SQLite):** VIOLATE — does not write to SQLite at all. Findings are printed to stdout only. The `sec_hook_checks`, `hook_findings`, and `security_findings` tables all exist and are schema-compatible with persisting findings, but this hook does not use them.
- **Intent 2 (Security intake):** UNMET — this hook is not invoked during project intake/onboarding. It fires only on active Edit/Write operations.
- **Intent 3 (Security gate):** UNMET — this hook is advisory only and cannot block. It prints warnings but has no mechanism to enforce a gate. No findings are stored, so no gate can query them.
- **Intent 4 (Events):** SILENT — emits no canonical events
- **Output:** Console warning text (conditional); no SQLite writes; no canonical events
- **Notes:** See detailed analysis in the Special Focus section below.

---

#### `runtime/hooks/quality/on-agent-correction.py`
- **Trigger:** PostToolUse Edit|Write (handler #1 in `on-edit-dispatch`)
- **Purpose:** Detects writes to `director-corrections.md`; extracts the newest correction; logs to `corrections.log`; drafts lessons when patterns repeat 3+ times
- **Current state:** ACTIVE (rarely triggered) — 5 timing entries; returns early unless the written file is `director-corrections.md`
- **Intent 1 (SQLite):** VIOLATE — writes to `~/.dream-studio/meta/corrections.log` (file); draft lessons to `~/.dream-studio/meta/draft-lessons/` (files). No SQLite writes.
- **Intent 4 (Events):** SILENT — emits no canonical events
- **Output:** `corrections.log` file append; draft lesson files
- **Notes:** The `cor_skill_corrections` table exists in SQLite (schema matches the correction data model) but is not written by this hook. A SQLite-first implementation would write there.

---

#### `runtime/hooks/quality/on-quality-score.py`
- **Trigger:** Stop (handler #3 in `on-stop-dispatch`)
- **Purpose:** Checks if `milestone-active.txt` exists; if so, runs git-diff quality analysis; prints report; writes `quality-score.json` and appends to `quality-log.md`
- **Current state:** ACTIVE — 146 timing entries; returns early unless milestone marker exists (5 times `on-edit-dispatch` fired suggests milestone was active occasionally)
- **Intent 1 (SQLite):** VIOLATE — reads `milestone-active.txt` (file dependency); writes `~/.dream-studio/meta/quality-score.json` (file); appends `~/.dream-studio/meta/quality-log.md` (file). No SQLite writes.
- **Intent 4 (Events):** SILENT — emits no canonical events
- **Output:** `quality-score.json` (file); `quality-log.md` append (file)
- **Notes:** `quality-score.json` is read by `control/execution/workflow/engine.py` — a production code path depending on file state. The `project_health_scorecards` and `production_readiness_findings` tables exist in SQLite but are not used by this hook.

---

#### `runtime/hooks/quality/on-structure-check.py`
- **Trigger:** PostToolUse Write only (handler #4 in `on-edit-dispatch`)
- **Purpose:** Checks if newly-created source files (`*.py`, `*.ts`, `*.js`) are placed outside standard directories; emits advisory nudge once per violation pattern
- **Current state:** ACTIVE (rarely triggered) — 5 timing entries; dedup via `emit_nudge_once` writes a sentinel
- **Intent 1 (SQLite):** PARTIAL ALIGN — `emit_nudge_once` uses `raw_sentinels` (SQLite) to deduplicate nudges. No other SQLite writes.
- **Intent 4 (Events):** SILENT — emits no canonical events
- **Output:** Console nudge (conditional); `raw_sentinels` row (SQLite for dedup)
- **Notes:** SQLite is used correctly here for idempotency. Findings are advisory only.

---

### Domain Hooks (1)

#### `runtime/hooks/domains/on-game-validate.py`
- **Trigger:** PostToolUse Edit|Write (handler #2 in `on-edit-dispatch`)
- **Purpose:** Validates game project files (syntax, asset refs) when the `domains` pack is active
- **Current state:** ACTIVE (rarely triggered) — 5 timing entries; gate-check via `pack_context.is_pack_active("domains")`
- **Intent 1 (SQLite):** N/A — no state writes; read-only check
- **Intent 4 (Events):** SILENT — emits no canonical events (but can block via `sys.exit(2)` for critical violations)
- **Output:** Console output if violations found; blocking exit code 2 for `should_block` findings
- **Notes:** The only hook that can block execution (exit code 2). No evidence of blocking in the run history (5 firings, 0 blocks inferred from timing).

---

## Special Focus: File-Based Hook Outputs

### `hook-timing.jsonl` (391KB, 3,636 lines)
- **Written by:** `control/execution/dispatch_helpers.py::write_timing` (called from `on-stop-dispatch.py` and `control/execution/dispatch_tracking.py::execute_handlers`)
- **Contents:** `{event, handler, duration_ms, ts}` per handler invocation
- **Intent #1 assessment:** VIOLATE — this is runtime state (hook execution history) that is stored in a JSONL file but not in SQLite. `hook_executions` table exists and has the correct schema but is only populated by `on-pulse`. All 3,636 timing records from the dispatcher chain have no SQLite equivalent.
- **Readers:** No production code reads this file; it is effectively write-only diagnostic output
- **SQLite equivalent:** `hook_executions` table — schema matches perfectly (hook_name, hook_type, started_at, completed_at, duration_ms, exit_code, status)
- **Assessment:** High-value data stranded in a file

---

### `skill-usage.jsonl` (366 bytes, 3 lines)
- **Written by:** `control/skills/metrics.py::write_skill_usage` (called from `on-skill-metrics`)
- **Contents:** `{ts, skill, mode, session, recommended_model}`
- **Intent #1 assessment:** VIOLATE — this is operational skill usage state in a file
- **Schema inconsistency (from Pass 0b):** All 3 records have `skill="unknown"` and `session=""` — skill name extraction from the Skill tool payload fails. The data is structurally present but semantically empty.
- **Readers:** `on-skill-telemetry` reads this file to build `telemetry-buffer.jsonl`; `control/skills/completion.py` reads it for chain suggest logic
- **SQLite equivalent:** `raw_skill_telemetry` table (0 rows) — exists but not populated by this path

---

### `telemetry-buffer.jsonl` (91 bytes, 1 line)
- **Written by:** `core/telemetry/processor.py::write_telemetry` (called from `on-skill-telemetry`)
- **Contents:** `{skill_name, invoked_at, success}` — aggregated from `skill-usage.jsonl` at session end
- **Intent #1 assessment:** VIOLATE — a derived aggregate stored in a file
- **Readers:** `interfaces/cli/pulse_collector.py` reads and clears this buffer during pulse check
- **SQLite equivalent:** `raw_skill_telemetry` table — exact structural match. The buffer pattern is itself a v1 artifact; the correct flow is: hook → SQLite row directly.

---

### `token-capture.jsonl` (in `state/diagnostics/`, 3,690 bytes, ~14 lines)
- **Written by:** `core/telemetry/diagnostics.py::log_diagnostic` (called from `token_capture.handle_post_tool_use`)
- **Contents:** `{ts, category:"performance", source, machine_id, session_id, context:{step}, duration_ms}`
- **Intent #1 assessment:** DIAGNOSTIC — this is performance timing data, not runtime state. Intentionally separate from canonical state. Acceptable as diagnostic.
- **Assessment:** Not a violation of Intent #1. Correctly scoped as diagnostic-only.

---

### `activity.json` (258 bytes)
- **Written by:** `core/telemetry/tool_tracking.py::update_activity_feed` (called from `on-tool-activity`)
- **Contents:** `{agents:[{id, name, status, task, elapsed, ts}], timestamp}` — rolling window of recent tool activity for dashboard display
- **Intent #1 assessment:** BORDERLINE — this is a dashboard display feed, not canonical state. The current content reflects `Write: _audit_tmp.py` with `status: running` — indicating the file is a snapshot of the live agent view, not a permanent record.
- **Readers:** Dream Studio dashboard (`ds_dashboard.py`) reads this for live agent status display
- **Assessment:** Reasonable as an ephemeral display cache. However, the `hook.tool_activity` canonical events (257 in DB) provide a durable record of the same information. The file is a real-time cache; the canonical events are the authority.

---

### `pending-handoff.json` (164 bytes)
- **Written by:** `on-context-threshold.py::_write_pending_handoff`; mutated by `on-prompt-validate.py::_check_pending_handoff`
- **Contents:** `{session_id, triggered_at, cwd, invocation_flags, status:"in_progress"}`
- **Intent #1 assessment:** VIOLATE — this is transient coordination state (pending handoff trigger → prompt injection → session spawn) stored in a file. The `status` field transitions (pending → in_progress → consumed) are not tracked in SQLite.
- **Current state:** File exists with `status: in_progress` from session `dd1a4f73` (a prior session) — the file is stale. This indicates the cleanup path in `on-stop-dispatch::_dispatch_handoff_continuation` did not run (likely because `handoff-latest.json` was never written by the model).
- **Assessment:** File is both a coordination channel and a potential stale-state leak

---

### `workflow-checkpoint.json` and `workflows.json`
- **Written by:** Chief-of-Staff skill execution (not by hooks). `on-workflow-progress` reads these but explicitly does not write them.
- **`workflows.json`:** `{schema_version, active_workflows:{}}` — currently empty active_workflows
- **`workflow-checkpoint.json`:** `{workflow_key:"wf-fail-1", last_node:"n1", status:"failed", timestamp}` — stale failed workflow checkpoint
- **Intent #1 assessment:** VIOLATE — workflow execution state stored in files. `raw_workflow_runs` and `raw_workflow_nodes` tables exist in SQLite with compatible schemas.
- **Assessment:** Files owned by skill execution layer (not hooks). Hook is correctly read-only here. The underlying state storage is the violation, not the hook.

---

### `.sessions/handoff-*.md` and `recap-*.md`
- **Written by:** `control/context/handoff.py::write_session_handoff` (called from `on-stop-handoff`)
- **Contents:** Structured markdown handoff documents with branch, commits, tasks, decisions
- **Intent #1 assessment:** COMPANION — `raw_handoffs` SQLite row is written first (canonical); the markdown is a human-readable companion. The markdown exists in addition to, not instead of, the SQLite record.
- **Assessment:** Acceptable secondary artifact. The SQLite row is authoritative; the file is a projection.

---

### `~/.dream-studio/meta/token-log.md`
- **Written by:** `on-token-log` (Stop chain)
- **Contents:** Markdown table of per-session token usage
- **Intent #1 assessment:** VIOLATE — session token accounting stored only in a file. `raw_token_usage` has 3 rows but those are from `on-skill-metrics` (skill-level, not session-level). `raw_sessions.input_tokens` / `raw_sessions.output_tokens` are mostly NULL. Token log data has no SQLite equivalent.

---

### `~/.dream-studio/state/milestone-active.txt`
- **Written by:** `on-milestone-start`; deleted by `on-milestone-end`
- **Contents:** Milestone start timestamp + command
- **Intent #1 assessment:** VIOLATE — milestone lifecycle state stored in a file. `ds_milestones` table exists in SQLite. This is a parallel, disconnected milestone tracking system running entirely in files.

---

## Special Focus: Silent Hooks

Hooks that fire but produce NO canonical events:

| Hook | Fires Per | Invocations | What it produces instead |
|------|-----------|-------------|--------------------------|
| `on-prompt-validate` | Every prompt | 238 | Modified prompt payload (stdout); file write |
| `on-first-run` | Every prompt | 241 | Console text; SQLite registry hydration (side-effect) |
| `on-memory-retrieve` | Every prompt | 241 | Context XML (stdout); `memory-last-score.json` file |
| `on-context-threshold` | Per prompt (rate-limited) | 39 | `pending-handoff.json` file; console message; broken spool emit |
| `on-pulse` | Every prompt | 42 | `hook_executions` row; `system.hook.execution.logged`; pulse files |
| `on-token-log` | Every stop | 146 | `token-log.md` file |
| `on-skill-telemetry` | Every stop | 147 | `telemetry-buffer.jsonl` file |
| `on-meta-review` | Every stop | 146 | `review-YYYY-MM-DD.md` file; draft lessons |
| `on-milestone-start` | Every prompt | 241 | `milestone-active.txt` file (conditional) |
| `on-milestone-end` | Every stop | 147 | File deletion; `milestone-log.md` append (conditional) |
| `on-changelog-nudge` | Every stop | 147 | Console nudge only |
| `on-workflow-progress` | Every stop | 146 | Console status only |
| `on-security-scan` | Edit/Write | 5 | Console warning only |
| `on-agent-correction` | Edit/Write | 5 | `corrections.log` file; draft lessons |
| `on-quality-score` | Every stop | 146 | `quality-score.json` + `quality-log.md` files (conditional) |
| `on-structure-check` | Write only | 5 | Console nudge; `raw_sentinels` row (SQLite dedup only) |
| `on-game-validate` | Edit/Write | 5 | Console output; possible exit(2) block |
| `on-skill-load` | PostToolUse Read | 0 (dormant) | `skill-usage.log` file |
| `on-skill-complete` | PostToolUse Skill | 0 (unknown) | SQLite + console (when active) |
| `on-post-compact` | PostCompact | 16 | Sentinel clear (SQLite); temp file reset |

Of 22 active handlers, **20 emit no canonical events**. Only `on-stop-handoff` (via `insert_handoff`) and `on-post-tool-use` (via `token_capture`) produce canonical events, and both do so indirectly through library calls.

The two hooks that DO produce canonical events indirectly:
- `on-stop-handoff` → `studio_db.insert_handoff` → `system.handoff.created`
- `on-post-tool-use` → `token_capture.handle_post_tool_use` → `token.consumed`

`on-session-start` and `on-session-end` produce canonical events via `studio_db.insert_session` / `end_session` → `system.session.recorded` / `system.session.closed` — also indirect.

**Assessment for Intent #4:** The pattern of event emission through SQLite DB functions (which internally emit) is consistent and correct where it exists. The problem is that most hooks bypass the canonical event spine entirely.

---

## Special Focus: on-security-scan.py

**Location:** `runtime/hooks/quality/on-security-scan.py`
**Trigger:** PostToolUse Edit|Write (handler #3 in `on-edit-dispatch`)
**Invocations:** 5 timing entries in `hook-timing.jsonl`

### What it does
1. Reads stdin PostToolUse payload
2. Filters to Edit and Write tool calls only
3. Calls `security_patterns.extract_content(payload)` — extracts `file_path` and `content` from the payload
4. Calls `security_patterns.should_scan(file_path)` — applies file extension and path filters
5. If scanned: calls `security_patterns.scan_for_patterns(content)` — regex-based pattern matching for hardcoded secrets, dangerous functions, SQL injection patterns, etc.
6. If findings: calls `security_patterns.print_warning(file_path, findings)` — prints formatted warning to stdout

### What it writes
- **Stdout only:** Console warning text. No file writes. No SQLite writes.

### SQLite interaction
- **None.** `sec_hook_checks`: 0 rows. `hook_findings`: 0 rows. `security_findings`: 0 rows. `sec_sarif_findings`: 0 rows.
- The SQLite tables `sec_hook_checks` and `hook_findings` both have `hook_exec_id` FK columns that would link to `hook_executions` — the schema anticipates hook findings being stored, but the implementation does not write them.

### Intent #2 (Security intake during brownfield onboarding)
**UNMET.** The hook fires on Edit/Write during any session — it does not have any awareness of whether a project is being onboarded or is in brownfield intake. There is no intake-specific invocation path. The `project_intake_records` table exists but is not consulted.

### Intent #3 (Security gate before go-live)
**UNMET.** The hook is advisory only (`never blocks` is stated in the docstring). It cannot prevent a deployment. There is no mechanism to accumulate findings across a session and block a gate check. The `production_readiness_findings` and `production_readiness_assessment_runs` tables exist but this hook does not write to them.

### Current activity
With only 5 firing events (the `on-edit-dispatch` Edit/Write chain fires 5 times) and no scanned findings stored, this hook has effectively been advisory-only since creation. The security scanning surface (`ds-security` skill pack) provides deeper scanning as a separate code path and does write to `sec_sarif_findings` and `security_findings` via the skill execution path — but that is unrelated to this hook.

---

## Hook → canonical_events Tracing

| canonical_events event_type | Count | Emitted by | Hook / path |
|---|---|---|---|
| `tool.execution.completed` | 822 | `.claude/hooks/run.py` → `emitters/claude_code/emitter.py::normalize_post_tool_use` | PostToolUse — independent of hook dispatcher chain |
| `hook.tool_activity` | 257 | `core/telemetry/emitters.py::emit_tool_activity_event` | Called from `on-tool-activity` → `tool_tracking.update_activity_feed` → telemetry emitter |
| `prompt.lifecycle.submitted` | 250 | `run.py` → `emitters/claude_code/emitter.py::normalize_user_prompt_submit` | UserPromptSubmit — run.py independent path |
| `token.consumption.recorded` | 181 | `run.py` → `emitters/claude_code/emitter.py::normalize_stop` | Stop — run.py independent path |
| `event.validation.failed` | 57 | Spool ingestor (`spool/ingestor.py`) validation | Emitted when schema validation rejects `execution.completed` events (now-fixed event type issue, no new failures after 2026-05-19) |
| `system.session.recorded` | 51 | `core/event_store/studio_db.py::insert_session` | Called from `on-session-start` |
| `system.hook.execution.logged` | 45 | `core/event_store/studio_db.py::insert_hook_execution` | Called from `on-pulse` only |
| `system.session.closed` | 33 | `core/event_store/studio_db.py::end_session` | Called from `on-session-end` |
| `system.handoff.created` | 26 | `core/event_store/studio_db.py::insert_handoff` | Called from `on-stop-handoff` via `record_session_to_db` |
| `workflow.node.completed` | 25 | `control/execution/workflow/runner.py` | Skill execution path (not hooks) |
| `skill.invoked` | 21 | `core/skills/invocation.py` | CLI / skill invocation path (not hooks) |
| `context.threshold.crossed` | 20 | `run.py` → `emitters/claude_code/emitter.py::normalize_post_compact` | PostCompact — not from `on-context-threshold` (broken) |
| `work_order.started` | 15 | CLI (`interfaces/cli/ds.py`) | Not hooks |
| `work_order.created` | 14 | CLI | Not hooks |
| `task.created` | 9 | CLI | Not hooks |
| `token.consumed` | 7 | `on-post-tool-use` → `token_capture.handle_post_tool_use` → spool | PostToolUse hook — most recent, ta3 workstream |
| `milestone.created` | 4 | CLI | Not hooks |
| `task.completed` | 4 | CLI | Not hooks |
| `work_order.closed` | 4 | CLI | Not hooks |
| `gate.bypassed` | 3 | CLI | Not hooks |
| `project.created` | 3 | CLI | Not hooks |
| `workflow.completed` | 2 | CLI / workflow runner | Not hooks |

**Key observation:** The highest-volume canonical events (`tool.execution.completed` 822, `prompt.lifecycle.submitted` 250, `token.consumption.recorded` 181) are all emitted by `run.py` — the spool entry point that runs independently of the dispatcher chain. The dispatcher chain hooks contribute a much smaller fraction of canonical events and almost exclusively through indirect SQLite function calls.

---

## Findings

### F1: Two parallel telemetry channels at the same trigger
`run.py` and `on-prompt-dispatch.py` (plus `on-tool-activity.py`) all fire at UserPromptSubmit/PostToolUse. `run.py` writes canonical envelopes via the spool. The dispatch chain hooks write file artifacts and SQLite rows via library calls. These two paths are uncoordinated — neither knows what the other wrote. The result is partial duplication (both record session starts, tool uses) and partial divergence (only one records token counts, only one records handoffs).

### F2: `hook-timing.jsonl` is the de facto hook execution log
3,636 records of hook invocations exist in `hook-timing.jsonl` but zero records in `hook_executions` (except the 45 `on_pulse` rows). The intended SQLite-backed hook execution audit trail does not exist. `hook_executions` is populated only by one hook.

### F3: `spool.emitter` module is missing — on-context-threshold harvest is silently broken
`on-context-threshold.py` calls `from spool.emitter import emit` but `spool/emitter.py` does not exist. The `_emit_harvest` function always silently fails. The 20 `context.threshold.crossed` canonical events come from PostCompact events via `run.py`, not from actual threshold crossings in `on-context-threshold`.

### F4: Handoff coordination is entirely file-based with observable stale state
The `pending-handoff.json` file (Intent #1 violation) currently contains stale state (`status: in_progress`, session `dd1a4f73`) from a prior session that never completed. The cleanup path in `_dispatch_handoff_continuation` only runs if `handoff-latest.json` exists — if the model never wrote that file, `pending-handoff.json` persists indefinitely.

### F5: Milestone lifecycle is a parallel file-based system disconnected from ds_milestones
`milestone-active.txt` (written by `on-milestone-start`, deleted by `on-milestone-end`) is a completely separate milestone tracking mechanism from the `ds_milestones` SQLite table populated by the CLI. A session can have a "milestone" in the hook sense without a corresponding `ds_milestones` row, and vice versa.

### F6: Session token accounting has no SQLite pathway
`on-token-log` writes token counts to `token-log.md` only. `raw_sessions.input_tokens` / `raw_sessions.output_tokens` are NULL in recent rows. The `token_usage_records` table has 0 rows. The only token counts in SQLite are from `on-post-tool-use` (`token.consumed`, 7 rows) and `raw_token_usage` (3 rows from `on-skill-metrics` with all zeros).

### F7: on-security-scan writes no findings to any storage
Despite 5 firings, no security findings exist in `sec_hook_checks`, `hook_findings`, or `security_findings`. The SQLite schema for persisting hook security findings exists and is correctly structured, but the hook implementation does not use it. Intents #2 and #3 are structurally unmet.

### F8: on-skill-load and on-skill-complete are likely dormant in practice
Neither appears in `hook-timing.jsonl`. Both are non-dispatcher hooks that may require direct `settings.json` registration to fire. Their file-based outputs (`skill-usage.log`, calibration records) have no observed writes from the current period. `skill_invocations` has 1 row.

### F9: skill-usage.jsonl produces structurally empty data
All 3 records have `skill="unknown"` and `session=""`. The skill name extraction from Skill tool payload fails silently. The downstream `telemetry-buffer.jsonl` carries `skill_name="unknown"`. The `raw_skill_telemetry` table (0 rows) was presumably intended to replace this but is not wired.

### F10: hook.tool_activity canonical events use a non-standard event type
`hook.tool_activity` does not follow the `domain.entity.action` three-part pattern validated by the spool ingestor (`event.validation.failed` errors show this pattern check). However, `hook.tool_activity` itself was never rejected — it may predate the validator or be exempt. `execution.completed` was the rejected type (57 failures, all before 2026-05-19, now resolved).

---

## Intent Divergence

| Intent | Status | Evidence |
|--------|--------|----------|
| #1 SQLite-first | **WIDE GAP** | 11 of 22 active handlers write exclusively to files. `hook-timing.jsonl` (3,636 rows), `token-log.md`, `skill-usage.jsonl`, `telemetry-buffer.jsonl`, `milestone-active.txt`, `milestone-log.md`, `quality-score.json`, `quality-log.md`, `corrections.log`, `pending-handoff.json` are all file-only runtime state with SQLite equivalents available but unused. |
| #2 Security intake | **UNMET** | `on-security-scan` is not triggered during project intake. No intake-to-security-findings pipeline exists through hooks. |
| #3 Security gate | **UNMET** | `on-security-scan` is advisory-only. No findings accumulate in SQLite. No gate queries hook-generated security findings. |
| #4 Canonical events as spine | **PARTIAL** | 20 of 22 active handlers emit no canonical events. The handlers that do emit (`on-session-start`, `on-session-end`, `on-stop-handoff`) do so indirectly via SQLite library calls. Only `on-post-tool-use` emits via spool (the correct path). The highest-volume events are emitted by `run.py` outside the hook chain entirely. |
| #5 Marker file authority | **N/A** — hooks do not manage `.dream-studio-project` marker files | |

---

## Open Questions

1. **Is `on-skill-load` registered in `settings.json`?** It fires on PostToolUse Read events and is not in any dispatcher. If it's independently registered, it should appear in `hook-timing.jsonl`. If it's not registered, it is dead code.

2. **Why does `on-pulse` record to `hook_executions` but none of the other 21 handlers do?** Was `hook_executions` intended to eventually replace `hook-timing.jsonl`, with `on-pulse` as the prototype? Or is the distinction intentional?

3. **Is `pending-handoff.json` currently causing prompt injection?** The file exists with `status: in_progress` from a prior session. On the next UserPromptSubmit, `on-prompt-validate` will check it, find `age >= 60` (it's days old), and return `False` — so no injection will occur. But the file should be cleaned up.

4. **What is the intended relationship between `ds_milestones` (CLI) and `milestone-active.txt` (hook)?** They track different things under the same concept. Is the file-based milestone tracking intended to be deprecated in favor of the CLI milestone system?

5. **Was the `spool.emitter` module removed?** It is imported by `on-context-threshold` but does not exist. The emitter capability (writing envelopes to spool) exists in `emitters/shared/spool_writer.py`. Was `spool/emitter.py` renamed and the import never updated?

6. **The `token_usage_records` table has 0 rows.** The table schema is the most detailed token accounting schema in the system (with `billing_mode`, `accounting_confidence`, `cached_tokens`, `estimated_cost`). Nothing writes to it. Is this the intended destination for `token.consumed` events post-projection, or is it a schema placeholder?
