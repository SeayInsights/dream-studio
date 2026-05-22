# Dream Studio — What's Broken and the Remediation Roadmap
*Phase 3 Synthesis | 2026-05-22*

---

## PART A — Findings by Severity

Severity definitions used in this document:
- **Critical:** System actively misbehaves or silently lies in a way that makes the operator believe something is true that is not. Includes broken import chains, stale state files, and data integrity violations.
- **High:** An architectural intent is structurally unachieved. The gap is wide enough that fixing it requires deliberate engineering work, not a one-line fix.
- **Medium:** Partial implementation or broken pipeline that degrades a named feature but does not silently mislead. The system still mostly works.
- **Low:** Configuration drift, dead code, missing documentation, or cosmetic inconsistency. No functional impact on the primary operator workflows.

---

### Critical Findings

#### C1 — `on-context-threshold.py` silently fails with ImportError on every invocation
**Evidence:** `from spool.emitter import write_harvest_event` fails because `spool/emitter.py` does not exist. The hook continues silently (Python catches the ImportError at import time, not invocation time — the module is imported when dispatched). Every context threshold crossing since installation has silently failed to emit any canonical event. The 20 `context.threshold.crossed` events in `canonical_events` are PostCompact normalization artifacts from `run.py`, not actual threshold crossings. The `pending-handoff.json` file is written as the fallback, meaning the cross-session handoff coordination still happens via file — but the operator has no L2 record of any threshold event.
**Specific fix:** Create `spool/emitter.py` with `write_harvest_event()` function, or update the import to use the correct existing spool write path (`emitters.shared.spool_writer`).

#### C2 — `pending-handoff.json` is stale and stuck in `in_progress` with no TTL
**Evidence:** File at `~/.dream-studio/state/pending-handoff.json` contains `status: "in_progress"` with `triggered_at` = 2026-05-21 ~8:44 PM. As of audit time (2026-05-22 ~1:53 PM), this is ~17 hours old. `on-prompt-validate.py` transitions status from `pending` to `in_progress` when it injects handoff context. There is no expiry check in any reader — the `in_progress` record persists indefinitely. The consequence is that the next session may incorrectly inject stale handoff context, and `on-stop-dispatch.py` sees a file that looks "in progress" when it should be cleared.
**Specific fix:** Add TTL check in `on-prompt-validate.py` and `on-stop-dispatch.py` (e.g., discard `triggered_at` older than 300 seconds). Immediate action: delete the stale file manually.

#### C3 — Test fixture contamination of `ds_projects` (23 of 25 rows are pytest artifacts)
**Evidence:** `ds_projects` has 25 rows. 23 are test fixture rows from pytest runs that bypassed the `guard_real_homedir` autouse fixture (which redirects `DREAM_STUDIO_DB_PATH` to a temp DB in tests). These rows exist in `~/.dream-studio/state/studio.db` — the production database. The active project resolver queries `ds_projects WHERE status='active' ORDER BY updated_at DESC`. With 23 contaminating rows, any query using loose filtering could return a test fixture as the active project. The documented mismatch (MEMORY.md says Dream Command is active; DB shows Dream Studio as active) is a symptom.
**Specific fix:** Write a migration (065) that DELETEs rows from `ds_projects` where `project_id` matches known test fixture patterns (UUIDs used in test factories, or via a `is_test_fixture` column that gets backfilled). Audit `guard_real_homedir` fixture to ensure it applies before any DB connection in every test module.

#### C4 — `guardrails/evaluator.py` has a stale `activity_log` dependency (table removed in TA0c)
**Evidence:** `guardrails/evaluator.py` queries `activity_log` to resolve trigger conditions when evaluating rules. Migration 062-063 (TA0c workstream) dismantled `activity_log` — the table no longer exists. If `evaluator.py` were activated (registered in `settings.json`), every evaluation attempt would fail with a SQLite "no such table" error. The file `guardrails/rules/security.yaml` also triggers on `event_type: "hook_finding.created"` — an event type never emitted by any hook. Two separate failures exist: broken data dependency + broken trigger event.
**Specific fix:** Update `evaluator.py` to query `canonical_events` or `hook_invocations` instead of `activity_log`. Update `security.yaml` rule triggers to reference an emitted event type. Then register in `settings.json`.

#### C5 — `workflow-checkpoint.json` is a stale test artifact in the production state directory
**Evidence:** `~/.dream-studio/state/workflow-checkpoint.json` contains `wf-fail-1 / n1 / failed / 2026-05-20T21:59:02Z`. The `wf-fail-1` pattern matches pytest test fixtures, not real workflow runs. `WorkflowRunner.run` reads this file on startup to check for a checkpoint to resume. A real workflow run named `wf-fail-1` that starts and hits node `n1` would attempt to resume from this checkpoint — potentially executing a failed-state resume path against real state.
**Specific fix:** Delete the file immediately (manual action). Then add validation in `WorkflowRunner.run` that a checkpoint's `workflow_key` matches an actual workflow in `raw_workflow_runs` before attempting resume. Add TTL check (e.g., discard checkpoints older than 24 hours).

