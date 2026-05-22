# Dream Studio — What Exists
*Phase 3 Synthesis | 2026-05-22*

> **Note on architecture references:** No `docs/architecture/data-model-v2.md` or `docs/architecture/SYSTEM.md` exists. The v2 target architecture is documented in the Phase 2 connection analysis (`02-connection-analysis.md`). Architecture docs live flat in `docs/` — the closest reference is `docs/ARCHITECTURE.md`. All v2 target statements in this document are sourced from Phase 2.

---

## Summary Table

| Category | Count | Installed / Active | State |
|----------|-------|--------------------|-------|
| Canonical skills | 11 | 11 (all installed) | 3 confirmed invocations; 8 zero-invocation |
| Skill modes | 47 | 47 | Most never invoked |
| CLI command groups | 13 | 13 | Active; 6 groups have file-backed or no-event operations |
| Hook handlers | 22 | 22 (dispatched) | 2 emit canonical events; 20 do not |
| Hook orphans | 3 | 0 (unreachable via dispatch) | on-startup-health, on-periodic-health, on-skill-gate |
| SQLite tables (total) | 182 | 182 (schema present) | 41 with data; 141 empty |
| Migrations applied | 61 | — | 4 eras: foundation, expansion, telemetry, TA-series |
| Workflows | 23 | 23 | 1 ran (studio-onboard, 2 runs); 22 dormant |
| Adapters | 8 | 1 (claude_code) | 7 stubs; claude_code file-only install state |
| API routes | 141 | 141 | Active FastAPI; security/PRD routes return empty |
| Canonical event rows | 1,853 | — | Significant backfill fraction |
| Security DB tables | 12 | 12 (schema) | All 0 rows |
| File-backed runtime stores | 24+ | Active | Intent #1 violations |
| Test functions | 3,498 | — | 338 test files; 26 xfail in dependency chain |
| Documentation files | 30+ in docs/ | — | No docs/architecture/ directory |
| Coverage omissions (hooks/lib) | 17 | — | "Temporary" labels, no work order refs |

---

## Skills

### Canonical Skill Pack Inventory

11 skill packs live at `canonical/skills/<pack>/SKILL.md` and installed equivalents at `~/.claude/skills/ds-<pack>/SKILL.md`. Every installed file is 22–224 bytes larger than canonical — the difference comes from installer prefix injection. Pack registry is `canonical/packs.yaml`.

| Pack | Canonical path | Mode count | Confirmed invocations | Notes |
|------|---------------|------------|----------------------|-------|
| ds-core | `canonical/skills/core/` | 8 modes | 19 (plan mode) | Work order linkage null on all 19; burst pattern suggests workflow runner over-emission |
| ds-quality | `canonical/skills/quality/` | 8 modes | 0 | Mode name mismatch: canonical says `secure`, installed routing says `pr-security-scan` |
| ds-security | `canonical/skills/security/` | 8 modes | 0 | All modes client-pipeline tools (PLMarketing/Kroger), not project-level SDLC gates |
| ds-analyze | `canonical/skills/analyze/` | 4 modes | 0 | — |
| ds-domains | `canonical/skills/domains/` | 7 modes | 0 | — |
| ds-website | `canonical/skills/website/` | 9 modes | 0 | — |
| ds-fullstack | `canonical/skills/fullstack/` | 4 modes | 0 | — |
| ds-setup | `canonical/skills/setup/` | 3 modes | 0 | — |
| ds-project | `canonical/skills/project/` | 3 modes | 1 | Partial SDLC chain; brief/lock not event-silent |
| ds-workflow | `canonical/skills/workflow/` | 1 mode | Backfill only | studio-onboard invocations attributed via migration, not live event |
| ds-career | `canonical/skills/career/` | 6 modes | 0 | External dependency; permanently disabled |

