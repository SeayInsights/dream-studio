# Pass 1j — Tests Audit
*Phase 1 analysis | 2026-05-22*

---

## Stated Architectural Intents

1. **SQLite-first authority** — all runtime state must be SQLite-backed. File-based state is v1 rot.
2. **Security audit during brownfield onboarding** — security skills run during project intake, findings stored in SQLite.
3. **Security audit as SDLC lifecycle gate** — greenfield projects must pass security audit before going live.
4. **Canonical events as the spine** — all state changes flow through canonical_events.
5. **Marker file authority for attribution** — `.dream-studio-project` markers are identity source for project attribution.

---

## Test Directory Inventory

### tests/ (root) — 9 test files, 212 test functions

**What it is:** Top-level test files that predate the subdirectory reorganization. Mix of integration-style and unit tests. Includes a `factories.py` and `conftest.py` at this level.

**What it tests:** `control.research.tools`, `core.graph.query`, `projections.api.main`, `control.research`, `core.memory.retrieval`. Covers API discovery and research pipeline, graph query layer, think/research integrations, retrieval capability, and tool search.

**Current state:** ACTIVE — files appear to be maintained alongside newer tests.

**Coverage status:** Covers research/memory/graph sub-domains. The `projections.api.main` import is notable — it is one of the few places the projections API is touched by tests.

**Intent alignment:**
- Intent 2 (Security intake): NO
- Intent 3 (Security gate): NO
- Intent 4 (Events): NO — no event emission tests at this level

**Notes:** `factories.py` provides test data factories. `conftest.py` is the single global conftest for the entire test suite (no subdirectory conftest files exist anywhere). Validation tests in `tests/validation/` are not collected by pytest (no `test_` prefix on files); they are manual validation scripts.

---

### tests/core/ — 1 test file, 1 test function

**What it is:** Single file — `test_dual_write.py`.

**What it tests:** `core.event_store.studio_db` — specifically the dual-write migration path: `_insert_activity_log` must write to both `activity_log` (legacy) and `canonical_events` (spine).

**Current state:** ACTIVE.

**Coverage status:** Covers exactly one function in one module. The module `core.event_store.studio_db` is also covered more broadly in `tests/unit/` root. No other `core/` sub-modules have their own directory here.

**Intent alignment:**
- Intent 1 (SQLite-first): YES — asserts canonical_events row is written alongside legacy row
- Intent 4 (Events): YES — verifies dual-write produces a canonical event row

**Notes:** Structurally anomalous — a single test in its own directory. The test creates a temporary DB manually, bypassing the `guard_real_homedir` fixture. It pre-dates the fixture and uses its own connection management.

---

### tests/evals/ — 7 test files (8 with `__init__.py`), 99 eval functions

**What it is:** "Eval" tests — machine-checked projections of audit findings and behavioral contracts. Different from unit/integration tests: they assert invariants about how the system *should behave* according to spec documents, not just that code runs. Organized into named C-series checks (C1–C7).

**What it tests:**

| File | C-series | Coverage |
|------|----------|----------|
| `test_round_trip_evals.py` | C1 | `core.shared_intelligence.prd_authority`, `core.work_orders.*`, `core.config.sqlite_bootstrap` — full round-trip against real SQLite DB |
| `test_gate_evals.py` | C2 | `core.work_orders.close` — gate check functions directly |
| `test_skill_contract_evals.py` | C3 | `core.projects.*`, `core.milestones.*`, `core.work_orders.*`, `core.design_briefs.*` |
| `test_guardrail_enforcement_evals.py` | C4 | `guardrails.enforcement` — text detectors |
| `test_context_budget_evals.py` | C5 | `canonical.events.types`, budget payload builders |
| `test_dependency_chain.py` | C6 | Cross-cutting — 46 tests mapping the 8-chain audit; 26 are `xfail` |
| `test_database_grounding_evals.py` | C7 | DB-grounding: verifies skill functions call DB not session memory |

