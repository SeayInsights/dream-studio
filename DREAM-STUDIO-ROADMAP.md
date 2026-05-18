# Dream Studio — Master Roadmap
**Last updated:** 2026-05-17
**Status:** Slices 1–9e CLOSED — all dependency chains proven operational — entering Slice 10
**Read this first in every new session before doing anything.**

---

## What Dream Studio Actually Is

Dream Studio is a **local AI development operating system**. Not a plugin. Not a workflow template library. An operating system that:

- Manages the relationship between developer intent and AI execution
- Provides persistent memory and state that AI tools lack between sessions
- Enforces quality standards AI tools don't enforce natively
- Routes work to the right capability at the right moment
- Accumulates intelligence across sessions and projects so the system improves over time
- Installs natively into any AI tool the developer uses — Claude Code today, Cursor/Codex/Copilot tomorrow

**The core differentiator:** Every other system (GSD, Superpowers, task-master) solves context rot within a session. Dream Studio is the first system designed to accumulate intelligence *across* sessions. Gotchas, lessons, approach history, event logs, design briefs — these persist and make every future session smarter than the last.

**The end goal:** Take any developer (technical or non-technical) through the full software development lifecycle — from idea to scoped PRD to verified, polished, traceable shipped software — with AI doing the execution and Dream Studio providing the structure, memory, quality gates, and intelligence that turns 90% completion into 100%.

---

## Why the Clean Rebuild Happened

Iteration one worked. Skills ran. Builds reached 90% completion on DreamySuite (86K LOC), Dream Studio, and others. What failed: no guiding principle connecting business intent to technical execution. No PRD defining done. No milestone tracking. No traceability showing which skill produced which output. No module boundary enforcement preventing god files. The codebase also accumulated overlapping adapter boundaries and competing sources of truth across 15 specific architectural flags identified in recon. Structural refactor before adding capabilities was the right call.

---

## What Has Been Proven From Real Usage

From the iteration one SQLite backup (not theory — operational evidence):

- `core:build` — 98 invocations, 98 succeeded
- `core:plan` — 60 invocations, 60 succeeded
- `core:think` — 32 invocations, 32 succeeded
- `quality:debug` — 25 invocations, 25 succeeded
- Wave-based parallel subagent dispatch — 33 tasks in 5 waves, zero conflicts
- DreamySuite architecture refactor — 12/12 domains complete

From Slice 9 live testing (dependency chain end-to-end proofs):

- `Skill("ds-core", "build")` — loads from `~/.claude/skills/ds-core/`, dispatches to `modes/build/SKILL.md` (168 lines), follows skill instructions not built-in behavior
- `Skill("ds-workflow")` — discovers all 22 workflows from `~/.claude/workflows/`
- UserPromptSubmit hook — fires before every response, surfaces enforcement + pulse check
- Docker clean install — all 9 skills, 9 agents, 22 workflows, complete hook tree on fresh Linux container, doctor returns pass

---

## Architecture: How the System Works

### Three Layers

**Layer 1 — Capability Layer** (skills, agents, workflows)
70+ SKILL.md files across 11 packs, 9 agents, 22 workflows. All in `canonical/`. Installed natively to `~/.claude/skills/`, `~/.claude/agents/`, `~/.claude/workflows/`. Complete.

**Layer 2 — Infrastructure Layer** (event pipeline, provisioner, spool, database)
Spool → ingestor → SQLite. Integration provisioner installs complete `~/.claude/` config. Project spine fully wired. Work order executor, gate system, design brief pipeline all operational.

**Layer 3 — Intelligence Layer** (scoping, SDLC pipeline, design gates, memory, learning loop)
Scoping skill proven. SDLC pipeline complete. Design gates wired. Memory harvest operational. Adaptive learning system (Slice 10) is the next layer.

### What a Correct Install Produces

`ds integrate install claude_code --execute` produces:

```
~/.claude/
  CLAUDE.md                     ← adapter projection + enforcement block
  settings.json                 ← 8 hooks (4 emitter + 4 dispatcher) with matchers
  skills/                       ← full directory tree per pack
    ds-core/                    ← SKILL.md + modes/ + gotchas.yml + config.yml + references/
    ds-quality/ ds-security/ ds-analyze/ ds-domains/
    ds-project/ ds-workflow/ ds-setup/ ds-bootstrap/
  agents/                       ← all 9 agent profiles
  workflows/                    ← all 22 workflow YAMLs
  hooks/
    run.py                      ← emitter (reads .plugin-root for repo path)
    dispatch/hooks.py           ← dispatcher
    runtime/hooks/meta/         ← 17 meta handlers
    .plugin-root                ← repo path sidecar (self-healing on reinstall)

~/.dream-studio/
  state/studio.db               ← SQLite (schema version 55)
  state/installed-version       ← build date for update detection
  state/installed-manifest.json ← hash manifest for incremental updates
  bin/ds.cmd (Windows) or ds    ← global launcher
  events/spool/                 ← incoming events
  events/processed/             ← ingested
  events/failed/                ← rejected events (not reason files)
  events/failed/reasons/        ← rejection reason files (separate subdirectory)
```

### Hook Architecture

Hooks use stable `~/.claude/hooks/` paths — no filesystem walking. The `.plugin-root` sidecar contains the repo path. Hook handlers read it to load Dream Studio imports via `sys.path`. Self-healing: repo move → reinstall → sidecar updated.

### Dual-Mode Skill Invocation

Every skill works in two modes with identical output:
- **Pipeline mode:** SDLC progression invokes automatically based on work order type
- **Direct mode:** `ds skill invoke <pack>:<mode>` — same skill, same standards

### Work Order Types — The Routing Key

| Type | Pre-Build Gate | Build Executor | Post-Build Gate |
|------|---------------|----------------|-----------------|
| `ui_component` | design brief locked | fullstack:frontend | design critique + anti-slop |
| `ui_page` | design brief locked | website:page | design critique + anti-slop |
| `api_endpoint` | API contract exists | fullstack:backend | security:scan |
| `authentication` | API contract + security review | fullstack:backend | security:scan |
| `data_pipeline` | — | fullstack:backend | security:scan |
| `saas_feature` | API contract exists | ds-domains:saas-build | security:scan |
| `game_mechanic` | spec approved | ds-domains:game-dev | game:validate |
| `deployment` | all tests pass | devops-engineer agent | security:scan |
| `documentation` | — | ds-core:build | — |
| `infrastructure` | — | ds-core:build | — |

---

## Completed Slices

| Slice | What It Did | Status |
|-------|------------|--------|
| 1 | Spool foundation — atomic event pipeline end-to-end | CLOSED |
| 2 | Integration provisioner — Claude Code compiler/installer/health | CLOSED |
| 3 | Emit migration — 39 call sites, hooks/run.py deleted, dispatcher created | CLOSED |
| 4 | Canonical migration + interfaces/adapters retired + project spine schema | CLOSED |
| 5a–5e | Project intelligence — dispatch chain, spine, scoping, memory ingest, WO types | CLOSED |
| Pre-6 | selector.py canonical path fix, 6 test debt items, 2059 pass baseline | COMPLETE |
| 6a–6d | SDLC pipeline — WO executor, gate system, dual-mode invocation, todo lists, quality:audit | CLOSED |
| 7 prereqs | Pack elevation, setup registration, quality:secure rename, fullstack:integrate deepened | CLOSED |
| 7a–7e | Design layer — brief persistence, design system lock, anti-slop, critique gate, milestone close | CLOSED |
| 8a | Hook enforcement — UserPromptSubmit blocking, CLAUDE.md enforcement, context.md enforcement | CLOSED |
| 8b | Active project from DB, ds project set-active/deactivate/delete, marker file removed | CLOSED |
| 8c | Global ds entry, compiler reads packs.yaml, stale refs fixed, docs overhaul, session harvest, CLI UX, resume skill | CLOSED |
| 8d pre-reqs | Installer hook gap, spool WO event failures, Dream Command stabilization | CLOSED |
| 9a | Spool envelope fix — schema_version defensive write, WO event types, backlog cleared, live harvest | CLOSED |
| 9b | Workflow execution loop — WorkflowRunner, ds workflow CLI, node skill mapping | CLOSED |
| 9c | Version tracking — VERSION file, update notification, ds update, expanded doctor | CLOSED |
| 9d | Complete hermetic install — full skill dirs, agents, workflows, hooks+sidecar, version marker | CLOSED |
| 9d extended | Full skill directory sync, workflow install, hook fixed-path install, legacy purge | CLOSED |
| 9e | Docker verification, cross-platform hardening, install scripts, reason.json fix, PATH auto-config | CLOSED |

**Authoritative baseline: 1 remaining failure.**