**Critical fact:** `skill_invocations` table has 1 row — `skill_id=unknown`. The schema for skill tracking exists (`skill_invocations`, `raw_skill_telemetry`); the live write path does not.

**Dead artifact:** `adapter-projections/` directory declared superseded since Slice 3. Contains `adapter-projections/claude/CLAUDE.md` which is still read by the installer compiler. Six of 8 files in that directory have no live readers.

---

## CLI

### Command Group Inventory

13 command groups in `interfaces/cli/ds.py`. All are operational. Event emission posture varies.

| Command group | Primary module | Event emitted? | Notes |
|---------------|---------------|----------------|-------|
| `ds project register` | `core/projects/mutations.py` | YES — `project.registered` | Writes `ds_projects` + emits via spool |
| `ds project set-active` | `core/projects/mutations.py` | NO | Silent state mutation |
| `ds project deactivate` | `core/projects/mutations.py` | NO | Silent state mutation |
| `ds work-order start` | `core/work_orders/start.py` | YES — `work_order.started` | Full spool path |
| `ds work-order close` | `core/work_orders/close.py` | YES — `work_order.closed` | Gate check runs first |
| `ds work-order block` | `core/work_orders/mutations.py` | YES — `work_order.blocked` | TA4 fix applied |
| `ds work-order unblock` | `core/work_orders/mutations.py` | NO | Silent state mutation |
| `ds work-order task-done` | `core/work_orders/mutations.py` | YES — `task.completed` | — |
| `ds milestone close` | `core/milestones/close.py` | YES — `milestone.completed` | — |
| `ds design-brief update/lock/fill` | `core/design_briefs/mutations.py` | NO | All three operations are event-silent |
| `ds task set-active` | `core/sdlc/active_task.py` | NO | Writes `active_task.json` only |
| `ds workflow start/status/list` | `control/execution/workflow/state.py` | NO (file-only during run) | Writes `workflows.json`; SQLite only at completion |
| `ds diagnostics list/clear` | `interfaces/cli/ds.py` | NO | File operations on `.jsonl` diagnostic files |

**Notable gap:** No `ds security` command group exists. Security is operator-invoked via `ds-security:` skill keyword only.

**Gate files:** `security_scan` gate at work-order close reads `.planning/work-orders/<id>/security-scan.md` — a gitignored file. Security milestone gate reads `.planning/milestones/<id>/security-audit.md`. Both gates are file-backed.

---

## Hooks

### Hook Dispatch Architecture

Two entry points:
- `emitters/claude_code/run.py` — PreToolUse/PostToolUse/Stop dispatcher. Reads `CLAUDE_PLUGIN_ROOT` and `USERPROFILE`.
- `runtime/hooks/dispatch/hooks.py` — Routes to 22 handlers based on hook type and matcher patterns.

### Handler Inventory