**Current state:** ACTIVE — C6 was last updated post A0/A3 reclassifications (2026-05-20).

**Coverage status:** Evals cover the "contract layer" — they assert that spec-mandated invariants hold. They are not coverage in the import-graph sense; they cross module boundaries intentionally.

**Intent alignment:**
- Intent 1 (SQLite-first): YES — C1 uses real SQLite DB; C7 verifies DB calls are made
- Intent 4 (Events): PARTIAL — C1 round-trip does not explicitly assert event emission; C6 has several event-chain links tested

**Notes on C6 xfail tests (26 of 46 tests are xfail):** These represent documented broken or unknown dependency chain links:

| Classification | Count | Examples |
|---|---|---|
| BROKEN | 7 | dispatcher not installed (C3-L1, C3-L3), workflow trigger missing (C4-L1), harvester schema mismatch (C7-L3, C7-L6), SKILL.md install gap (C8-L2) |
| UNKNOWN | 11 | Live behavioral tests required; Claude Code session-dependent (C1-L3, C1-L4, C2-L2, C4-L2, C4-L3, C5-L1, C5-L2, C5-L3, C8-L3 etc.) |
| UNTESTED | 8 | Manual-only processes: linter, design critique, memory harvest, model selector (C6-L3 through C6-L5, C7-L2, C7-L4, C7-L5, C4-L5) |

---

### tests/integration/ (root) — 35 test files, 379 test functions

**What it is:** Integration tests spanning hook dispatch chains, workflow execution, migration, session analytics, schema management, research pipeline, cloud backup, and daily learning pipeline.

**What it tests:** `core.event_store.studio_db`, `core.config.*`, `control.execution.*`, `control.session.*`, `core.telemetry.*`, `core.validation.*`, `core.research.store`, and hook handlers via the `handler` fixture.

**Subdirectory breakdown:**

Notable files:
- `test_hook_dispatch_chain.py` / `test_hook_dispatch_chain_e2e.py` — dispatcher invocation chains
- `test_hook_on_security_scan.py` — on-write security scanner hook (see Security section)
- `test_hook_on_tool_activity.py` — includes `test_security_suggest_fires_for_auth_file`
- `test_migration.py` / `test_schema_migrations.py` — database migration integrity
- `test_workflow_runner_e2e.py` / `test_workflow_idea_to_pr.py` — workflow DAG parsing and execution
- `test_session_analytics.py` / `test_session_tracking.py` — session state
- `test_cloud_backup.py` / `test_daily_learning_pipeline.py` — operational pipelines
- `test_approach_capture.py` / `test_backfill.py` — SDLC data backfill

**Current state:** ACTIVE.

**Coverage status:** Integration tests heavily cover the hook layer (12 hook-specific test files). Workflow coverage focuses on idea-to-pr; studio-onboard has no dedicated integration test.

**Intent alignment:**
- Intent 2 (Security intake): PARTIAL — `test_hook_on_security_scan.py` tests the on-write security hook, not intake-time security
- Intent 3 (Security gate): NO — no integration test verifies security as a required workflow step before project goes live
- Intent 4 (Events): PARTIAL — some hook dispatch tests implicitly verify event emission paths

---

### tests/integration/emitters/ — 1 test file, 10 test functions

**What it is:** Integration test for the Claude Code emitter dispatch — `test_claude_code_dispatch.py`.

**What it tests:** Subprocess-based: fires the emitter as a child process and verifies spool files are created. No direct project module imports.

**Current state:** ACTIVE.

**Intent alignment:**
- Intent 4 (Events): YES — verifies that hook payloads produce spool files (write_envelopes path)

---

### tests/integration/integrations/ — 4 test files, 24 test functions

**What it is:** Integration tests for the installer/integrations subsystem. Covers doctor health checks, dry-run install, full install chain, and status reporting.

**What it tests:** `integrations.health`, `integrations.installer.claude_code`, `integrations.detector`, `integrations.installer.*`.

**Current state:** ACTIVE.