---

### High Findings

#### H1 — Security Intent #2 (brownfield intake) has zero implementation
**Evidence:** `studio-onboard.yaml` has no security node — confirmed by the 13-node execution record from 2026-05-18. `ds-project:scope` SKILL.md Phase 1 (Brownfield Check) calls `analyze:intelligence` only. `register_project` in `core/projects/mutations.py` fires no security trigger. `production-readiness.yaml` lists `project_intake` as a full-review event, but the workflow has never run and is not invoked by any intake path. The `security-by-default-development-lifecycle-gate.md` contract states intake security is required. The contract is accurate; the implementation is absent.
**Impact:** Every project registered since installation (including Dream Studio, Dream Command, and any future project) has been onboarded without any security audit.

#### H2 — Security Intent #3 (SDLC gate) is a file presence check, not a scan requirement
**Evidence:** `core/work_orders/close.py` security_scan gate: checks for `wo_dir / "security-scan.md"` file existence and absence of "BLOCKED". The gate applies to 6 of 10 work order types (api_endpoint, authentication, saas_feature, data_pipeline, deployment, infrastructure). An operator can create this file manually — or it can be created by any process writing a file with no scan content — and the gate passes. No security skill is invoked. No SQLite security table is consulted. The gate name (`security_scan`) misrepresents its function (file presence check).
**Impact:** 6 work order types formally require security scans but the gate cannot distinguish between a real scan and an empty file.

#### H3 — 20 of 22 hook handlers bypass L2 (canonical events)
**Evidence:** Only `on-post-tool-use` (via `token_capture.py`) and `run.py` (via `emitters/claude_code/emitter.py`) produce canonical events via the spool. The other 20 handlers write directly to file-based stores or L3 tables (direct INSERT), or produce no persistent record at all. The hook execution record in `hook-timing.jsonl` (3,645 lines) is entirely outside SQLite. Session lifecycle, handoff lifecycle, skill invocation lifecycle, and workflow progress are all invisible to canonical event consumers.
**Impact:** The majority of system activity is unobservable through the canonical event spine. Downstream projections, dashboards, and operators relying on `canonical_events` see a partial picture.

#### H4 — `ds_projects` active project resolver is unreliable due to test contamination and mismatch
**Evidence:** The resolver (`ds_projects WHERE status='active' ORDER BY updated_at DESC`) returns Dream Studio as active, but MEMORY.md states Dream Command is the active project. 23 test fixture rows exist in the table. The mismatch means any session-start logic that reads the active project from SQLite may resolve to the wrong project. Attribution for canonical events (which carry `project_id`) depends on this resolver's correctness.
**Impact:** Token attribution, work order association, and skill invocation linkage may be associating to the wrong project.

#### H5 — `production-readiness.yaml` has never run and is not in any automatic invocation path
**Evidence:** `production_readiness_assessment_runs` table: 0 rows. `production_readiness_findings` table: 0 rows. The workflow has 0 runs in `raw_workflow_runs`. The workflow is not referenced by `studio-onboard.yaml`, not referenced by any work order type's `workflow_template` field, and not in any SKILL.md as a triggered workflow. It is available only by manual invocation (`workflow: production-readiness`).
**Impact:** The workflow that is architecturally designated as the correct answer for both security intents has never provided any operator value. Its `persist-authority-records` node — which would write to SQLite production readiness tables — has never fired.

#### H6 — Design brief lifecycle is invisible to canonical events (L3 direct write, no L2)
**Evidence:** `ds design-brief update`, `lock`, and `fill` all call `core/design_briefs/mutations.py` which writes directly to `ds_design_briefs`. No `CanonicalEventEnvelope` is emitted for any design brief operation. The 1 row in `ds_design_briefs` (Dream Command brief, locked) has no L2 counterpart. The design brief lock gates WO3 from starting — a gating event with no canonical event record.
**Impact:** Design brief lifecycle is invisible to projections. The most visible SDLC gating event currently blocking real work (WO3 for Dream Command) has no event record.

#### H7 — `hook_invocations` and `tool_invocations` (917 rows each) are direct-INSERT L3 violations
**Evidence:** `core/telemetry/emitters.py:emit_hook_tool_activity()` calls `INSERT INTO hook_invocations` and `INSERT INTO tool_invocations` directly, triggered by `on-tool-activity`. No corresponding canonical event exists for these 1,834 rows. These are the most populated non-spool L3 tables in the system, and both violate the v2 population model (L3 should be populated by projection from L2).
**Impact:** Tool-use telemetry is recorded but disconnected from the event spine. Projections over tool-use patterns must read `hook_invocations` directly rather than deriving from `canonical_events`.

