# Pass 1e — Adapters Audit
*Phase 1 analysis | 2026-05-22*

---

## Stated Architectural Intents

1. **SQLite-first authority** — all runtime STATE must be SQLite-backed. File-based state is v1 rot.
2. **Security audit during brownfield onboarding** — security skills run during project intake, findings stored in SQLite.
3. **Security audit as SDLC lifecycle gate** — greenfield projects must pass security audit before going live.
4. **Canonical events as the spine** — all state changes flow through canonical_events. Direct table writes without event emission are anomalies.
5. **Marker file authority for attribution** — `.dream-studio-project` markers are identity source; `ds_projects` is metadata storage.

---

## Adapter Targets

### adapter-projections/ — Snapshot Archive

**Status:** SUPERSEDED (self-declared in `_SUPERSEDED.md`)

**What it is:** Eight frozen stub files — one per AI tool surface — at `adapter-projections/{chatgpt,claude,codex,copilot,cursor,local-model,mcp,shell}/`. Each file contains only: adapter metadata (id, type, project_id), an authority-role declaration (`This adapter config is a generated projection`), and a supported context packets / result types list. Total content per file: ~600–700 bytes.

**Superseded by:** `integrations/` (compiler + installer) + `emitters/` (event pipeline). The `_SUPERSEDED.md` note reads: "scheduled for deletion in Slice 3." Slice 3 has passed; these files remain.

**Whether anything still reads them:** Yes. Two live code paths reference `adapter-projections/` content:

1. `integrations/compiler/claude_code.py` (line 18) reads `adapter-projections/claude/CLAUDE.md` as the base template when compiling the CLAUDE.md output for install. The file contains routing-table marker comments (`<!-- BEGIN AUTO-ROUTING -->` / `<!-- END AUTO-ROUTING -->`) that the compiler populates dynamically from `packs.yaml`. This is an active, non-dead read.

2. `core/shared_intelligence/adapter_alignment.py` (DEPRECATED header) and `core/shared_intelligence/adapter_staleness.py` (DEPRECATED header) store adapter config projection paths as `adapter-projections/claude/CLAUDE.md`, `adapter-projections/codex/AGENTS.md`, etc. in `adapter_authority_profiles` SQLite rows. The staleness checker uses these paths to compute hash drift. Both files carry `# DEPRECATED: Superseded by integrations/...` headers but are not deleted.

**Net:** The `adapter-projections/claude/CLAUDE.md` file is not dead code — it is the compiler's template source. The other seven files (`chatgpt`, `codex`, `copilot`, `cursor`, `local-model`, `mcp`, `shell`) have no live code path that reads or installs them.

---

### integrations/ — Live Integration Module

**What it is:** The sole live adapter management layer. Three sub-packages plus top-level modules.

**Sub-packages:**
- `compiler/claude_code.py` — reads `canonical/skills/*/SKILL.md`, `canonical/agents/`, `canonical/workflows/`, `adapter-projections/claude/CLAUDE.md`, and `packs.yaml` to produce a deterministic install plan dict (`compile_pack()`). Does not write to disk.
- `installer/claude_code.py` (`ClaudeCodeInstaller`) — applies the plan to the filesystem via `FileOp` operations. Writes to `~/.claude/` (user scope) or `./.claude/` (project scope). Writes the manifest to `~/.dream-studio/integrations/claude_code/manifest.json`.
- `installer/base.py` — abstract `InstallerBase` class, `FileOp` dataclass, `FileOpPlan`.
- `installer/file_ops.py` — `atomic_write`, `atomic_copy`, `backup_before_write`.
- `targets/claude_code/settings_merge.py` — additive JSON merge logic for `settings.json`. Purges legacy hook commands; deduplicates by normalized command path.
- `targets/claude_code/hooks_template.json` — defines 9 hook entries: UserPromptSubmit (×3), Stop (×2), PostCompact (×2), PostToolUse/Skill (×2), PostToolUse/Edit|Write (×1).