**Coverage status:** `test_install_chain_complete.py` verifies that `studio-onboard.yaml` is installed alongside `idea-to-pr.yaml` — this is the only test that references studio-onboard, and it only checks file presence, not workflow execution.

**Intent alignment:**
- Intent 2 (Security intake): NO
- Intent 3 (Security gate): NO
- Intent 4 (Events): NO

---

### tests/integration/spool/ — 7 test files (8 with `__init__.py`), 16 test functions

**What it is:** Integration tests for the spool pipeline — the file-to-SQLite event ingestion chain. The most technically precise integration tests in the suite.

**What it tests (file by file):**

| File | What it proves |
|------|---------------|
| `test_decoupled_pipeline.py` | `write_envelopes` writes to spool/ only; SQLite is untouched until ingest |
| `test_ingestor_sqlite.py` | `write_event` + `ingest()` produces a `canonical_events` row |
| `test_minimal_pair.py` | Minimal emitter + ingest + cleanup pair; regression guard |
| `test_spool_end_to_end.py` | Hook JSON → emitter → spool write → `ingest_pending` → processed/ |
| `test_sqlite_isolation.py` | SQLite connections are isolated per test (no shared state) |
| `test_cli_event_chain.py` | CLI work_order start/close → valid envelopes → ingestor processes without failure; SQLite has rows |
| `test_ta6_e2e_attribution.py` | Full SDLC hierarchy chain: task_id → work_order_id → milestone_id → project_id consistent in canonical_events and ds_* tables; `token.consumed` events carry `attribution_status: "fully_attributed"` when active task is set |
| `sigint_idle_test.py` | *Not a pytest test* — manual SIGINT diagnostic script; runs a 30-second sleep loop to characterize Windows phantom SIGINT behavior |

**Current state:** ACTIVE — TA6 is the most recently added test, proving the full attribution chain.

**Coverage status:** These tests do not import source modules by name (subprocess/file-based), but they exercise the critical spool pipeline end-to-end: `emitters.shared.spool_writer`, `spool.ingestor`, `spool.states`, `canonical.events.envelope`.

**Intent alignment:**
- Intent 1 (SQLite-first): YES — explicitly proves spool-to-SQLite path works
- Intent 4 (Events): YES — most direct tests of canonical event production in the suite
- Intent 5 (Markers): PARTIAL — TA6 tests marker-based project resolution for attribution

---

### tests/runtime_verification/ — 1 test file, 2 test functions

**What it is:** `test_write_paths.py` — a guard-enabled runtime verification test. Skipped by default unless `DREAM_STUDIO_RUNTIME_WRITE_VERIFY=1` is set.

**What it tests:** End-to-end write path verification against the *real* operator database (not a test DB). Tests `core.events.emitter.emit_event` and `core.event_store.studio_db._insert_activity_log` by counting rows before/after.

**Current state:** DORMANT in CI — requires explicit env var activation. Two test functions (`test_event_emission`, `test_activity_log`) are defined but only run on-demand.

**Intent alignment:**
- Intent 1 (SQLite-first): YES — designed to prove real DB write paths work
- Intent 4 (Events): YES — directly tests `emit_event` produces a canonical_events row

**Notes:** The trace-stage verification (`TRIGGER → PREPARE → EXECUTE → COMMIT → VERIFY`) is not used by any other test. This pattern exists only here.

---

### tests/unit/ (root) — 239 test files, 2439 test functions

**What it is:** The dominant test tier. Covers the full breadth of the codebase through unit tests, contract tests, regression gates, and static structural assertions.

**What it tests:** All major source domains: `core.*`, `canonical.*`, `interfaces.cli.*`, `projections.api.*` (partial), `guardrails.*`, `emitters.*`, `spool.*`, `control.*`, `integrations.*`.

**Current state:** ACTIVE — continuously extended.

**Coverage status:** See "Untested Critical Paths" section for gaps. The unit tier has the broadest coverage but leaves the `projections/` subsystem almost entirely untested.