#### H8 — 141 of 182 SQLite tables (77%) are empty — schema overreach without write paths
**Evidence:** See `03a-what-exists.md` for full list by domain. Security (12), PRD (9), career (14), project intelligence (8), production readiness (5), adapters (4), GitHub repo analysis (8), and 70+ others all have 0 rows. Migrations created valid schema infrastructure that no projection or writer has ever populated.
**Impact:** A reader of the schema would believe these domains are implemented. They are not. The empty table ratio creates false confidence in architectural completeness. Maintenance cost: every migration must avoid collisions with 141 tables that are maintained for aspirational purposes.

#### H9 — Skill telemetry has no authoritative store and all records have `skill=unknown`
**Evidence:** `skill-usage.jsonl` has 3 lines, all with `skill="unknown"`. `telemetry-buffer.jsonl` has 1 line with `skill_name="unknown"`. `raw_skill_telemetry` has 0 rows. The skill name resolution is broken at the write site in `on-skill-metrics.py`. Even if the flush pipeline to `raw_skill_telemetry` were fixed, the data would be semantically empty.
**Impact:** There is no reliable record of which skills have been invoked, when, or in what context. The `skill_invocations` table has 1 row from the upgrade tool. Skill-level observability is entirely absent.

#### H10 — `reg_skills` and `reg_workflows` have been empty since migration 003 (foundational intent never achieved)
**Evidence:** Both tables created in migration 003 as the canonical registries for skills and workflows. `first-run.log` records that `hydrate_registry_once` ran, but the hydration function does not INSERT into these tables. `reg_skills`: 0 rows. `reg_workflows`: 0 rows. The canonical skills live in `canonical/skills/` as file-based SKILL.md files; there is no SQLite registry of what skills exist, what modes they expose, or what their routing keywords are.
**Impact:** The `packs.yaml` file is the de facto skill registry. Any feature that depends on `reg_skills` or `reg_workflows` as the authoritative registry is reading empty tables.

---

### Medium Findings

**M1 — `on-security-scan.py` fires but writes nothing.** 5 invocations, 0 rows in `sec_hook_checks`, 0 events emitted, advisory print only. The hook-to-DB write path for security findings was never implemented.

**M2 — `.sessions/` handoff ingest is manual and has fallen 55% behind.** 58 session files exist; 26 are in `raw_handoffs`. The `ds memory ingest` command is the ingest path but requires manual invocation. Approximately 32 sessions of handoff data are in files only.

**M3 — Workflow live state is file-backed during execution.** `workflows.json` is the authority during a workflow run. SQLite (`workflow_invocations`, `raw_workflow_runs`) receives data only at completion. If the process dies during a workflow run, the live state exists only in the file.

**M4 — Token count data is not reliably stored anywhere.** `raw_token_usage` has 3 rows with zero values. `token_usage_records` has 0 rows. `token-log.md` is written by `on-token-log.py` but the SQLite equivalent receives no data. Token cost accounting is file-backed and unreliable.

**M5 — Session lifecycle (`raw_sessions`, 51 rows) is a direct-INSERT L3 write with no L2 record.** `session.started` and `session.ended` are not event types in `canonical_events`. Session-level context for event attribution is missing from the event spine.

**M6 — `ds project set-active`, `ds project deactivate`, and `ds work-order unblock` are silent state mutations.** These transition the most important SDLC entities (project active state, work order blocked state) with no canonical event. State transitions are invisible to any consumer relying on `canonical_events`.

**M7 — Three orphaned hook handlers are unreachable.** `on-startup-health.py`, `on-periodic-health.py`, `on-skill-gate.py` are in `runtime/hooks/` but not registered in any dispatcher. They consume maintenance attention but produce no system behavior.

**M8 — The `self-audit` cron job is scheduled to run `studio-onboard` instead.** The studio-onboard run on 2026-05-18 created a cron job with `prompt=workflow: studio-onboard` where `prompt=workflow: self-audit` was intended. The scheduled self-audit is currently scheduling re-onboarding instead.

**M9 — `spool/events/processed/` accumulates indefinitely.** 1,593 files with no pruning mechanism. `events/.sessions/{pid}.json` also accumulates (1,102 files). Both grow without bound.

**M10 — `shared/config.py` and `shared/paths.py` are explicitly deprecated but still imported.** `shared/paths.py` emits `DeprecationWarning` at import time, but `filterwarnings = ["ignore::DeprecationWarning"]` in `pyproject.toml` silences it. Dead code paths through these modules are invisible in test output.

**M11 — ds-quality mode name mismatch: canonical says `secure`, installed routing says `pr-security-scan`.** `canonical/skills/quality/SKILL.md` references `modes/secure/SKILL.md` and keyword `secure:`, but all installed/routing configurations use `pr-security-scan`. Skill authors reading the canonical source file would build against the wrong name.

