# Dream Studio Hooks Reference

Complete catalog of all 31+ hook handlers across 4 packs.

**Canonical source:** `runtime/hooks/{pack}/`  
**Registration:** `hooks/hooks.json` + `~/.claude/settings.json`  
**Launcher:** `hooks/run.sh` (macOS/Linux), `hooks/run.cmd` (Windows)  
**Runtime doc:** `docs/HOOK_RUNTIME.md`

---

## Runtime Guarantees

**Fail-open (Phase 18.1.12):** All dispatchers catch `BaseException`. No hook failure can block a user session or prompt.

**Local-first:** No hook makes external network calls.

**Launcher resolution order:**
1. `runtime/hooks/core/{handler}.py`
2. `runtime/hooks/quality/{handler}.py`
3. `runtime/hooks/analyze/{handler}.py`
4. `runtime/hooks/domains/{handler}.py`
5. `runtime/hooks/meta/{handler}.py`
6. `hooks/handlers/{handler}.py` _(legacy fallback, deprecated)_

---

## UserPromptSubmit Hooks

**Trigger:** User submits a prompt  
**Dispatcher:** `on-prompt-dispatch`  
**Execution:** Sequential, fail-open per handler

| Slug | Pack | Purpose |
|------|------|---------|
| `on-prompt-validate` | meta | Validates input for security risks. Manages stale handoff files (300s TTL). Validates pending-handoff injection window (60s). Logs stale discards to diagnostics. |
| `on-session-start` | meta | Records new session on first user prompt. Inserts session row into `studio_db`. Uses marker-based UUID resolution for project tracking. |
| `on-first-run` | meta | Welcomes new users and prompts Director profile setup. Advisory; runs once per new installation. |
| `on-memory-retrieve` | meta | Injects relevant memories from `~/.dream-studio/memory/` into context. Outputs XML block to stdout. |
| `on-context-inject` | meta | Injects relevant `memory_entries` from SQLite before prompt processing (Chain 7 — Memory Loop, 18.4.4). Queries `reg_gotchas`, `raw_lessons`, `raw_approaches`. 24h dedup via `intelligence_surfaced_at`. |
| `on-milestone-start` | core | Writes marker when a milestone opens. Persists `milestone-active.txt` to `~/.dream-studio/state/`. |
| `on-context-threshold` | meta | Monitors session JSONL size and `context_window.used_percentage`. Prints compact reminder at urgent threshold. Emits `session.harvested` spool event. Never blocks. |
| `on-pulse` | meta | Proactive cross-project health check. Runs once per 15+ min per project idle. Advisory. |

---

## Stop Hooks

**Trigger:** Session ends (Stop button or Ctrl+C)  
**Dispatcher:** `on-stop-dispatch`  
**Execution:** Sequential, fail-open per handler

| Slug | Pack | Purpose |
|------|------|---------|
| `on-session-end` | meta | Closes session row on Stop event. Passes `outcome = payload.get("stop_reason") or "end_turn"` to `end_session()`. |
| `on-stop-handoff` | core | Writes handoff + recap on natural session Stop. Only writes if git activity exists (working tree changes OR commit in last 24h). Must complete in <2s. |
| `on-quality-score` | quality | Advisory quality scoring after milestone. Scans git diff for test coverage proxy, debug leftovers, potential secrets, large files. Appends to `~/.dream-studio/meta/quality-log.md`. Never blocks. |
| `on-skill-telemetry` | meta | Captures skill usage statistics at session end. Aggregates to telemetry store. |
| `on-milestone-end` | core | Emits checkpoint and clears marker at turn end. If milestone marker exists: records completion, prints checkpoint reminder, clears marker. Drafts retrospective lesson when session time exceeds difficulty threshold. |
| `on-token-log` | meta | Appends session token usage to `~/.dream-studio/meta/token-log.jsonl`. Records `prompt_tokens + completion_tokens`. |
| `on-meta-review` | meta | Weekly retrospective across recent sessions. Runs once per week. Wrapped in defensive try/except (fail-open). |
| `on-workflow-progress` | core | Read-only workflow status reporter. Reads `~/.dream-studio/state/workflows.json`, prints summary if any workflow active. **Never writes state.** |
| `on-changelog-nudge` | core | Reminds to update `CHANGELOG.md` when source files changed. Checks git status — advisory only, never blocks. |
| `on-memory-ingest` | meta | Batch-syncs `reg_gotchas`, `raw_lessons`, etc. into `memory_entries`. Default 300s cooldown (override: `DREAM_STUDIO_MEMORY_INGEST_INTERVAL`). Emits `memory.ingested` canonical event. Non-blocking. |

---

## PostToolUse Hooks — Skill Matcher