**Intent alignment summary:**
- Intent 1 (SQLite-first): YES — many tests assert SQLite is the authority; `test_shared_intelligence_sqlite_authority.py`, `test_install_bootstrap_sqlite_authority.py`, `test_database_governance.py`
- Intent 3 (Security gate): PARTIAL — `test_work_order_close_extraction.py` tests `security_scan` gate at work order level; `test_milestone_close.py` tests `security-audit.md` gate at milestone level. Both gates are FILE-BACKED, not SQLite-backed (see Intent Divergence section).
- Intent 4 (Events): YES — extensive; see Event Emission Tests section
- Intent 5 (Markers): YES — `test_ta3_token_capture.py` has 12 marker-related tests

---

### tests/unit/canonical/ — 7 test files, 80 test functions

**What it is:** Contract and schema tests for the canonical layer.

**What it tests:** `canonical.events.types`, `canonical.events.envelope`, migration completeness, the ds-project SKILL.md content, the ds-quality:audit skill content, the redactor, documentation existence.

**Intent alignment:**
- Intent 4 (Events): YES — `test_types.py` verifies EventType registry; `test_envelope.py` verifies envelope construction and validation
- Notable: `test_ds_project_skill.py :: test_skill_contains_brownfield_check` — the only test in the suite that directly asserts "brownfield" appears in a SKILL.md. It checks that the ds-project SKILL.md text mentions brownfield; it does NOT test brownfield behavior.

---

### tests/unit/emitters/ — 3 test files, 15 test functions

**What it is:** Unit tests for the emitter layer — Claude Code emitter, tool normalization, spool writer.

**What it tests:** `emitters.claude_code.emitter` (indirectly via assertions on output), `emitters.shared.spool_writer`.

**Intent alignment:**
- Intent 4 (Events): YES — `test_spool_writer.py` verifies that spool writer creates files for envelope lists

---

### tests/unit/gates/ — 4 test files, 27 test functions

**What it is:** Unit tests for the pre-push gate subsystem.

**What it tests:** `core.gates.pre_push`, `canonical.events.types`, `canonical.events.envelope`, `interfaces.cli`.

**Intent alignment:**
- Intent 4 (Events): YES — `test_pre_push_event.py` verifies gate events use canonical envelopes

---

### tests/unit/health/ — 1 test file, 16 test functions

**What it is:** `test_doctor_skill_sync.py` — verifies doctor health checks are in sync with installed skills.

**What it tests:** `core.health.doctor`.

---

### tests/unit/hooks/ — 2 test files, 10 test functions

**What it is:** `test_context_threshold.py` and `test_session_start.py` — subprocess-based hook tests.

**What it tests:** Hook handlers via subprocess (no direct project imports).

---

### tests/unit/integrations/ — 11 test files, 145 test functions

**What it is:** Unit tests for the integrations subsystem — compiler, detector, installer components, settings merge, manifest.

**What it tests:** `integrations.compiler.claude_code`, `integrations.detector`, `integrations.installer.*`, `integrations.manifest`, `integrations.targets.claude_code.settings_merge`, `integrations.health`.

**Coverage status:** Thorough coverage of the installer contract and verification logic.

---

### tests/unit/spool/ — 5 test files, 23 test functions

**What it is:** Unit tests for spool state machine components.

**What it tests:** `spool.ingestor` (state transitions), `spool.states` (state directory logic), `spool.writer` (envelope serialization), `spool.session_cleanup`.

**Intent alignment:**
- Intent 4 (Events): YES — verifies spool state transitions and file movement

---

### tests/validation/ — 0 pytest-collected test files, 4 scripts

**What it is:** Manual validation scripts — `T134_end_to_end_validation.py`, `T145_end_to_end_validation.py`, `check_db.py`, `check_video_tools.py`. None have `test_` prefix so pytest does not collect them. These are one-off validation runs from earlier development phases. `T134` references `skills/core/modes/think/SKILL.md` (old path, pre-restructure); `T145` tests research integration.