| Handler | Trigger | Canonical events emitted | SQLite write | File write |
|---------|---------|--------------------------|--------------|------------|
| `on-tool-activity` | PostToolUse | None | `hook_invocations`, `tool_invocations` (direct INSERT, 917 rows each) | `activity.json` |
| `on-post-tool-use` | PostToolUse | `token.consumed` (via CanonicalEventEnvelope → spool) | None direct | `diagnostics/token-capture.jsonl` |
| `on-security-scan` | PostToolUse Edit/Write | None | None (sec_hook_checks: 0 rows) | None (advisory print only) |
| `on-agent-correction` | PostToolUse Edit/Write | None | None (cor_skill_corrections: 0 rows) | `director-corrections.md` |
| `on-session-start` | SessionStart | None | `raw_sessions` (direct INSERT) | None |
| `on-session-end` | SessionEnd | None | `raw_sessions` (direct INSERT) | None |
| `on-context-threshold` | PostToolUse (context budget) | BROKEN — `from spool.emitter import write_harvest_event` fails (module DNE) | None | `pending-handoff.json` |
| `on-prompt-validate` | PreToolUse | None | None | Reads/mutates `pending-handoff.json` |
| `on-skill-load` | PreToolUse | None | None | None |
| `on-skill-complete` | PostToolUse | None | None | None |
| `on-skill-metrics` | PostToolUse | None | None | `skill-usage.jsonl` |
| `on-skill-telemetry` | Stop | None | None | `telemetry-buffer.jsonl` |
| `on-workflow-progress` | Stop | None | None | Reads `workflows.json` |
| `on-stop-handoff` | Stop | Indirect via `studio_db.py` | `raw_handoffs` (direct INSERT) | `.sessions/handoff-*.md` + `.sessions/recap-*.md` |
| `on-stop-dispatch` | Stop | None | None | Orchestration only |
| `on-pulse` | Stop | None | `hook_executions` (45 rows, on_pulse only) | `pulse-*.md` |
| `on-token-log` | Stop | None | None | `token-log.md` |
| `on-first-run` | Stop (first run) | None | None (`reg_skills`/`reg_workflows`: 0 rows) | `first-run.log` |
| `on-game-validate` | PostToolUse | None | None | None |
| `on-edit-dispatch` | PostToolUse Edit/Write | None (dispatcher only) | None | None |
| `on-session-harvest` | Stop (context) | BROKEN — calls `spool.session_harvester` which queries missing `file_count` column (should be `count`) | None | None |
| `on-skill-gate` | PostToolUse (unreachable) | None | None | None |

**Unreachable handlers** (not in any dispatcher entry): `on-startup-health.py`, `on-periodic-health.py`, `on-skill-gate.py`.

**Broken import fact:** `on-context-threshold.py` runs for every PostToolUse where context exceeds 75%. The ImportError is silent — the hook continues and writes `pending-handoff.json`. The 20 `context.threshold.crossed` events in `canonical_events` come from `run.py` PostCompact normalization, not actual threshold crossings.

---

## Database Tables

### Active Tables (41 tables with data)

Key active tables by domain:

**Event spine:** `canonical_events` (1,853 rows — significant backfill fraction; 22 distinct event types). `execution_events` (929 rows — projection from canonical, correctly v2-compliant).

**Telemetry (direct-write, not via spool):** `hook_invocations` (917 rows), `tool_invocations` (917 rows) — both via direct INSERT from `on-tool-activity`, bypassing L2.

**SDLC authority:** `ds_projects` (25 rows: 1 real active, 1 paused, 23 test fixture pollution), `ds_work_orders` (14 rows — all Dream Command), `ds_tasks` (9 rows), `ds_milestones` (4 rows — all pending), `ds_design_briefs` (1 row — Dream Command, locked).

**Learning/memory:** `reg_gotchas` (1,488 rows), `fts_gotchas` and shadows (1,488 rows each — FTS5 over gotchas).

**Sessions/handoffs:** `raw_sessions` (51 rows), `raw_handoffs` (26 rows), `ds_documents` (12 rows, type=session_handoff).

**Workflows:** `raw_workflow_runs` (2 rows), `raw_workflow_nodes` (25 rows), `workflow_invocations` (2 rows), `outcome_records` (2 rows) — all from 2 studio-onboard runs.

**Infrastructure:** `_schema_version` (61 rows — migration counter), `raw_sentinels` (113 rows), `validation_failures` (57 rows — all from on_pulse schema mismatch on `execution.completed`).

**Technology signals:** `ds_technology_signals` (54 rows — session harvester ingest).

**Skill tracking:** `skill_invocations` (1 row — `skill_id=unknown`), `raw_token_usage` (3 rows — all zero values).

### Empty Table Domains (141 tables, 0 rows each)

Grouped by domain:

| Domain | Table count | Representative tables |
|--------|-------------|----------------------|
| Security | 12 | `sec_cve_matches`, `sec_hook_checks`, `sec_manual_reviews`, `sec_sarif_findings`, `security_findings`, `guardrail_decisions`, `guardrail_rules_audit`, `hook_findings`, `risk_register`, `risk_mitigations`, `compliance_review_flags`, `production_readiness_findings` |
| Career | 14 | All `career_*` tables — external dependency (career_studio_path), permanently inactive |
| PRD | 9 | `prd_documents`, `prd_plans`, `prd_tasks`, `prd_sessions`, `prd_handoffs`, `prd_amendment_records`, `prd_version_records`, `prd_route_reconciliation_records`, `prd_sessions` |
| Project intelligence | 8 | `pi_analysis_runs`, `pi_bugs`, `pi_components`, `pi_dependencies`, `pi_improvements`, `pi_violations`, `pi_wave_tasks`, `pi_waves` |
| Production readiness | 5 | `production_readiness_assessment_runs`, `production_readiness_control_results`, `production_readiness_findings`, `production_readiness_remediation_work_orders`, `production_readiness_skill_control_mappings` |
| Adapters | 4 | `adapter_authority_profiles`, `adapter_executions`, `adapter_result_records`, `ai_adapter_accounting_profiles` |
| GitHub repo analysis | 8 | `github_repo_evaluations`, `github_repo_security_findings`, `github_repo_adoption_decisions`, etc. |
| Registry | 4 | `reg_skills` (0 rows — hydration not persisting), `reg_workflows` (0 rows), `telemetry_entity_registry`, `telemetry_module_registry` |
| Workflow execution graph | 4 | `execution_nodes`, `execution_outputs`, `execution_dependencies`, `execution_event_links` |
| Billing/usage | 4 | `ai_usage_operational_records`, `model_provider_profiles`, `ai_adapter_accounting_profiles`, `token_usage_records` |
| Monitoring/alerting | 4 | `alert_history`, `alert_rules`, `dashboard_attention_items`, `dashboard_authority_reconciliation_records` |
| Agents | 5 | `agent_invocations`, `agent_registry_records`, `agent_result_records`, `agent_context_scope_policies`, `capability_center_records` |
| SDLC (extended) | 10+ | `project_intake_records`, `project_intake_questions`, `project_health_scorecards`, `shared_context_packets`, `blocker_resolution_records`, etc. |
| Learning (broken pipeline) | 8 | `raw_approaches`, `raw_lessons`, `raw_skill_telemetry`, `raw_pulse_snapshots`, `cor_skill_corrections`, `learning_event_records`, `raw_tasks`, `raw_specs` |
| Other | 30+ | Various authority, compliance, connector, scheduling tables |

**Ratio:** 141 empty : 41 active = 3.4:1. Schema has grown substantially ahead of write-path implementation.

---

## Migrations

### Era Summary

| Era | Migration range | Primary intent | Current state |
|-----|----------------|---------------|---------------|
| Foundation | 001–010 | SDLC spine: `ds_projects`, `ds_work_orders`, `ds_milestones`, `ds_tasks`, `canonical_events`, `reg_skills`, `reg_workflows` | SDLC tables active; `reg_skills`/`reg_workflows` empty since creation |
| First Expansion | 012–034 | Security tables, workflow tables, PRD tables, career tables, adapter tables | All new domains remain empty (0 rows) |
| Post-Gap Expansion | 037–050 | `execution_events`, `hook_invocations`, `tool_invocations`, `token_usage_records` (created by 3 separate migrations: 037, 042, 043) | `hook_invocations`/`tool_invocations` active via direct write; `execution_events` active via projection; `token_usage_records` 0 rows |
| TA Series | 051–064 | Token attribution: retroactive SDLC spine events, `_built_from_event_id` column, dismantling `activity_log` | SDLC backfill complete; `activity_log` hub-and-spoke built (018-025) then reversed (062-063) |

**Total applied:** 61 (note: `_schema_version` shows 61 rows; Phase 0c inventory counted 61 migrations).