**Top-level modules:**
- `detector.py` — detects Claude Code presence by checking for `.claude/` in working directory (project scope) or `~/.claude/` (user scope). Only `claude_code` is in `SUPPORTED_TOOLS`. No other tool detection exists.
- `health.py` — nine-state machine: `NOT_DETECTED → DETECTED_NOT_INTEGRATED → PLAN_AVAILABLE → INSTALLED_UNVERIFIED → INSTALLED_VERIFIED → INSTALLED_DRIFTED → EVENTS_EMITTING → INGEST_VERIFIED → BROKEN`. State is computed fresh by `doctor()` on each call by comparing manifest hashes to disk. Emits `integration.health.changed` event to spool when state transitions (conditional on `last_health_state` field in manifest). `last_health_state` is never written back to the manifest after a transition — the field is always `null` in the live manifest (confirmed in runtime data below).
- `manifest.py` — read/write of `~/.dream-studio/integrations/{tool_id}/manifest.json`. Schema version: `ds.integration.manifest.v1`. Tracks SHA-256 hashes of all installed files for drift detection.

**CLI surface:** `ds integrate {detect, status, doctor, plan, install}` via `interfaces/cli/ds.py`.

---

### Per-Adapter Assessment

#### chatgpt

- **What it is:** `adapter-projections/chatgpt/context_packet.md` — 643-byte stub.
- **What it does:** Declares ChatGPT as a projection consumer. Supported packets: `resume`, `research`, `review`. Result types: `decision`, `research`, `review`, `risk`.
- **Current state:** STUB. No compiler, no installer, no targets/ subdirectory.
- **Evidence of recent use:** Zero `adapter_executions` rows. No detection mechanism. Not referenced by any live install path.
- **Intent 1 (SQLite):** NO — file-based only.
- **Intent 2 (Security intake):** NO.
- **Intent 3 (Security gate):** NO.
- **Intent 4 (Events):** NO.
- **Intent 5 (Marker):** NO.
- **Files installed:** None.
- **Notes:** `adapter_alignment.py` (DEPRECATED) registers chatgpt in `adapter_authority_profiles` with `config_projection_path = adapter-projections/chatgpt/context_packet.md`. That table has 0 rows at runtime — registration has never been executed.

---

#### claude (claude_code)

- **What it is:** The sole fully-implemented adapter target. Covers Claude Code (the CLI environment this system runs in).
- **What it does:** Installs Dream Studio operational constraints, skill routing, hook scripts, agent profiles, workflow YAMLs, and settings.json hooks into `~/.claude/` (user) or `./.claude/` (project). Makes Claude Code a Dream Studio execution surface.
- **Current state:** IMPLEMENTED. Installed, with drift (see below).
- **Evidence of recent use:** Manifest at `~/.dream-studio/integrations/claude_code/manifest.json` — installed 2026-05-19T23:09:42Z. `ds_version: migration-57`. 515 files tracked (513 create, 1 merge_json, 1 unchanged). Active session is running through this installed surface now.

**Full install chain (what gets written, in plan order):**

1. **Skill directories** (`~/.claude/skills/ds-{analyze,bootstrap,career,core,domains,fullstack,project,quality,security,setup,website,workflow}/`) — all files under `canonical/skills/*/` synced recursively. Every `SKILL.md`, mode file, metadata YAML, asset file.
2. **`~/.claude/CLAUDE.md`** — enforcement block (hardcoded in `_ENFORCEMENT_BLOCK` constant) prepended to the content of `adapter-projections/claude/CLAUDE.md`, with the routing table (`<!-- BEGIN AUTO-ROUTING -->` block) populated by reading `packs.yaml` and `canonical/skills/*/modes/*/metadata.yml`.
3. **`~/.claude/settings.json`** — additive JSON merge adding DS hook entries (UserPromptSubmit, Stop, PostCompact, PostToolUse). Legacy hooks purged. Deduplication applied.
4. **`~/.claude/settings.local.json`** — always SKIP.
5. **Agent profiles** (`~/.claude/agents/*.md`) — all `canonical/agents/**/*.md` (excluding README).
6. **Workflow YAMLs** (`~/.claude/workflows/*.yaml`) — all `canonical/workflows/*.yaml`. Plus `docs/contracts/workflow-contract.md` copied into `~/.claude/skills/ds-workflow/docs/contracts/`.
7. **Hook scripts** (to `~/.claude/hooks/`):
   - `emitters/claude_code/run.py` → `hooks/run.py`
   - `runtime/dispatch/hooks.py` → `hooks/dispatch/hooks.py`
   - `control/execution/dispatch_tracking.py` → `hooks/control/execution/dispatch_tracking.py`
   - `runtime/session_config.py` → `hooks/runtime/session_config.py`
   - `runtime/hooks/meta/*.py` (all handlers) → `hooks/runtime/hooks/meta/`
   - `.plugin-root` sidecar → `hooks/.plugin-root` (repo path, overwritten every install)
   - `canonical/adapters/claude/statusline.py` → `hooks/statusline.py`