**Current state:** STALE — paths reference old skill directory layout (`skills/core/` vs current `canonical/skills/`).

---

## Special Focus: Security and Brownfield Tests

### Brownfield Onboarding (Intent #2)

**Verdict: No tests for brownfield onboarding workflow.**

The only test that uses the word "brownfield" is:

```
tests/unit/canonical/test_ds_project_skill.py :: test_skill_contains_brownfield_check
```

This test asserts that the text "brownfield" appears somewhere in the ds-project SKILL.md file. It is a *documentation presence check*, not a behavioral test. It does not:
- Test that security runs during project intake
- Test that brownfield findings are stored in SQLite
- Test any function that implements brownfield-specific behavior
- Test the `studio-onboard` workflow

The `tests/integration/integrations/test_installer_complete.py` verifies that `studio-onboard.yaml` is *installed* (file presence). It does not test what the workflow does.

There are no tests for:
- `studio-onboard.yaml` workflow execution
- Security scanning running during project intake
- Brownfield security findings being recorded to `canonical_events` or any SQLite table
- The `ds-security` skill being invoked during project intake

### Security as SDLC Gate (Intent #3)

**Verdict: Security gate tests exist but are FILE-BACKED, not SQLite-backed.**

The following tests verify security-as-gate behavior:

**Work order level (file-backed):**
- `test_work_order_close_extraction.py :: test_run_gate_check_security_scan_fails_when_blocked` — reads `security-scan.md` from `.planning/work-orders/<id>/`; presence of "BLOCKED" in file content causes gate failure
- `test_work_order_gates.py :: test_close_exits_1_when_pre_gate_fails` — CLI exit code when gate fails

**Milestone level (file-backed):**
- `test_milestone_close.py :: test_close_fails_when_security_audit_has_blocked` — reads `security-audit.md` from `.planning/milestones/<id>/`; presence of "BLOCKED" blocks milestone close
- `test_milestone_close.py :: test_milestone_status_shows_open_gate_checks` — open checks list includes `security_audit`
- `test_milestone_close_extraction.py :: test_close_milestone_returns_gate_failures_list`

**Contract/lifecycle tests:**
- `test_security_lifecycle_gate.py` — 6 tests on `core.security.lifecycle.build_security_lifecycle_gate()` and `classify_security_impact()`. Tests the 47-control framework classification, release merge requirements, and skill mapping.
- `test_critique_gate.py :: test_skill_invoke_security_scan_writes_artifact_template` — verifies that invoking `security:scan` writes a template artifact file
- `test_secure_production_readiness_gate.py :: test_full_release_review_includes_security_and_readiness_controls`

**What is not tested:**
- No test verifies that a greenfield project *cannot* go live without passing a security gate in SQLite
- The security gate check reads files from `.planning/` — a directory that is gitignored and local-only (see feedback_planning_gitignored.md). The gate implementation is file-backed, which conflicts with Intent #1 (SQLite-first authority)
- No test verifies that `core.security.event_emitter.emit_security_event` produces a row that is consulted by the gate logic

**On-write security scanner tests (separate concern):**
`tests/integration/test_hook_on_security_scan.py` tests the `on-security-scan` hook handler — a real-time scanner that fires when Claude Code writes source files. This tests *code scanning during development*, not *security as a project lifecycle gate*. It is a different intent from Intent #3.

---

## Special Focus: Skipped and XFail Tests

### Skipped Tests (3 total — all platform-conditional)

| Test | File | Reason |
|------|------|--------|
| `test_run_cmd_resolves_plugin_root_from_launcher_path` | `tests/unit/test_hook_runtime_reliability.py` | `os.name != "nt"` — Windows-only (run.cmd) |
| `test_run_cmd_resolves_prompt_dispatcher_without_env_root` | `tests/unit/test_hook_runtime_reliability.py` | `os.name != "nt"` — Windows-only |
| `test_launcher_shell_script_is_executable_on_nonwindows` | `tests/unit/integrations/test_installer_complete.py` | `sys.platform == "win32"` — chmod not reliable on Windows |