**Notable:** `token_usage_records` was created and altered by migrations 037, 042, and 043 — three separate migrations for one table — with 0 rows as the result.

**Notable:** The `activity_log` hub-and-spoke system (8 migrations to build, 2 to reverse) is the most complete v2 precursor that has ever been implemented and then dismantled in this system.

---

## Adapters

### Adapter System Inventory

| Adapter | Status | Install state | L1 tables populated |
|---------|--------|--------------|-------------------|
| claude_code | IMPLEMENTED | File-backed (`~/.dream-studio/integrations/claude_code/manifest.json`, 515 files) | 0 rows in `adapter_authority_profiles`, `adapter_executions`, `adapter_result_records` |
| codex | STUB | Not installed | — |
| cursor | STUB | Not installed | — |
| copilot | STUB | Not installed | — |
| chatgpt | STUB | Not installed | — |
| mcp | STUB | Not installed | — |
| shell | STUB | Not installed | — |
| local_model | STUB | Not installed | — |

**Critical gap:** `last_health_state` field in `manifest.json` is always `null`. The `integration.health.changed` event is never emitted. The full health circuit (adapter → L2 event → L3 `adapter_authority_profiles`) has never fired.

**Dead directory:** `adapter-projections/` is declared superseded since Slice 3 but not deleted. `adapter-projections/claude/CLAUDE.md` is still read by the installer compiler as a template input.

---

## Workflows

### Workflow Inventory

23 workflows in `canonical/workflows/`. All workflow YAMLs are installed.

| Workflow | Runs | Security nodes | Notes |
|----------|------|---------------|-------|
| `studio-onboard.yaml` | 2 (2026-05-18) | NONE | Only workflow that has actually executed; 13 confirmed nodes; readiness score 79/100 |
| `idea-to-pr.yaml` | 0 | `review-security` (skill: pr-security-scan) | Dormant; security findings would write to `.md` files not SQLite |
| `comprehensive-review.yaml` | 0 | `review-security` (skill: pr-security-scan) | Dormant |
| `project-audit.yaml` | 0 | `secure` node (skill: pr-security-scan) | Dormant |
| `security-audit.yaml` | 0 | Full ds-security pipeline (all 8 modes) | Dormant; client-level org security tool |
| `production-readiness.yaml` | 0 | `build-gate` (47 controls); `persist-authority-records` | **Never run; the most architecturally critical workflow for both security intents** |
| `audit-to-fix.yaml` | 0 | Conditional (audit=secure → pr-security-scan) | Dormant |
| `pre-push.yaml` | Git hook | NONE | 6 gates: format, lint, skill-sync, test-suite, atlas-leak, docs-drift |
| `fix-issue.yaml` | 0 | None | Contains Unix `head -1 <<<` syntax — fails on Windows |
| `ui-feature.yaml` | 0 | None | No persistence/record node — ships code with no record |
| `daily-close.yaml` | 0 | None | Would produce `draft-lessons/` files; pipeline not activated |
| `feature-research.yaml` | 0 | None | — |
| `idea-to-pr-simple.yaml` | 0 | None | — |
| `self-audit.yaml` | 0 | None | Cron schedule incorrectly points to `studio-onboard` not `self-audit` |
| 9 others | 0 | Varies | All dormant |

**CronCreate bug confirmed:** The studio-onboard run on 2026-05-18 scheduled `prompt=workflow: studio-onboard` instead of `prompt=workflow: self-audit`. The wrong workflow was scheduled.

---

## Documentation

### Documentation Inventory

`docs/` directory contains 30+ markdown files (flat layout — no `docs/architecture/` subdirectory despite CLAUDE.md references to `docs/architecture/` paths).