8. **Git pre-push hook** (`{git_repo_root}/.git/hooks/pre-push`) — opt-in only; set when `git_repo_root` is provided to installer.
9. **`~/.dream-studio/state/installed-version`** — VERSION file content.
10. **`~/.dream-studio/bin/ds.cmd`** (Windows) — global launcher script. PATH appended to PowerShell profile.
11. **Manifest** → `~/.dream-studio/integrations/claude_code/manifest.json`.

**Health check state (from `ds integrate doctor` run 2026-05-22):**
- State: `installed_drifted`
- 10 drift items: 8 hash mismatches in `~/.claude/skills/ds-domains/modes/website/{assets,data}/` plus `~/.claude/skills/ds-setup/skill.ts` and `~/.claude/settings.json`.
- The `.claude/` target is project-scope (cwd at time of install had `.claude/` present).

**Intent 1 (SQLite):** PARTIAL — install state is tracked in `~/.dream-studio/integrations/claude_code/manifest.json` (file-based JSON). There is no corresponding row in SQLite. The `adapter_authority_profiles`, `adapter_executions`, and `adapter_result_records` tables all have 0 rows.
**Intent 2 (Security intake):** NO — the installer does not invoke any security skill or store security findings in SQLite during installation.
**Intent 3 (Security gate):** NO — no security gate check in the install or plan path.
**Intent 4 (Events):** PARTIAL — `health.py` emits `integration.health.changed` to spool when state transitions, conditional on `last_health_state` in manifest differing from new state. However, `last_health_state` is always `null` in the live manifest (never written back after a transition), so the condition `last_state is not None` is never satisfied. **No `integration.health.changed` events have been emitted to canonical_events** (confirmed: 0 matching rows). The install path itself emits no events.
**Intent 5 (Marker):** NO — the installer does not consult `.dream-studio-project` marker files. Scope (user vs project) is inferred solely from whether a `.claude/` directory exists in the working directory.

---

#### codex

- **What it is:** `adapter-projections/codex/AGENTS.md` — 682-byte stub.
- **What it does:** Declares Codex as a projection consumer. Supported packets: `resume`, `work_order_execution`, `review`, `release_gate`. Result types: `decision`, `code_change`, `validation`, `evidence`, `risk`.
- **Current state:** STUB. No compiler, no installer, no targets/ subdirectory.
- **Evidence of recent use:** None.
- **Intent 1-5:** All NO.
- **Files installed:** None.
- **Notes:** `adapter_staleness.py` maps codex to `ACTIVE_REPO_SURFACES["codex"] = "AGENTS.md"` and `LOCAL_USER_SURFACES["codex"] = "~/.codex/AGENTS.md"`. These checks run against a provided config root, not installed surfaces. Both deprecated files.

---

#### copilot

- **What it is:** `adapter-projections/copilot/instructions.md` — 650-byte stub.
- **What it does:** Declares GitHub Copilot as a projection consumer. Supported packets: `repo_instructions`, `review`. Result types: `code_suggestion`, `review`, `evidence`.
- **Current state:** STUB.
- **Evidence of recent use:** None.
- **Intent 1-5:** All NO.
- **Files installed:** None.

---

#### cursor

- **What it is:** `adapter-projections/cursor/rules` — 658-byte stub.
- **What it does:** Declares Cursor as a projection consumer. Supported packets: `editor_context`, `resume`. Result types: `code_change`, `review`, `evidence`.
- **Current state:** STUB.
- **Evidence of recent use:** None.
- **Intent 1-5:** All NO.
- **Files installed:** None.

---

#### local-model

- **What it is:** `adapter-projections/local-model/context_packet.md` — 647-byte stub.
- **What it does:** Declares a local (offline) model as a projection consumer. Supported packets: `resume`, `offline_analysis`. Result types: `analysis`, `validation`, `risk`.
- **Current state:** STUB.
- **Evidence of recent use:** None.
- **Intent 1-5:** All NO.
- **Files installed:** None.