No tests are unconditionally skipped. All three skips are `skipif` with platform conditions, meaning they run on the correct platform. The first two run only on Windows; the third runs only on non-Windows.

### XFail Tests (26 total — all in tests/evals/test_dependency_chain.py)

All xfail tests use `strict=False`. They represent documented dependency chain gaps from the 2026-05-17/2026-05-20 chain audit. Classifications and counts:

| Classification | Count | Root cause category |
|---|---|---|
| BROKEN | 7 | Code defects: missing dispatcher entries, workflow trigger keyword absent, schema column mismatch |
| UNKNOWN | 11 | Behavioral gaps requiring live Claude Code session; cannot be unit-tested |
| UNTESTED | 8 | Manual-only processes with no automation trigger |

Key broken chains:
- C3-L1/C3-L3: Dispatcher entries missing from installer template (hooks_template.json has only emitter entries)
- C4-L1: `workflow:` trigger keyword absent from installed routing table
- C7-L3: `spool.session_harvester` queries `file_count` but migration 055 column is `count` — schema mismatch
- C8-L2: Mode-level SKILL.md files not installed (only ds-bootstrap is installed)

---

## Special Focus: Event Emission Tests

The test suite has substantial coverage of canonical event emission across multiple tiers:

**Emission path verification (spool/SQLite):**
- `tests/integration/spool/test_decoupled_pipeline.py` — write does not ingest; spool/SQLite are decoupled
- `tests/integration/spool/test_ingestor_sqlite.py` — ingestor produces canonical_events row
- `tests/integration/spool/test_spool_end_to_end.py` — full hook-to-processed pipeline
- `tests/integration/spool/test_cli_event_chain.py` — CLI operations produce valid envelopes
- `tests/core/test_dual_write.py` — legacy write produces canonical event

**Envelope contract verification:**
- `tests/unit/canonical/test_envelope.py` — construction, validation, missing fields rejection
- `tests/unit/test_envelope_correctness.py` — start_work_order, close_work_order, close_milestone produce well-formed envelopes
- `tests/unit/test_event_emission_reliability.py` — security emitter routes through spool; no direct SQL INSERT

**Specific operation event tests:**
- `test_ta0_sdlc_events.py` — project creation, work order creation emit with full SDLC trace
- `test_ta1_task_lifecycle.py` — task create/delete emit canonical events
- `test_ta3_token_capture.py` — PostToolUse hook emits token.consumed with correct attribution_status
- `test_ta4_attribution_enforcement.py` — SDLC events without attribution trigger diagnostics
- `tests/unit/test_work_order_gates.py` — close emits work_order.closed; force emits gate_bypassed
- `tests/unit/test_work_order_close_extraction.py` — close emits work_order.closed envelope
- `tests/unit/test_milestone_close_extraction.py` — milestone close emits milestone.completed; force emits gate_bypassed
- `tests/unit/test_skill_invoke_extraction.py :: test_record_skill_invocation_emits_skill_invoked_event`
- `tests/unit/test_task_attribution.py` — task operations emit
- `tests/unit/test_work_order_tasks.py :: test_task_done_emits_task_completed_event`

**Boundary/constraint tests:**
- `test_event_contract_boundaries.py` — projection API must not write/emit canonical events; adapter interfaces must not own event store persistence
- `test_projection_contract_boundaries.py` — API routes do not directly write canonical runtime tables
- `test_governance_privacy_boundaries.py` — scanner outputs write only security evidence surfaces
- `test_dashboard_safety.py :: test_event_emission_tests_exist` — meta-test: asserts that event emission tests exist

**Gap in event emission tests:** No test verifies that `core.milestones.mutations` or `core.milestones.close` emit canonical events — these modules are in the Phase 0c untested list.

---

## Untested Critical Paths

From Phase 0c Gap 8: 131 modules identified as not directly imported by any test file. Critical modules among them:

### High severity — core state mutation with no tests