**M12 — Coverage configuration measures only `hooks/lib` and `packs/domains/domain_lib`.** The `fail_under = 70` threshold is meaningless as a codebase health indicator. `core/`, `runtime/`, `interfaces/`, `spool/`, `emitters/`, and `projections/` are not measured.

**M13 — 17 coverage omissions carry "temporary" labels with no work order references.** All labeled "add tests in Wave 1/Wave 6/follow-up." No dates, no issue numbers. Several are likely dead code (`migrate_files_to_sqlite.py`, `document_store.py`).

**M14 — `fix-issue.yaml` contains Unix-only syntax (`head -1 <<<`) that fails on Windows.** The operator's environment is Windows 11 Pro. This workflow cannot execute.

**M15 — Pyright scope excludes `core/`, `runtime/`, `interfaces/` — the three highest-impact production directories.** Static type coverage is limited to `hooks/` and `tests/` at Python 3.10 basic mode. Type errors in the production core are invisible to the type checker.

---

### Low Findings (brief list)

**L1 —** `adapter-projections/` directory is superseded since Slice 3 but not deleted. `adapter-projections/claude/CLAUDE.md` is still read by the installer compiler.

**L2 —** `tests/validation/T134_*.py`, `T145_*.py`, `check_db.py`, `check_video_tools.py` are stale, reference old skill paths, never collected by pytest.

**L3 —** `quickstart.md` references legacy CLI patterns. `copilot-setup.md` and `cursor-setup.md` reference missing `.marketplace/adapters/` path. `design-skills-guide.md` references `huashu-design`.

**L4 —** 35 of 39 operational env vars are undocumented in any `docs/` file. `ANTHROPIC_API_KEY`, `SENTRY_DSN`, `JINA_API_KEY`, `EMAIL_PASSWORD` are used in production code but not documented.

**L5 —** `shared/config.py` hardcodes `"migration_version": 13` in the default config JSON. 54 migrations have been applied. This literal is stale and misleading.

**L6 —** Two session directory conventions exist simultaneously: `~/.dream-studio/.sessions/` (hidden) and `~/.dream-studio/projects/<name>/sessions/` (non-hidden). Both are in `core/config/paths.py`.

**L7 —** `write_pulse()` triggers a full `sqlite3.backup()` (SQLite Online Backup API) on every invocation. Pulse writes can be frequent, making DB backup frequency coupled to pulse write frequency.

**L8 —** `projections/api/test_api_integration.py` is outside `testpaths` and double-gated by `DREAM_STUDIO_RUN_LEGACY_API_INTEGRATION`. Never runs in standard CI.

**L9 —** `sigint_idle_test.py` is a manual diagnostic script in `tests/integration/spool/`. Not a pytest test; potentially confusing alongside `test_*.py` files.

**L10 —** The guardrail pilot-mode conversion dates (`convert_to_block: "2026-05-13"` in `security.yaml` rules) passed 9 days ago with no upgrade from advisory to block.

---

## PART B — Remediation Roadmap

This roadmap is organized into phases numbered to continue from the existing workstream cadence. Phases are sketched, not spec'd — each phase heading describes scope and rationale. Individual work orders will be defined when the phase begins.

Each phase is preceded by an operator decision prompt where choices affect scope or approach.

---

### Phase 18.0 — Emergency Cleanup (Before Any New Feature Work)
**Rationale:** Critical findings C1–C5 include a silently broken hook (C1), stale file state that could inject wrong context (C2, C5), production database contamination (C3), and a dependency on a removed table (C4). These are not technical debt — they are active misconfigurations that cause the system to lie or fail silently.

**Workstream sketch:**

1. **Create `spool/emitter.py`** (C1): Minimal implementation of `write_harvest_event()` that wraps the existing spool write path. Update `on-context-threshold.py` to use it. Verify that context threshold events appear in `canonical_events` after the fix.

2. **Add TTL guards to handoff coordination** (C2): In `on-prompt-validate.py`, add expiry check before consuming `pending-handoff.json`. In `on-stop-dispatch.py`, add TTL check before reading. Immediate manual action: delete stale `pending-handoff.json` and `workflow-checkpoint.json`.

3. **Clean test fixture contamination from `ds_projects`** (C3): Write migration 065 to DELETE known test fixture rows. Identify contamination by cross-referencing with test factory patterns. Audit `guard_real_homedir` fixture to prevent recurrence.

4. **Update `guardrails/evaluator.py` data dependency** (C4): Replace `activity_log` references with `canonical_events` or `hook_invocations`. This is a prerequisite for Phase 18.4.

5. **Fix `self-audit` cron schedule** (M8): Correct the CronCreate invocation in `studio-onboard.yaml` or update the scheduled cron entry to use `workflow: self-audit`.