**Confirmed present and relevant:**
- `docs/ARCHITECTURE.md` — high-level component map and data flow (the closest doc to a system-level reference)
- `docs/DATABASE.md` — database schema overview
- `docs/HOOK_RUNTIME.md` — hook dispatch reference
- `docs/operator-guide.md` — operator-facing usage guide
- `docs/quickstart.md` — onboarding guide (references legacy CLI patterns)
- `docs/security-best-practices.md`, `docs/security-orchestration-pattern.md`, `docs/security-storage-layout.md` — security-specific docs
- `docs/WORKFLOWS.md`, `docs/WORKFLOW_RUNTIME.md` — workflow reference

**Contracts** (in `docs/contracts/`):
- `security-by-default-development-lifecycle-gate.md` — 172-line policy contract specifying SQLite-backed security findings at project_intake and deployment events; zero implementation
- Six Phase 16A contracts explicitly document file-based state as canonical (approved scoping for current phase)

**Documentation gaps confirmed in Phase 1h:**
- `copilot-setup.md` and `cursor-setup.md` reference missing `.marketplace/adapters/` path
- `quickstart.md` references legacy CLI patterns
- `design-skills-guide.md` references `huashu-design` (not a current skill name)
- 35 of 39 operational env vars are undocumented in any `docs/` file
- `docs/architecture/data-model-v2.md` does not exist (v2 target architecture is described only in `02-connection-analysis.md`)

---

## Configuration

### Environment Variable Summary (51 total)

9 of 13 file-path env vars configure runtime state with no SQLite equivalent:
- `DS_ACTIVE_TASK_PATH` → `~/.dream-studio/state/active_task.json`
- `DS_MACHINE_ID_PATH` → `~/.dream-studio/state/machine_id`
- `DS_PLATFORM_PROFILE_PATH` → `~/.dream-studio/state/platform.json`
- `DS_DIAGNOSTICS_DIR` → `~/.dream-studio/diagnostics/`
- `DS_DREAM_STUDIO_HOME` → integration manifest writes
- `DREAM_STUDIO_CORRECTIONS_PATH` → operator corrections file
- `DREAM_STUDIO_CONFIG` → adapter config file
- `DREAM_STUDIO_WORK_ORDER_ROOT` → `~/.dream-studio/meta/work-orders/` (with explicit `STORAGE_CLASS = "file_backed"` constant in `core/work_orders/models.py`)

Aligned: `DREAM_STUDIO_DB_PATH` (points to SQLite), `DS_SPOOL_ROOT` (intentional pre-ingest buffer).

### pyproject.toml Key Facts

**Coverage scope:** `hooks/lib` and `packs/domains/domain_lib` only. `fail_under = 70` applies to this narrow slice. `core/`, `runtime/`, `interfaces/`, `spool/`, `emitters/`, `projections/` not measured.

**Pyright scope:** `hooks/` and `tests/` only at `basic` level against Python 3.10. All production directories (`core/`, `runtime/`, `interfaces/`, etc.) have zero static type coverage.

**Pre-commit hooks:** Three total — `black`, `flake8`, `conventional-commits`. No security pre-commit hook (`bandit`, `pip-audit`, `detect-secrets`).

---

## Tests

### Test Volume and Distribution

| Tier | Files | Functions |
|------|-------|-----------|
| `tests/` root | 9 | 212 |
| `tests/core/` | 1 | 1 |
| `tests/evals/` | 7 | 99 |
| `tests/integration/` | 35 | 379 |
| `tests/integration/emitters/` | 1 | 10 |
| `tests/integration/integrations/` | 4 | 24 |
| `tests/integration/spool/` | 7 | 16 |
| `tests/runtime_verification/` | 1 | 2 (opt-in, never runs in CI) |
| `tests/unit/` root | 239 | 2,439 |
| `tests/unit/canonical/` | 7 | 80 |
| `tests/unit/emitters/` | 3 | 15 |
| `tests/unit/gates/` | 4 | 27 |
| `tests/unit/health/` | 1 | 16 |
| `tests/unit/hooks/` | 2 | 10 |
| `tests/unit/integrations/` | 11 | 145 |
| `tests/unit/spool/` | 5 | 23 |
| **Total** | **338** | **3,498** |