---

#### mcp (MCP Tools)

- **What it is:** `adapter-projections/mcp/server-policy.json` — 447-byte stub.
- **What it does:** Declares MCP tool surface as a projection consumer. Supported packets: `tool_context`, `authority_query`. Result types: `tool_result`, `evidence`, `artifact`.
- **Current state:** STUB.
- **Evidence of recent use:** None.
- **Intent 1-5:** All NO.
- **Files installed:** None.
- **Notes:** Notably, `adapter-projections/mcp/` uses a different format (JSON policy) vs the markdown stubs for other adapters. This divergence is unexplained.

---

#### shell (Local Shell)

- **What it is:** `adapter-projections/shell/command-policy.json` — 452-byte stub.
- **What it does:** Declares local shell as a projection consumer. Supported packets: `command_context`, `validation`. Result types: `command_result`, `validation`, `evidence`.
- **Current state:** STUB.
- **Evidence of recent use:** None.
- **Intent 1-5:** All NO.
- **Files installed:** None.
- **Notes:** Like `mcp/`, uses JSON format rather than markdown.

---

## Special Focus: Installation State Storage

**Where install state lives:** File-based only. The manifest (`~/.dream-studio/integrations/claude_code/manifest.json`) is the sole record of installation state. It tracks: `schema_version`, `tool`, `scope`, `ds_version`, `installed_at`, and a per-file list with `path`, `operation`, and `content_hash`.

**What is NOT in SQLite:**
- No row in `adapter_executions` records when `ds integrate install` was run.
- No row in `adapter_authority_profiles` records the claude_code adapter as registered (0 rows).
- No row in `adapter_result_records` records install results.
- The `last_health_state` field in the manifest is always `null` — it is read by `_maybe_emit_transition()` to decide whether to emit a health event, but nothing in the install path ever writes it back.

**Intent 1 alignment:** The stated intent is "SQLite-first authority — file-based state is v1 rot." The integration install record, health state, and adapter execution history are entirely file-based. The SQLite tables intended to track this (`adapter_executions`, `adapter_result_records`, `adapter_authority_profiles`) exist at schema level but contain 0 rows. This is a clear divergence.

**Platform detection:** `~/.dream-studio/state/platform.json` stores OS/shell detection results (`os_name: Windows`, `python_version: 3.12.8`, etc.). This is also file-based, not SQLite.

---

## Special Focus: Event Emission from Adapters

**Canonical events emitted by any adapter path:** Zero. The `canonical_events` table has no rows matching `event_type LIKE '%integration%'` or `event_type LIKE '%adapter%'`.

**What the code intends:**
- `health.py::_maybe_emit_transition()` conditionally emits `integration.health.changed` via `CanonicalEventEnvelope` + `write_envelopes`. The condition is `last_health_state is not None AND last_health_state != new_state`.
- `last_health_state` is never written to the manifest by any code path in `integrations/`. The `build_manifest()` function in `manifest.py` does not include a `last_health_state` field. The manifest read by `_maybe_emit_transition()` therefore always returns `None` for this field.
- Result: the event emission guard never fires. Even if the state has changed, no event is emitted.

**Implication for Intent 4:** The canonical event spine is not receiving any integration lifecycle signals. Health transitions (e.g., `installed_verified → installed_drifted`) are invisible to the event store.

---

## Findings

**F1 — Deletion debt outstanding.** `_SUPERSEDED.md` states adapter-projections/ was scheduled for deletion in Slice 3. Six of eight files (`chatgpt`, `codex`, `copilot`, `cursor`, `local-model`, `mcp`, `shell`) have no live readers. The `claude/CLAUDE.md` stub is still read by the compiler. The other six are dead weight with no removal execution.

**F2 — `adapter-projections/` has a dual identity.** The directory is declared SUPERSEDED, yet `core/shared_intelligence/adapter_alignment.py` and `adapter_staleness.py` (both also marked DEPRECATED) store these paths as the canonical projection path references in SQLite authority profile definitions. These two deprecated modules reference `adapter-projections/` path strings in code that was also meant for deletion. Neither the directory nor the code referencing it has been cleaned up.