`test_game_validate.py::TestValidateGdscriptCoverage::test_skips_oversized_file` — ERROR at teardown only. Python 3.12 `follow_symlinks` incompatibility in `conftest.py`. Not fixable without touching conftest. Accepted permanently.

**All dependency chains proven operational:**

| Chain | Status | Evidence |
|-------|--------|----------|
| Chain 1 — Natural language → skill execution | ✅ PROVEN | Skill("ds-core", "build") loads modes/build/SKILL.md, follows instructions |
| Chain 2 — Work order lifecycle | ✅ PROVEN | WO events have schema_version, ingest cleanly, land in SQLite |
| Chain 3 — Hook dispatch | ✅ PROVEN | Dispatcher installed, matchers present, stable paths, legacy purged |
| Chain 4 — Workflow execution | ✅ PROVEN | 22 workflows discoverable, runner built and tested |
| Chain 5 — Agent execution | ✅ PROVEN | 9 agents in ~/.claude/agents/ |
| Chain 6 — Design system pipeline | ✅ PROVEN | Brief + 5 systems + critique gate all wired |
| Chain 7 — Memory loop | ⚠️ PARTIAL | Harvest runs, gotchas seeded; intelligence surfacing is Slice 10 |
| Chain 8 — Install chain | ✅ PROVEN | Docker clean install verified on fresh Linux container |

---

## Known Technical Debt (Carry Forward Every Slice)

**1. skills/career/ has external dependency**
Not migrated to canonical/. Depends on `career_studio_path`. Do not touch.

**2. Skill consolidation deferred**
Security split three ways, thin modes exist. Accepted — real usage will inform what to consolidate.

**3. Auto-advance after work-order close**
System stops after a WO closes. AI must manually call `project start` for the next WO. The autonomous loop is a Slice 10 concern.

**4. Chain 7 intelligence surfacing incomplete**
Gotchas in SQLite. Raw approaches recorded. Technology signals seeded. Nothing surfaces them to the AI before skill invocations yet. Slice 10 closes this.

**5. Binary distribution deferred**
Python 3.12+ required. Install scripts handle auto-install. Compiled binaries (`ds.exe`, `ds-mac`, `ds-linux`) would eliminate the Python requirement. Deferred post-launch. Revisit when real user feedback shows Python is a barrier.

---

## Current State: Dream Command

**Project ID:** `a4befdce-bfb6-40ed-9e83-ace93edac44b`
**Repo:** `C:\Users\Dannis Seay\builds\dream-cmd`
**Status:** Active — WO1 ✅ WO2 ✅ WO3 🔲 (next)

**Before WO3 starts:**
- Run `workflow: studio-onboard` — on-first-run handler flagged incomplete onboarding
- Design brief `525c53d6` is DRAFT — needs population and lock
- WO3 is `ui_component` — pre-build gate requires locked design brief

---

## Roadmap: Slice 10 — Adaptive Learning System

Full vision in `dream-studio-evolution-prompt.md`. Five workstreams:

**10a — Friction signal harvester** (migration 056, ds_friction_signals table)
Runs at session end. Detects moments where the system wasn't enough — gate skips, unrouted language, immediate redos, timing anomalies.

**10b — Gap classifier** (`ds learn review` command)
Classifies friction signals as capability gap / personalization gap / onboarding gap. Human confirms before action.

**10c — User extensions schema** (ds_user_skill_extensions table)
Canonical never modified. Extensions layer on top at skill invocation time. `ds skill extensions list/revert/export`.

**10d — Guided expansion conversation** (`learn:expand` skill mode)
One question at a time. Non-technical users supported. Generates extension, tests retroactively, asks approval.

**10e — Provisioner integration**
Compiler reads user extensions on install. New modes appear in CLAUDE.md routing and `~/.claude/skills/` automatically.

**Constraints:** Fully local. No cloud. Canonical never modified. Extensions portable. Dual-mode parity.

---

## After Slice 10

**Open source on GitHub:** MIT or Apache 2.0. Free. Fully local. Adaptive to each developer over time.

**Multi-tool expansion:** Same capability layer. Tool-specific compiler + installer + emitter. `integrations/targets/<tool>/capabilities.py` declares what each tool supports.

**DreamySuite revival:** Once Dream Command proves the full lifecycle, DreamySuite gets the same treatment.

**Dashboard analytics layer:** Distiller, skill effectiveness metrics, recommendation engine — post-Slice 10.

---

## Architectural Constraints — Never Violate These