| Module | Why critical |
|--------|-------------|
| `core.milestones.close` | Milestone close is a high-impact operation; has tests for the CLI wrapper but not the module itself |
| `core.milestones.mutations` | Milestone create/update mutations; untested directly |
| `core.milestones.queries` | Milestone read path; untested directly |
| `core.design_briefs.mutations` | Design brief mutations; test coverage via CLI tests only |
| `core.design_briefs.queries` | Design brief read path |
| `core.dispatch.bus` | Dispatch bus — event routing; no tests |
| `core.sdlc.active_task` | Active task management — critical for attribution chain |
| `core.sdlc.cwd_resolver` | CWD-based project resolution; tested only indirectly via hooks |
| `core.skills.invocation` | Skill invocation layer; no direct tests |
| `core.skills.queries` | Skill query layer |
| `core.projections.consumers` | Projection consumers — canonical event consumers |
| `core.projections.framework` | Projection framework |
| `core.projections.workflow_consumer` | Workflow event projections |
| `core.repo_actions.*` (8 files) | Repo action subsystem — executor, feedback, formatter, generator, model, planner, priority, runner |

### High severity — security subsystem gaps

| Module | Why critical |
|--------|-------------|
| `canonical.skills.analyze.*` (9+ files) | All analyze domain skill files untested |
| `canonical.adapters.claude.statusline` | Adapter statusline — no tests |

### Large untested block — projections/

The entire projections subsystem except `projections.api.main` is untested:

- 21 route files in `projections.api.routes.*` (alerts, analytics, audits, exports, frontend, hooks, insights, intelligence, metrics, prd, realtime, reports, security, shared_intelligence, telemetry, etc.)
- `projections.api.models.*` (insights, metrics, reports)
- `projections.api.queries.token_attribution`
- `projections.api.websocket.connection_manager`
- All `projections.core.*` analyzers, insights, email, notifications, reports, SLA tracker, streaming
- All `projections.exporters.*` (10+ files: chart_renderer, CSV, Excel, PDF, PowerBI, PPTX exporters)
- `projections.parsers.sarif_parser` — SARIF security report parser; no tests

The SARIF parser absence is notable: it is the entry point for structured security report ingestion, and it has no tests.

### Moderate severity — infrastructure

| Module | Why notable |
|--------|-------------|
| `core.storage.document_store` | Document storage abstraction |
| `core.monitoring.validation_monitor` | Validation monitoring |
| `core.pricing.claude_models` | Model pricing — used by cost accounting |
| `projections.config.settings` | Projections service configuration |
| `emitters.shared.spool_writer` | Listed as untested in Phase 0c, but covered via integration tests; the module itself is not directly imported by test files |

---

## Findings

**F1 — Test volume is high but concentrated.** 3,498 test functions across 338 test files. The unit tier dominates (2,439 functions). The `tests/unit/` root contains 239 files that span the full codebase breadth but rely on direct module imports — modules not imported are not tested.

**F2 — The spool pipeline is well-covered.** `tests/integration/spool/` (9 files, 16 functions) provides direct end-to-end proof of the canonical event pipeline from hook payload to SQLite row. This is the most mechanically precise tier in the suite.

**F3 — Security gate tests are file-backed, not SQLite-backed.** Both the work order `security_scan` gate and the milestone `security-audit` gate check for the presence and content of `.planning/` files. The `.planning/` directory is gitignored and local-only. This creates a test-only artifact dependency and conflicts with Intent #1 (SQLite-first authority).

**F4 — Brownfield onboarding has zero behavioral tests.** The `test_skill_contains_brownfield_check` test is a documentation presence check. The studio-onboard workflow has no execution test. Security during project intake has no test. This is the largest gap relative to stated architectural intent.

**F5 — 26 xfail tests document broken chains.** All in `test_dependency_chain.py`. Seven are classified BROKEN — code defects with known root causes. Eleven are UNKNOWN — they require live Claude Code sessions and cannot be automated. Eight are UNTESTED — manual-only processes with no trigger mechanism.