**26 xfail tests** in `tests/evals/test_dependency_chain.py`: 7 BROKEN (code defects with known causes), 11 UNKNOWN (require live Claude Code session), 8 UNTESTED (manual-only processes).

**`tests/validation/`:** 4 stale manual scripts never collected by pytest; reference old skill path `skills/core/` (pre-restructure).

### Critical Coverage Gaps

- **Brownfield intake:** Zero behavioral tests. `test_skill_contains_brownfield_check` is a documentation presence check only.
- **Security as SQLite gate:** No test verifies security blocks a project in SQLite. Existing gate tests verify file-backed (.planning/) behavior.
- **Projections subsystem:** 21+ route files, models, exporters, analyzers — zero direct tests.
- `projections/api/test_api_integration.py` is outside `testpaths` and double-gated by env var — never runs in standard CI.
- `projections.parsers.sarif_parser` — SARIF entry point, no tests.
- `core.milestones.close`, `core.milestones.mutations`, `core.milestones.queries` — tested only via CLI wrapper, not directly.
- `core.repo_actions.*` (8 files) — completely untested.

---

## Security Infrastructure

### Wiring State Summary

| Category | Items | Operational |
|----------|-------|-------------|
| ds-security skill modes | 8 | 0 (zero invocations in 6-day window) |
| ds-quality:pr-security-scan | 1 | 0 invocations |
| on-security-scan.py hook | 1 | WIRED but advisory only (5 fires, 0 rows written) |
| guardrails/evaluator.py | 1 | SCAFFOLDED — complete implementation, not registered in settings.json |
| guardrails/rules/security.yaml | 5 rules | STUB — triggers on `hook_finding.created`, an event never emitted |
| Scanner stubs (giskard, llm_guard, rebuff) | 3 | STUB — Python 3.12 incompatibility, not wired |
| Security DB tables | 12 | 0 rows each |
| Security API routes | 6 | Accessible; all return 0 results |
| Workflows with security nodes | 6 | All dormant |
| Security gate (work order close) | 1 | WIRED but resolves via file presence only |

**Ratio:** Security infrastructure is approximately 5% operational and 95% scaffolding by operational data.

---

## File-Based Runtime State Stores

### Complete Inventory

These stores violate Intent #1 (SQLite-first authority). Marker files (`.dream-studio-project`) are excluded — they are intentional by Intent #5.