**F3 — Install state is entirely file-based.** The manifest lives at `~/.dream-studio/integrations/claude_code/manifest.json`. No row in `adapter_executions`, `adapter_result_records`, or `adapter_authority_profiles` records anything about the current installation. The SQLite tables for tracking adapter state are empty.

**F4 — `last_health_state` is a broken circuit.** The manifest format does not include `last_health_state`. The `_maybe_emit_transition()` function reads this field to decide whether to emit a health event. Since the field is never written, it is always `null`, and the guard `if last_state is not None` never fires. Health transitions emit no canonical events.

**F5 — Seven of eight adapter targets are unimplemented.** The `integrations/` module was architected for multi-adapter support (generic `InstallerBase`, `detector.py` with `SUPPORTED_TOOLS` tuple, `targets/` directory structure) but only `claude_code` was built. No installer exists for chatgpt, codex, copilot, cursor, local-model, mcp, or shell. The SUPPORTED_TOOLS tuple contains only `"claude_code"`.

**F6 — Scope detection ignores `.dream-studio-project` markers.** The installer determines scope (user vs project) by checking whether `.claude/` exists in the working directory. Intent 5 specifies `.dream-studio-project` marker files as identity source. The integration install path does not consult these markers at all.

**F7 — No security participation.** Neither the install path nor the health path invokes any security skill, calls any security gate, or stores security findings in SQLite. Intents 2 and 3 are not touched by any code in `integrations/`.

**F8 — `installed_drifted` state with `last_health_state = null` means the transition has never been recorded.** The live install is in `installed_drifted` state (10 drift items, detected 2026-05-22). Because `last_health_state` is never written, no `integration.health.changed` event was emitted when this drift occurred.

**F9 — The compiler reads `adapter-projections/claude/CLAUDE.md` but the file's routing table block is a placeholder.** The compiler *injects* the routing table into the `<!-- BEGIN AUTO-ROUTING -->` block at compile time. The placeholder in the source file is correct behavior. But this means the source `adapter-projections/claude/CLAUDE.md` is not itself valid — it is only valid after compiler injection. This creates a latent trap: reading the file directly without compiling it produces an empty routing table.

---

## Intent Divergence

| Intent | Status | Evidence |
|--------|--------|----------|
| 1 — SQLite-first authority | DIVERGED | Install state is in `~/.dream-studio/integrations/claude_code/manifest.json` (JSON file). All adapter SQLite tables (adapter_executions, adapter_result_records, adapter_authority_profiles) have 0 rows at runtime. |
| 2 — Security audit on brownfield intake | NOT PRESENT | No code in integrations/ invokes security skills or writes security findings during install. |
| 3 — Security gate for greenfield | NOT PRESENT | No security gate check in installer plan() or install() paths. |
| 4 — Canonical events as spine | BROKEN | Event emission guard depends on `last_health_state` field that is never written to the manifest. Zero integration events in canonical_events. |
| 5 — Marker file authority | NOT PRESENT | Scope detection uses `.claude/` directory presence, not `.dream-studio-project` marker files. |

---

## Open Questions

**OQ1 — Were the adapter-projections/ deletion and the deprecated adapter_alignment/staleness module deletions explicitly deferred, or did they slip?** The `_SUPERSEDED.md` says Slice 3. Slice 8c is current. No evidence of a deliberate deferral decision.

**OQ2 — Is `last_health_state` supposed to be written by the installer after a successful install, or by a separate health-update step?** The `build_manifest()` function signature does not include a `last_health_state` parameter. If it is supposed to be written post-install, the code to do so does not exist.

**OQ3 — Are the seven non-claude adapter stubs aspirational (future targets) or obsolete (replaced by the single claude_code implementation)?** The `adapter_alignment.py` deprecated file registers all eight adapters in SQLite, suggesting they were planned as real targets. But SUPPORTED_TOOLS contains only `claude_code`.

**OQ4 — Why does `adapter_authority_profiles` table exist in SQLite schema but have 0 rows?** Registration code exists in `adapter_alignment.py` (DEPRECATED) but was apparently never executed. Was the migration that created the table followed by a registration step that was skipped?

**OQ5 — What is the intended flow for `adapter_executions` and `adapter_result_records`?** These tables are schema-present but empty. No code in `integrations/` writes to them. Are they intended for future adapter execution tracking, or were they part of an earlier design that was superseded?