**Gate before 18.1:** `canonical_events` receives context threshold events. `pending-handoff.json` has TTL enforcement. `ds_projects` contamination count < 5. Evaluator compiles without import error.

---

### Phase 18.1 — Event Spine Completeness (Core SDLC Gaps)
**Rationale:** High findings H6 (design brief invisible), H3 subset (session lifecycle), and H5 subset (project status mutations) represent SDLC-layer events that should exist in `canonical_events` but don't. These are small, targeted fixes — one event emission per missing operation.

**Workstream sketch:**

1. **Design brief event emission**: Add `CanonicalEventEnvelope` emission to `core/design_briefs/mutations.py` for `design_brief.created`, `design_brief.updated`, `design_brief.locked`. This directly addresses the invisible gating of WO3.

2. **Silent SDLC mutation events**: Add event emission to `ds project set-active`, `ds project deactivate`, `ds work-order unblock`. These are simple mutations — the pattern is already established in the existing mutation functions.

3. **Session lifecycle events**: Add `CanonicalEventEnvelope(session.started)` and `CanonicalEventEnvelope(session.ended)` emission to `on-session-start.py` and `on-session-end.py`. Use the spool path, not direct INSERT to `raw_sessions`.

**Gate before 18.2:** Design brief lock event appears in `canonical_events`. Project and work order status changes appear in `canonical_events`.

---

### Phase 18.2 — File-Backed State Migration (Small/Medium Migrations)
**Rationale:** From the storage architecture audit, 11 stores have SMALL migration effort and 5 have MEDIUM effort. This phase targets the stores where the SQLite schema already exists and the primary work is wiring the write path.

**Priority order (schema already exists, wire the write):**

1. **`telemetry-buffer.jsonl` → `raw_skill_telemetry`**: Fix `pulse_collector.py` flush. The schema is present; the pipeline is broken at the last stage.

2. **`raw_pulse_snapshots` write path**: Fix `on-pulse.py` to INSERT to `raw_pulse_snapshots`. The schema exists; the write call was never added.

3. **`director-corrections.md` → `cor_skill_corrections`**: Wire `on-agent-correction.py` to write to `cor_skill_corrections` at the same time it writes the markdown file. Schema exists.

4. **`first-run.log` → `reg_skills` + `reg_workflows`**: Wire `hydrate_registry_once` to persist discovered skills/workflows to the registry tables. This is a Phase 18.2 priority because it enables skill-level observability downstream.

5. **`active_task.json` → `ds_tasks` pointer**: Add `is_active` flag column to `ds_tasks` (migration 066). Update `core/sdlc/active_task.py` to write to the column rather than (or in addition to) the JSON file. The attribution chain depends on this pointer — making it SQLite-backed would improve reliability when the file is absent.

6. **`pending-handoff.json` → new `ds_handoff_requests` table** (migration 067): Single-row table with session_id, triggered_at, status, cwd. Cross-session hook coordination moves to SQLite.

**Phase 18.2b — Medium migrations:**

7. **`workflows.json` live state → `workflow_invocations`**: Extend `workflow_invocations` to carry in-flight node state. `cmd_status` and `cmd_list` read from DB instead of file. The live-state-in-file pattern is the last remaining case where SQLite cannot serve as the runtime authority during an operation.

8. **Fix `skill-usage.jsonl` skill name resolution**: The `skill=unknown` value in all records means the write site in `on-skill-metrics.py` is not resolving the skill name. Fix the resolution before the triple-store problem (M9) is meaningful to address.

**Gate before 18.3:** `raw_skill_telemetry` receives data from the flush pipeline. `reg_skills` is populated after `hydrate_registry_once`. `ds_tasks` carries the active pointer.

---

### Phase 18.3 — `.sessions/` Ingest Automation
**Rationale:** 58 session files vs 26 `raw_handoffs` rows — the ingest is falling behind at roughly 55% coverage. Manual `ds memory ingest` is not keeping up with session creation rate. This is a medium-effort change to the Stop hook.

**Workstream sketch:**

1. **Automate `ds memory ingest` at Stop time**: Add a call to the memory ingest pipeline at the end of `on-stop-dispatch.py`. The ingest should be non-blocking (run in the background or queue for the next ingest pass) so it doesn't extend Stop hook latency.

2. **Ingest backlog**: After automating, run a one-time backlog ingest of the 32 uningest files.

3. **Spool processed/ and sessions/ pruning**: Add a pruning step in `on-stop-dispatch.py` (or a separate periodic hook) that deletes `events/processed/` files older than N days and `events/.sessions/{pid}.json` files whose session has been confirmed ingested. Define N with operator input.

**Gate before 18.4:** `raw_handoffs` row count is within 5% of session file count. `events/processed/` is pruned to 0 files older than 7 days.

---