| Store | Location | Active | SQLite equivalent | Migration effort |
|-------|----------|--------|-------------------|-----------------|
| `workflows.json` | `~/.dream-studio/state/` | Active (empty = no in-flight workflows) | `workflow_invocations` (archive only) | MEDIUM |
| `workflow-checkpoint.json` | `~/.dream-studio/state/` | Stale (test artifact from 2026-05-20) | `automation_checkpoints` (0 rows) | SMALL |
| `active_task.json` | `~/.dream-studio/state/` | Absent at audit time | `ds_tasks` flag column | SMALL |
| `activity.json` | `~/.dream-studio/state/` | Active (1,275 bytes) | Materialized view over `hook_invocations` | MEDIUM |
| `pending-handoff.json` | `~/.dream-studio/state/` | Stale/stuck in `in_progress` | `shared_context_packets` (0 rows) | SMALL |
| `platform.json` | `~/.dream-studio/state/` | Active (218 bytes) | New `ds_machine_profile` table | SMALL |
| `machine_id` | `~/.dream-studio/state/` | Active (36 bytes) | New `ds_machine_profile` table | SMALL |
| `installed-version` | `~/.dream-studio/state/` | Active (12 bytes) | New `ds_installation_records` table | SMALL |
| `hook-timing.jsonl` | `~/.dream-studio/state/` | Active (392 KB, 3,645 lines) | New `hook_timing_records` table | LARGE |
| `skill-usage.jsonl` | `~/.dream-studio/state/` | Active (3 lines, all `skill=unknown`) | `raw_skill_telemetry` (0 rows, flush broken) | MEDIUM |
| `telemetry-buffer.jsonl` | `~/.dream-studio/state/` | Active (1 line) | `raw_skill_telemetry` via pulse_collector | SMALL (fix flush) |
| `token-capture.jsonl` | `~/.dream-studio/state/diagnostics/` | Active (3,690 bytes) | New `diagnostic_records` table | MEDIUM |
| `.sessions/` files | `~/.dream-studio/.sessions/` | 58 files (55% not ingested to SQLite) | `raw_handoffs` + `ds_documents` | LARGE |
| `manifest.json` | `~/.dream-studio/integrations/claude_code/` | Active (515 file paths) | New `ds_installation_records` table | SMALL |
| `spool/ .sessions/{pid}.json` | `~/.dream-studio/events/.sessions/` | 1,102 files (accumulating) | Process coordination; `raw_sessions` pid field | SMALL |
| `director-corrections.md` | `packs/core/context/` | Active (18 lines, 750 bytes) | `cor_skill_corrections` (0 rows) | SMALL |
| `director-preferences.md` | `packs/core/context/` | Active (2,963 bytes) | `ds_documents` (type=director_preferences) | SMALL |
| `pulse-*.md` / `pulse-latest.json` | `~/.dream-studio/meta/` | Active (3 days silent) | `raw_pulse_snapshots` (0 rows, write broken) | SMALL |
| `token-log.md` | `~/.dream-studio/meta/` | Active | `raw_token_usage` (3 rows, all zero) | MEDIUM |
| `first-run.log` | `~/.dream-studio/meta/` | Active (27 KB) | `reg_skills`, `reg_workflows` (both 0 rows) | SMALL |
| `draft-lessons/` | `~/.dream-studio/meta/draft-lessons/` | 2 files | `raw_lessons` (0 rows) | SMALL |
| `security/scans/{client}/` | `~/.dream-studio/security/` | No files (ds-security never run) | `sec_sarif_findings` (0 rows) | MEDIUM |

---

## Dead / Removable Artifacts

Items confirmed to have no active read or write paths and no current consumers:

| Artifact | Location | Reason dead | Safe to remove |
|----------|----------|-------------|---------------|
| `adapter-projections/` (except CLAUDE.md) | `adapter-projections/` | Superseded since Slice 3; 6 of 8 files have no readers | YES (keep CLAUDE.md until compiler updated) |
| `tests/validation/T134_*.py`, `T145_*.py`, `check_db.py`, `check_video_tools.py` | `tests/validation/` | Reference `skills/core/` (old path); never collected by pytest | YES |
| `sigint_idle_test.py` | `tests/integration/spool/` | Not a pytest test; manual diagnostic script | YES (or move to scripts/) |
| `on-startup-health.py`, `on-periodic-health.py`, `on-skill-gate.py` | `runtime/hooks/` | Not reachable via any dispatcher | Confirm then remove |
| `shared/config.py` | `shared/` | Explicitly deprecated; `migration_version: 13` hardcoded (stale) | YES (after removing all imports) |
| `shared/paths.py` | `shared/` | Explicitly deprecated; emits DeprecationWarning on import | YES (after removing all imports) |
| `hooks/lib/migrate_files_to_sqlite.py`, `hooks/lib/document_store.py` | `hooks/lib/` | Coverage-omitted as Wave 0 infrastructure; likely v1 migration artifacts | Confirm then remove |
| `workflow-checkpoint.json` (stale) | `~/.dream-studio/state/` | Test artifact from 2026-05-20; `wf-fail-1` pattern | YES (manual delete) |
| `pending-handoff.json` (stale) | `~/.dream-studio/state/` | Stuck `in_progress` from 2026-05-21 session | YES (manual delete) |