**Trigger:** `Skill` tool invocation completes  
**Execution:** Sequential, fail-open

| Slug | Pack | Purpose |
|------|------|---------|
| `on-skill-metrics` | meta | Appends skill usage record to `skill_usage.jsonl`. |
| `on-skill-complete` | meta | Advisory chain-suggest after skill invocation. Suggests next steps based on skill outcome. |

---

## PostToolUse Hooks — Edit/Write Matcher

**Trigger:** `Edit` or `Write` tool invocation completes  
**Dispatcher:** `on-edit-dispatch`  
**Protected paths (auto-skipped):** `settings.json`, `settings.local.json`, `CLAUDE.md`

| Slug | Pack | Purpose |
|------|------|---------|
| `on-agent-correction` | quality | Logs director corrections. Parses newest correction from `director-corrections.md`, appends to `corrections.log`. Drafts lessons when patterns repeat 3+ times. |
| `on-game-validate` | domains | Validates game project files (Godot/Blender constraints). Advisory only — emits stderr warning, never blocks. |
| `on-security-scan` | quality | Lightweight security pattern check on new file content. Scans for high-signal anti-patterns. Advisory only — never blocks. |
| `on-structure-check` | quality | Nudges when source files placed outside standard dirs (`.py`/`.ts`/`.js` should live in `src/`, `lib/`, `hooks/`, `app/`, or `tests/`). Advisory only. |

---

## PostToolUse Hooks — Read Matcher

**Trigger:** `Read` tool invocation completes

| Slug | Pack | Purpose |
|------|------|---------|
| `on-skill-load` | meta | Logs skill file reads and resolves `director_name`. Records access timestamps and extracts director metadata. |

---

## PostToolUse Hooks — All-Tools Matcher

**Trigger:** Any tool invocation completes  
**Registration:** `~/.claude/settings.json` (not `hooks.json`)

| Slug | Pack | Purpose |
|------|------|---------|
| `on-tool-activity` | meta | Rolling snapshot of recent tool usage. Maintains `~/.dream-studio/state/activity.json` with recent tool calls. |
| `on-post-tool-use` | core | Token attribution capture per tool invocation. Thin shim → delegates to `core.telemetry.token_capture`. Emits `token.consumed` canonical event. Always exits 0. |

---

## PostCompact Hooks

**Trigger:** `/compact` command completes

| Slug | Pack | Purpose |
|------|------|---------|
| `on-post-compact` | meta | Resets context tracking after `/compact`. Calls `record_kb_baseline()` to record JSONL size at compact time. Clears stale context markers. |

---

## Git Hooks

| File | Trigger | Purpose |
|------|---------|---------|
| `hooks/git/pre-push` | `git push` | Dream Studio pre-push gate. Runs `ds workflow run pre-push --non-interactive`. Blocks on gate failures. Bypass: `git push --no-verify` (not recommended). |
| `hooks/on-commit.py` | Git pre-commit (optional) | Guardrail enforcement at commit time. Modes: `advisory` (warn, allow) or `enforce` (block/require approval). Exit codes: `0`=allow, `1`=block, `2`=require_approval. |

---

## State Files

All hooks persist state to `~/.dream-studio/state/`:

| File | Writer | Purpose |
|------|--------|---------|
| `milestone-active.txt` | on-milestone-start | Marker for active milestone |
| `activity.json` | on-tool-activity | Rolling tool activity feed |
| `memory-ingest-last-run.json` | on-memory-ingest | Cooldown tracking (300s default) |
| `workflows.json` | Chief-of-Staff _(read-only to hooks)_ | Workflow progress |
| `handoff-latest.json` | on-stop-handoff | Handoff document for next session |
| `pending-handoff.json` | external writer | Pending handoff state |
| `stale-handoff.jsonl` | on-prompt-validate | Diagnostics: stale handoff discards |

---

## Orphaned Handlers (Not Invoked)

| Handler | Status | Note |
|---------|--------|------|
| `on-skill-gate` | Defined, not wired | HK-6 — not in hooks.json |
| `on-startup-health` | Root-level file, not in pack search path | Not reachable |
| `on-periodic-health` | Root-level file, not in pack search path | Not reachable |

---

## Hook Count by Pack

| Pack | Active handlers |
|------|----------------|
| meta | 14 |
| core | 6 |
| quality | 4 |
| domains | 1 |
| git | 2 |
| **Total** | **27 active** |

---

## Cross-references

- Events emitted by hooks: [`docs/reference/events.md`](events.md) — `system.*`, `session.*`, `token.*`, `memory.*`
- Hook runtime doc: `docs/HOOK_RUNTIME.md`
- Workflow monitoring: [`docs/reference/workflows.md`](workflows.md) — `on-workflow-progress`