**F6 — The projections subsystem (21+ route files) has no tests.** The dashboard and reporting surface is entirely untested by direct import. Only `projections.api.main` is imported (in `tests/` root and some unit tests) to verify route registration. Route handler logic, models, exporters, and analyzers have no test coverage.

**F7 — `tests/validation/` is effectively dead.** Four scripts that are never collected by pytest. `T134` and `T145` reference the old skill path layout (`skills/core/`) which no longer exists. These are stale artifacts from pre-restructure development.

**F8 — `tests/runtime_verification/test_write_paths.py` is opt-in and never runs in CI.** Requires `DREAM_STUDIO_RUNTIME_WRITE_VERIFY=1`. The trace-stage pattern it uses (`TRIGGER → PREPARE → EXECUTE → COMMIT → VERIFY`) is not replicated anywhere else. It tests the real operator DB, making it unsuitable for automated CI but potentially valuable for operator diagnostics.

**F9 — conftest.py is a single global file with no subdirectory overrides.** The `guard_real_homedir` autouse fixture is comprehensive (8 env vars guarded) but applies uniformly to all tests. Subdirectory-specific fixture customization is not used.

**F10 — `sigint_idle_test.py` is not a pytest test.** It is a manual diagnostic script in the spool integration directory. Its presence alongside `test_*.py` files is potentially confusing.

---

## Intent Divergence

| Intent | Test coverage verdict | Specific divergence |
|--------|----------------------|---------------------|
| Intent 1 — SQLite-first | TESTED at spine level; NOT TESTED at gate level | Security gates and design brief gates read `.planning/` files, not SQLite. Tests validate this file-backed behavior, which conflicts with the stated intent. |
| Intent 2 — Security during brownfield intake | NOT TESTED | No behavioral tests for brownfield onboarding path. Only documentation presence test exists. |
| Intent 3 — Security as SDLC gate | PARTIALLY TESTED | Gate mechanics tested but implementation is file-backed (.planning/ files), not SQLite-backed. No test verifies that a project is blocked from going live in SQLite until security passes. |
| Intent 4 — Canonical events as spine | WELL TESTED | Extensive coverage at emission, validation, and constraint layers. Attribution chain fully tested via TA6. Key gap: milestone mutations module not directly tested. |
| Intent 5 — Marker file authority | WELL TESTED | `test_ta3_token_capture.py` has 12 marker-related tests covering resolution, malformation, orphan detection, and CLI write. |

---

## Open Questions

1. **Security gate implementation vs. intent:** The security gate checks `.planning/work-orders/<id>/security-scan.md` and `.planning/milestones/<id>/security-audit.md`. These are file-backed artifacts. Is this intentional (file as artifact, SQLite as ledger), or is this the file-based v1 rot described in Intent #1? The tests validate the current file-backed behavior without surfacing this ambiguity.

2. **Brownfield intake pathway:** Does a code path exist for running security during project intake (the studio-onboard workflow)? The workflow YAML exists at `canonical/workflows/studio-onboard.yaml`. Does it include a security step? No test checks this.

3. **C6 xfail resolution ownership:** 7 BROKEN xfail tests represent actionable engineering work. Are these tracked as work orders? The `xfail` markers are in `test_dependency_chain.py` with `strict=False` — they will pass when they fail and pass when they succeed, providing no CI signal on regressions. Should these be `strict=True` once fixes land?

4. **projections/ test coverage gap:** The entire projections subsystem (dashboard routes, exporters, analyzers) has no direct tests. Is this intentional (projections are "views" not "authority") or is this a coverage gap that will grow as the dashboard is used in production?

5. **SARIF parser has no tests:** `projections.parsers.sarif_parser` is the entry point for structured security report ingestion into the dashboard. With no tests, the correctness of security finding parsing cannot be verified automatically.

6. **`tests/validation/` cleanup:** Should T134, T145, check_db.py, and check_video_tools.py be removed or updated? They reference stale paths and are never collected by pytest.