### Phase 18.4 — Security Infrastructure Activation (Intent #3 First)
**Rationale:** This is the largest remediation scope. The security domain is 5% operational and 95% scaffolding. The recommended sequencing starts with Intent #3 (SDLC gate, since this is lower-level) before Intent #2 (brownfield intake, which requires the SDLC gate infrastructure to be in place first).

**Workstream sketch (Intent #3 — SDLC gate):**

1. **Replace file-based `security_scan` gate with SQLite query**: Update `core/work_orders/close.py` to query `security_findings` (or a new `wo_security_scan_records` table) instead of checking `security-scan.md`. The gate should pass only if a confirmed scan record exists for the work order ID with no blocking findings.

2. **Wire `on-security-scan.py` to emit `hook_finding.created` events**: The hook fires 5 times in 6 days. Add `CanonicalEventEnvelope(hook_finding.created)` emission when `scan_for_patterns()` finds issues. Write to `hook_findings`. This provides the trigger event that `guardrails/evaluator.py` needs (C4 fixed in Phase 18.0 is a prerequisite).

3. **Register `guardrails/evaluator.py` in `settings.json`**: One settings.json hook registration entry (PostToolUse Edit|Write). The evaluator already has proper CanonicalEventEnvelope emission and `guardrail_decisions` writes — it just needs the entry point.

4. **Implement SARIF import endpoint** (T007): The `POST /security/sarif/import` endpoint is explicitly stubbed. Implement `projections/parsers/sarif_parser.py` and wire it to `sec_sarif_findings`. This unblocks the ds-security:scan → SQLite path.

**Workstream sketch (Intent #2 — brownfield intake):**

5. **Add security step to `studio-onboard.yaml`**: Add a `security-intake` node after the discovery phase. Use `skill: pr-security-scan` at minimum; optionally invoke `production-readiness` workflow for full intake. Write findings to `sec_manual_reviews` or `security_findings`.

6. **Add security step to `ds-project:scope` SKILL.md Phase 1 (Brownfield Check)**: The skill's Phase 1 currently calls `analyze:intelligence` only. Add a security scan step.

7. **Define `production-readiness.yaml` trigger path**: Either add it as a step in `studio-onboard.yaml` (for intake), or wire it as a work order type `workflow_template` for the `deployment` type. Make the invocation path explicit — this workflow should not require manual operator invocation for the intake and deployment cases.

**Gate before 18.5:** The `security_scan` work-order gate queries SQLite. At least one `hook_finding.created` event appears in `canonical_events` after the hook is activated. `studio-onboard.yaml` includes a security step.

---

### Phase 18.5 — Telemetry Spine Completion (H3 Hook Bypass)
**Rationale:** 20 of 22 hook handlers bypass L2. The highest-priority gaps are the high-volume ones: `hook-timing.jsonl` (3,645 lines, LARGE migration) and the session/handoff lifecycle events.

**Workstream sketch:**

1. **Create `hook_timing_records` table** (migration 068): Replace `hook-timing.jsonl` analytics with a SQLite table. Columns: `handler`, `duration_ms`, `status`, `invoked_at`, `session_id`. Writer: update `dispatch_helpers.write_timing()` to INSERT into this table. Reader: rewrite `ds_analytics/harvester.py` to use `SELECT handler, AVG(duration_ms) FROM hook_timing_records GROUP BY handler`. This is LARGE effort due to write frequency (~730 inserts/day) — WAL mode write performance must be validated.

2. **Emit canonical events for handoff lifecycle**: Update `on-stop-handoff.py` to emit `handoff.created` via spool in addition to the direct INSERT to `raw_handoffs`. Eventually deprecate the direct INSERT.

3. **Emit canonical events for workflow lifecycle**: Add `workflow.started` and `workflow.node.completed` event emission to `control/execution/workflow/state.py`. These events would finally give live workflow runs a canonical record.

**Gate before 18.6:** `hook_timing_records` table exists and receives data. `canonical_events` has `handoff.created` and `workflow.started` event types for new activity.

---

### Phase 18.6 — Schema Rationalization and Dead Code Cleanup
**Rationale:** 141 empty tables, orphaned handlers, deprecated modules, stale validation scripts, and superseded artifacts accumulate maintenance cost. This phase makes a deliberate decision about each category: migrate (if the write path is now in place from earlier phases), deprecate (mark as aspirational infrastructure with no planned implementation timeline), or remove.

**Workstream sketch:**

1. **Operator decision on aspirational schema**: For each of the 11 empty domains (security now partially addressed, plus PRD, career-external, project intelligence, production readiness, adapters, GitHub repo analysis, billing, monitoring, workflow execution graph, agents): decide whether to keep the schema as aspirational scaffolding, or drop the tables. Dropping is a migration; keeping requires documentation of the decision. Career tables are a special case (external dependency — recommend a single `-- EXTERNAL DEPENDENCY: career_studio_path` comment in the migration and do not drop).

2. **Remove orphaned handlers**: `on-startup-health.py`, `on-periodic-health.py`, `on-skill-gate.py` are unreachable. Remove after confirming no external call sites.

3. **Remove deprecated modules**: `shared/config.py`, `shared/paths.py` after removing all remaining imports (suppressed by `filterwarnings` — grep for remaining callers first).

4. **Clean up stale validation scripts**: Remove `tests/validation/T134_*.py`, `T145_*.py`, `check_db.py`, `check_video_tools.py`.

5. **Remove `adapter-projections/` dead files**: Keep `adapter-projections/claude/CLAUDE.md` until the installer compiler is updated to not reference it. Remove the other 7 files.

6. **Consolidate dual workflow tables**: Assess whether `raw_workflow_runs` + `workflow_invocations` should be merged. This requires a migration and a schema authority decision.

7. **Document env vars**: Write `docs/env-vars.md` covering all 39 undocumented env vars, particularly the secrets (`ANTHROPIC_API_KEY`, `SENTRY_DSN`, `JINA_API_KEY`, `EMAIL_PASSWORD`, `GITHUB_PERSONAL_ACCESS_TOKEN`).

8. **Fix `fix-issue.yaml` Windows compatibility**: Replace `head -1 <<<` with a cross-platform equivalent.

**Gate before 18.7:** The count of empty tables not formally designated as aspirational is < 20. All orphaned hook handlers are removed or formally registered. Deprecated module imports are 0.

---

### Phase 18.7 — v2 Model Completion (L3 Projections)
**Rationale:** The highest-fidelity architecture goal. Currently, the v2 model is only correctly implemented for `execution_events` (the one true L2→projection→L3 path). For all other domains, L3 is populated by direct INSERT or not at all. This phase extends the projection pattern.

**Workstream sketch:**

1. **Write the `design_briefs` projection**: After Phase 18.1 adds design brief events to L2, write a projection that populates a read model from those events. This makes design brief state derivable from `canonical_events`.

2. **Write the `skill_invocations` projection**: After Phase 18.2 fixes `reg_skills` population and skill name resolution, write a projection from `skill.invoked` events in `canonical_events` to `skill_invocations`. Retire the upgrade-tool population path.

3. **Write the `session_lifecycle` projection**: From `session.started`/`session.ended` events (added in Phase 18.1) to `raw_sessions`. The direct-INSERT path in `studio_db.py` can remain as a fallback during the transition.

4. **Scope the `hook_invocations` projection decision**: The v2 model requires `hook_invocations` to be populated by projection from L2. Currently it is a direct INSERT. Moving it to projection-from-events would require emitting a `hook.invoked` canonical event for every tool use — a potentially very high event volume. This may be the one case where pragmatically accepting the Drift is the correct choice. Operator decision required.

5. **Document the v2 model**: Write `docs/architecture/data-model-v2.md` (currently absent). Document which domains are Aligned, Drift, and Gap. This serves as the ongoing audit reference so the Phase 3 synthesis does not need to be re-run from scratch.

---

## PART C — Operator Decisions Required

These are architectural forks where the correct answer depends on operator intent, priority, or risk tolerance. They are not answerable from the audit evidence alone.

---

### OD1 — What is the intended write path from `ds-security scan:ingest` to `sec_sarif_findings`?

**Context:** `ds-security:scan` SKILL.md specifies file storage at `~/.dream-studio/security/scans/{client}/{repo}/{date}/`. `sec_sarif_findings` exists in the schema. `POST /security/sarif/import` is stubbed as T007. No ETL script connects the file store to the table.

**Decision:** Is the intended path (a) SKILL.md writes files, and a separate ingest step writes to SQLite (requiring T007 implementation), or (b) the SKILL.md itself should be updated to write to `sec_sarif_findings` directly, or (c) the security skill pipeline is intended as a file-only workflow (for portability to other clients) and `sec_sarif_findings` is populated by a separate CLI ingest command?

**Impact:** Determines whether Phase 18.4 scope includes implementing T007 or updating the SKILL.md storage specification.

---

### OD2 — Should `hook_invocations` and `tool_invocations` be migrated to the L2→projection path?

**Context:** These are the most populated L3 tables (917 rows each), written via direct INSERT from `on-tool-activity`. Moving to the correct v2 model would require emitting a `hook.invoked` canonical event for every tool use — potentially 917+ new events per session, significantly increasing `canonical_events` volume.

**Decision:** (a) Accept the Drift — formally designate these tables as "direct-write L3" and document this as an intentional exception, (b) move to projection-from-events at higher event volume, or (c) compress to a sampling strategy (emit only high-significance tool uses as canonical events).

**Impact:** Determines the shape of Phase 18.7's scope for the telemetry domain.

---

### OD3 — Should aspirational empty tables be dropped or kept?

**Context:** 100+ empty tables across 11 domains (PRD, project intelligence, production readiness, adapters, GitHub repo analysis, billing, monitoring, workflow execution graph, agents, compliance, alerting). Career tables have an external dependency and should be treated separately.

**Decision:** (a) Keep all empty tables — they represent future aspirational architecture and removing them would require migrations to re-add them later, (b) drop specific domains that have no planned implementation timeline within 6 months, or (c) keep but formally document each domain as "aspirational scaffolding, no current implementation timeline" in a schema governance doc.

**Impact:** Affects Phase 18.6 migration count and ongoing maintenance surface.

---

### OD4 — What is the production-readiness.yaml invocation path?

**Context:** This workflow is architecturally designated as the correct answer for both security intents (project_intake, release_merge, deployment are in its `run_policy.full_review_events`). It has never run. It is not in any automatic invocation path.

**Decision:** (a) Wire it to `studio-onboard.yaml` as a post-discovery security step (makes it automatic for all new project intakes), (b) wire it as a required step before `ds milestone close` for deployment milestones, (c) keep it as a manual-invocation workflow but add prominent documentation of the trigger conditions, or (d) decompose its responsibilities into smaller modular steps distributed across existing hooks and gates.

**Impact:** Determines the most critical single item in Phase 18.4's scope. Option (a) or (b) makes Intent #2 or Intent #3 achievable without building new workflows.

---

### OD5 — What should happen to the 6 Phase 16A file-backed contracts?

**Context:** `approval-contract`, `eval-artifact-contract`, `work-ledger-contract`, `work-order-contract`, `work-result-contract`, and `state-contract` (workflow row) all explicitly document file-based state as canonical for the current phase. This was intentional scoping. As Phase 18.2 migrates some of these stores to SQLite, the contracts will become outdated.

**Decision:** (a) Update contracts incrementally as each store is migrated (higher maintenance overhead but keeps contracts accurate), (b) mark all 6 contracts as "Phase 16A only, superseded by Phase 18.x" with a forward reference (lower overhead, but contracts become historical artifacts), or (c) maintain contracts as living documents with a schema_version field that tracks migration state.

**Impact:** Determines the documentation maintenance pattern for Phase 18.2 and beyond.

---

### OD6 — Should `ds-security:review` (Opus, 3-phase methodology) be wired to any workflow?

**Context:** `ds-security:review` is the deeper security review mode (Opus model, 3-phase methodology). It has never been invoked. Workflows with security nodes use `ds-quality:pr-security-scan` (Sonnet, lighter). The two modes are independent with no handoff between them.

**Decision:** (a) Wire `ds-security:review` as the default security node in `idea-to-pr.yaml` or `comprehensive-review.yaml` (higher cost per run, deeper findings), (b) keep `pr-security-scan` as the default workflow security node but invoke `ds-security:review` as an escalation path for HIGH/CRITICAL findings, (c) keep the current separation (pr-security-scan for workflow, ds-security:review for manual deep reviews), or (d) define `ds-security:review` as the gate before `ds milestone close` for security-relevant milestones.

**Impact:** Affects Phase 18.4 scope and ongoing security review cost per workflow run.

---

### OD7 — What is the intended behavior of `hook_invocations` vs `canonical_events` for tool-use telemetry?

**Context:** `hook_invocations` (917 rows, direct INSERT) and `canonical_events` (1,853 rows, spool) are both written for tool use activity, but they carry different data — `hook_invocations` has per-tool-use records (tool name, duration, session), while `canonical_events.tool.execution.completed` events (822 rows) carry envelope metadata. They are not duplicates; they are complementary records of the same events.

**Decision:** (a) Designate `canonical_events` as authoritative and deprecate `hook_invocations` (requires writing a migration of the complementary fields into the canonical envelope), (b) designate `hook_invocations` as the L3 tool-use telemetry table (accept the Drift permanently, document it formally), or (c) merge the two records by writing the hook-level fields into the canonical event payload at emission time.

**Impact:** Affects Phase 18.5 and 18.7 scoping. Also affects the shape of tool-use analytics queries.

---

### OD8 — Should `events/processed/` be pruned after N days?

**Context:** 1,593 processed spool files accumulate indefinitely. Each file is the original JSON envelope that was inserted into `canonical_events`. Since `canonical_events` is the SQLite authority, the processed files are technically redundant. However, they serve as an audit trail of raw events before schema validation.

**Decision:** (a) Prune after N days (recommend 7–14) — `canonical_events` is the authority, processed files are redundant after ingest, (b) keep indefinitely — processed files are a debugging and recovery resource, (c) move to a compressed archive (tar/gz per day) to reduce file count while preserving the raw record.

**Impact:** Affects Phase 18.3 scope. Low urgency but the count grows at ~300/day based on observed activity.