1. **No live AI tool config writes in tests** — `~/.claude`, `~/.codex`, `~/.cursor` never touched. `guard_real_homedir` autouse fixture enforces this.
2. **No live SQLite writes in tests** — All test DB operations use `tmp_path`.
3. **Atomic spool writes** — Temp file + fsync + rename. Never write directly to final path.
4. **Normalized skill IDs** — `ds-<pack>` for skill IDs, `<pack>:<mode>` for specifiers.
5. **`canonical/` is the authority** — `skills/career/` is the only exception.
6. **Project spine is the anchor** — Every event/artifact/invocation carries project_id.
7. **1 pre-existing failure is baseline** — `test_game_validate.py::test_skips_oversized_file` teardown error only.
8. **`skills/career/` stays deferred** — External dependency. Do not migrate.
9. **Dual-mode output parity** — Pipeline and direct invocation produce identical output format.
10. **Work order types drive routing** — Skill selection is automatic based on work order type.
11. **Installer is the authority** — `ds integrate install claude_code --execute` is the single command that produces a fully functional system.
12. **Canonical never modified by user extensions** — Extensions layer on top via `ds_user_skill_extensions`.
13. **Tool-capability-aware install** — Each AI tool gets configured with exactly what it natively supports via `integrations/targets/<tool>/capabilities.py`.
14. **Fail-open on observability** — Hook failures, DB query failures, spool write failures never block execution. Always exit 0 from hooks.

---

## Quick Reference: Current State

| Component | Status |
|-----------|--------|
| Spool event pipeline | ✅ Proven |
| Integration provisioner (Claude Code) | ✅ Docker verified |
| All 9 skills installed natively (full dirs) | ✅ Proven |
| All 9 agents installed natively | ✅ Proven |
| All 22 workflows installed natively | ✅ Proven |
| Hooks with stable paths + sidecar | ✅ Proven |
| Work order executor + gate system | ✅ Complete |
| Design brief + design system lock | ✅ Complete |
| Anti-slop gate + critique gate | ✅ Complete |
| Milestone close workflow | ✅ Complete |
| Version check + update notification | ✅ Complete |
| Session intelligence harvest | ✅ Live run complete |
| Workflow execution loop (runner) | ✅ Complete |
| Cross-platform (Docker verified) | ✅ Proven |
| install.sh + install.ps1 | ✅ Complete |
| Chain 1 end-to-end proof | ✅ PROVEN |
| **Dream Command studio-onboard** | ❌ Required before WO3 |
| **Friction signal harvester** | ❌ Slice 10a |
| **Gap classifier** | ❌ Slice 10b |
| **User extensions schema** | ❌ Slice 10c |
| **Guided expansion conversation** | ❌ Slice 10d |
| **Provisioner reads user extensions** | ❌ Slice 10e |
| **Multi-tool expansion** | ❌ Post-launch |
| **Binary distribution** | ❌ Future milestone |

---

## Key Planning Files

| File | Purpose |
|------|---------|
| `DREAM-STUDIO-ROADMAP.md` (this file) | Session anchor — intent, direction, constraints |
| `slice-9e-writeup.md` | Most recent completed slice |
| `system-audit-2026-05-17.md` | Full dependency chain audit findings |
| `dependency-chain-map-2026-05-17.md` | Chain-by-chain status with evidence |
| `dream-studio-evolution-prompt.md` | Slice 10 vision — adaptive learning system |
| `integration-pack-plan.md` | Original architectural plan |
| `recon-2026-05-15.md` | Repository reconnaissance — 15 architectural flags |

---

## How to Start a New Session Correctly

1. Read this file completely.
2. Read `slice-9e-writeup.md` to understand the most recent completed work.
3. Run `ds doctor` — must return `status: pass` before doing anything.
4. If doctor fails any check: `ds doctor --fix` then verify.
5. Check Dream Command: `ds project status a4befdce-bfb6-40ed-9e83-ace93edac44b`
6. Do not start Slice 10 before `workflow: studio-onboard` has run on Dream Command.
7. Do not propose work outside the current slice scope.
8. Every implementation decision must be traceable to a goal in this document.
9. The 1 accepted baseline failure is `test_game_validate.py::test_skips_oversized_file`. Any other failure is real.
10. The installer is the single source of truth. When in doubt: `ds integrate install claude_code --execute` then `ds doctor`.

---

*This document is the session anchor. When Claude Code returns unexpected results, this document defines what to adapt toward, not what to abandon. The intent is fixed. The path is flexible.*
