# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## Phase 18.1.13 — Install correctness + packaging: 12 pieces, fresh-install BLOCKER fixes (2026-05-24)

### Fixed
- `pyproject.toml` now contains a `[project]` section — `pip install -e .` was failing on fresh machines with "No `[project]` table in your pyproject.toml"
- Three runtime dependencies added to `requirements.txt`: `python-pptx`, `openpyxl`, `pytest-asyncio` (missing from prior inventory)
- Floating deps pinned; `pip check` conflicts resolved (3 conflicting packages); `requirements.lock` generated
- Missing `__init__.py` files added across 6 packages (`runtime/`, `interfaces/`, `interfaces/cli/`, `shared/`, and two others) — resolves `ModuleNotFoundError` on fresh installs
- Migration `011_memory_entries.sql` added; fresh-install migration gap closed: `_ensure_tables()` now validates the schema version rather than silently creating tables when migrations have not run
- `ds` CLI commands now exit 0 on success; exit-code regression test added (`tests/unit/cli/test_exit_codes.py`)
- `install.ps1` and `install.sh` now run `pip install -e .` and `ds rehearsal-install` before `ds integrate install` — prior scripts skipped both
- README: fixed clone URL (was pointing to non-existent repo path), version badge, and CI badge
- `test_github_pr_cicd_release_gate.py` assertion updated to `dream-studio-clean` repo name (unblocked `pr-smoke` CI gate)

### Added
- `docs/operations/fresh-install-validation.md` — step-by-step fresh-machine validation procedure; requires both `ds validate` (DB authority plane) and `ds doctor` (Claude Code integration plane)
- `ds validate --help` updated with explicit plane label ("DB authority: schema version, migrations, module profiles") and cross-reference to `ds doctor`
- `ds doctor --help` updated with explicit plane label ("Claude Code integration: hooks, skills, agents, routing") and cross-reference to `ds validate`
- README "Health checks" section added documenting both planes and when to run each

### Changed (style)
- `black` formatting applied to pre-existing unformatted files (mechanical; no semantic changes)

### Fixed (18.1.13.0 — test isolation, pulled forward from 18.1.16.3)
- Systemic test isolation: `DREAM_STUDIO_HOME`, `DREAM_STUDIO_DB_PATH`, and `DS_SPOOL_ROOT` are now set at `conftest.py` **module import time** (before pytest collects or imports any test module). Root cause: `DatabaseRuntime` initializes a singleton on first use and caches the real DB path if any test module's import chain reaches it before a fixture can monkeypatch the env var. The top-of-conftest block ensures the singleton always sees the tmp path on developer machines.
- `guard_real_homedir` mtime check now skips when `DREAM_STUDIO_DB_PATH` is redirected (the spool ingestor writes legitimate operator events to the real DB on developer machines, making mtime comparison a false positive). Guard now calls `pytest.exit(returncode=2)` on contamination instead of `assert`.
- `tests/unit/cli/test_exit_codes.py`: `bootstrapped_db` fixture runs `ds rehearsal-install` + `ds project register` before tests that need a populated DB; `test_project_state_exits_zero` and `test_work_order_list_exits_zero` now pass
- `tests/unit/cli/test_help.py` added: 4 tests enforcing that `ds validate` help references `ds doctor` and vice versa, with plane keywords present in each

### Policy decisions
- `ds validate` and `ds doctor` check genuinely different health planes and neither substitutes for the other. `ds validate` = DB authority (schema version, migrations, module profiles). `ds doctor` = Claude Code integration (hooks, skills, agents, routing). Both commands are required before declaring a fresh install healthy.
- Test isolation is now an enforced contract at `conftest.py` import time, not a best-effort fixture. Pull-forward from 18.1.16.3 was validated safe: Category (i) damage assessment confirmed no operator data was corrupted.

### Coverage baseline (post-18.1.13)
- Scope: `tests/unit/ tests/integration/migrations/ tests/unit/cli/`
- **2993 passed** / 109 pre-existing failures / 1 error / 10 xfailed / 1 skipped
- Delta from pre-18.1.13 baseline (2935+ passed, 110 failures, 50 errors): +58 passing, −1 failure, −49 errors
- Pre-existing failures categorized by phase home in `.planning/pre-existing-failures-categorized.md`

## Phase 18.1.12 — Audit follow-ups: fail-open gap, coverage scope, Sentry removal, env var audit (2026-05-23)

### Fixed
- Hook dispatcher fail-open guarantee restored: `dispatch_tracking.run_handlers()` and `runtime/dispatch/hooks.main()` now catch `BaseException` instead of `Exception`, so `SystemExit` and `KeyboardInterrupt` from handlers can no longer escape and block AI sessions
- `on-game-validate.py` no longer calls `sys.exit(2)` when validation issues are found; it now prints an advisory to stderr and returns normally (the handler should advise, not block)
- `on-pulse.py` no longer re-raises exceptions from `run_pulse_check()`; errors are recorded and the hook exits cleanly
- `on-stop-handoff.py` and `on-meta-review.py` now wrap their bodies in `try/except` for defense in depth
- Coverage scope corrected: `[tool.coverage.run] source` was pointing to `hooks/lib` (does not exist) and `packs/domains/domain_lib` (empty); now points to the actual production directories (`core`, `runtime`, `interfaces`, `spool`, `projections`, `emitters`, `canonical`, `control`); honest baseline: **9% of 42,683 statements** (was measuring <5% of nothing); `fail_under` set to 5 to reflect reality and give slack for CI variance

### Changed (Removed)
- Removed `sentry-sdk` from `requirements.txt`; Dream Studio does not phone home; `core/telemetry/telemetry.py` is now a documented no-op; `init_sentry()` and `capture_exception()` are API-preserving stubs

### Added
- `tests/unit/runtime/test_dispatcher_systemexit.py` — 7 tests verifying dispatcher fail-open for `SystemExit`, `KeyboardInterrupt`, `Exception`, and documenting the `os._exit()` known limitation
- `docs/operations/environment-variables.md` — complete env var inventory: all production variables, defaults, network/privacy implications; `SENTRY_DSN` listed under "Removed"
- Architecture doc `dream-studio-ai-orchestration-architecture.md` updated with honest "Current State" section: 2 of 22 hook handlers currently route through canonical events; dispatcher fail-open gap documented and closed

### Policy decisions
- Dispatcher fail-open is now a tested contract, not just a documented claim (18.1.12 real-world example of architectural-claim-vs-reality drift)
- Dream Studio does not send telemetry to external services; local crash dashboard planned in 18.8.10.1

### Fixed (additions from 2026-05-24 execution-verified audit)
- `WorkOrderProjection` status state machine regression introduced in Phase 18.2.2 and undetected until 2026-05-24 execution-verified audit: `business_work_orders.status` now correctly reflects work order lifecycle events instead of returning `'created'` for all statuses. Root cause: 18.2.2 removed the direct DB writes from CLI mutators (`start_work_order`, `close_work_order`, `block_work_order`, `unblock_work_order`, `create_work_order`) without adding synchronous projection execution; the projection only runs via the background daemon. Fix: restored dual-write pattern — CLI mutators write directly to `business_work_orders` for immediate consistency AND emit canonical events for the projection audit trail. Three eval tests that caught the regression: `test_eval_close_wo`, `test_eval_build_contract`, `test_eval_plan_contract`.
- Test contract for `create_work_order()` corrected: test was asserting `status == 'open'` (pre-rename status from `ds_work_orders`); `business_work_orders` uses `'created'` per migration 070 status mapping.

### Removed (additions from 2026-05-24 execution-verified audit)
- `control/research/methods.py` and downstream callers removed. Module returned hardcoded stub data (`placeholder://research-pending` sources, `confidence: 0.0`), never implemented per the Wave 3 plan. Operator decision: remove cleanly rather than ship fake data. `control/research/engine._execute_research()` now returns an explicit `status: "unavailable"` response. Research integration can be added in a future phase if needed.

## Phase 18.1.11 — Substrate policy lock: read-after-write + schema evolution (2026-05-23)

### Fixed
- `close_milestone` open-WO check now uses a canonical-events fallback: when `business_work_orders` shows a WO as `in_progress` due to projection lag, `business_canonical_events` is checked for a `work_order.closed` event; if found, the WO is treated as closed (fixes H4-2 — the standard `close_work_order → close_milestone` operator workflow was failing with "Cannot close milestone: open work orders remain")

### Added
- `ProjectionRegistry.projected_tables()` returns the set of all target tables across registered projections; single source of truth for projection-backed table enumeration (R3)
- `RegistryEntry.payload_required_keys: frozenset[str]` field on every registry entry; populated for the 5 SDLC WO event types consumed by `WorkOrderProjection`
- Runtime payload validation in `spool.writer.write_event()`: raises `ValueError` on emit if a required key is absent (R10 Layer 1)
- Integration test: `tests/integration/substrate/test_read_after_write_under_projection_lag.py` — 3 tests covering stale projection, canonical-events fallback, and mixed genuinely-open + stale cases (R2)
- Unit test: `tests/unit/config/test_event_schema_evolution_policy.py` — 17 tests covering registry integrity, versioned naming convention, fixture-payload coverage, `write_event` raises on missing key, and `write_event` succeeds with complete payload (R10 Layer 2)
- Architecture docs: `docs/architecture/substrate-policy.md` (parent), `docs/architecture/read-after-write-convergence.md`, `docs/architecture/event-schema-evolution.md`

### Policy decisions
- H4: Pattern C — optimistic return + named exclusion (within-function) + canonical-events fallback (cross-function); `work_order.closed` is terminal, presence of a canonical event is sufficient regardless of projection cursor
- H6: Additive-only schema evolution; breaking changes require a new `event_type` using `<base>.v<N>` naming convention; type-change detection is a documented known gap deferred to a future phase

## Phase 18.1.10 — Repo hygiene cleanup (2026-05-23)

### Changed
- Internal working documents scrubbed from git history (planning roadmaps, writer inventories, phase audit findings, PR body scaffolding, and operational tracking docs)
- `.gitignore` updated: added `venv/`, `env/`, `*.egg-info/`, `.env`, `.env.local`, `*.tmp`, `.pymon`, `docs/audits/`, `docs/publication/`, `backlog.md`, and patterns for `tools/_ta*.md`/`tools/_ta*.py` phase investigation files
- Documentation taxonomy established: end-user and architecture canonical docs in `docs/`; internal planning in `.planning/` (gitignored); historical audits in `.audit/` (gitignored)
- `tools/` cleaned: removed 9 phase investigation documents; retained `canonical_join.py`, `correlation_validate.py`, `raw_drilldown.py` as active development utilities

## Phase 18.1.9 — Test infrastructure cleanup (2026-05-23)

### Fixed
- 8 pre-existing test failures fixed (F1-F8): architectural violations (emitter import, TA6 fixture sync gap), infrastructure gaps (FK pragma, retry telemetry), stale references (dead dual-write test, `_BARE_TO_PACK` pack names), and test isolation issues (gotcha scanner monkeypatch target)
- `studio_db._connect` now restores `PRAGMA foreign_keys = ON` after `_run_migrations` (migration 062 left FK enforcement silently OFF on fresh DBs)
- Migration 071: removes stale `FOREIGN KEY (activity_id) REFERENCES activity_log` from `raw_workflow_runs` and `raw_workflow_nodes` (activity_log was dropped in migration 063)
- `emitters/claude_code/project.py` no longer imports from `core.config.database` (architectural boundary violation); DB path resolved from env vars inline
- `core/telemetry/execution_spine.py` dual-write restored: direct `INSERT OR IGNORE INTO execution_events` before spool write (12+ FK-referencing tables were failing on fresh DBs)
- `requirements.txt` comment corrected: removed self-contradictory "Python 3.14" claim; stubs in `guardrails/scanners/` are now correctly documented as the active implementation; Phase 18.4.3 is the integration scope

### Changed
- `_BARE_TO_PACK` in `control/execution/workflow/runner.py` updated to use `ds-*` prefixed pack names per packs.yaml as of Slice 9; fallback changed from `"core"` to `"ds-core"`
- `tests/integration/spool/test_ta6_e2e_attribution.py` fixture uses direct SQL for work order and task setup (projection-only architecture)
- `tests/integration/test_registry.py` gotcha scanner test patched at correct monkeypatch target (`core.learning.gotcha_scanner._try_db_search`)
- `tests/core/test_dual_write.py` deleted (referenced removed `_insert_activity_log` function)
- Contract docs drift gate satisfied for `sqlite_schema_authority` and `workflow_and_hooks` domains

## Phase 18.2.2 — Work-order writer migration (2026-05-23)

### Fixed
- `unblock_work_order` now emits `work_order.unblocked` event (registry entry existed, projection handled it, emit call was missing)

### Changed
- `business_work_orders` is now populated exclusively by `WorkOrderProjection` — zero direct writes remain
- Removed direct INSERT from `create_work_order` (W07); event emission retained
- Removed direct UPDATE from `start_work_order` (W08); event emission retained
- Removed direct UPDATE from `close_work_order` (W09); event emission retained; milestone-completion and next-WO queries updated to exclude the closing WO by ID so they remain correct without the synchronous write
- Removed direct UPDATE from `block_work_order` (W10); event emission retained
- Removed direct UPDATE from `unblock_work_order` (W11); event emission retained (newly added in this PR)
- Tests updated to reflect projection-only architecture: synchronous `business_work_orders` DB assertions removed; event-emission assertions retained

## Phase 18.1.7 — ds_* → business_* renames (2026-05-23)

### Renamed
- `ds_projects` → `business_projects` (2 rows preserved)
- `ds_milestones` → `business_milestones` (5 rows preserved; +schema enrichment fields: stage_gate_json, validation_expectations_json, security_readiness_checks_json)
- `ds_work_orders` → `business_work_orders` (14 rows merged; status mapping: open→created, complete→closed)
- `ds_tasks` → `business_tasks` (9 rows preserved)
- `ds_design_briefs` → `business_design_briefs` (1 row preserved)
- `ds_work_order_types` → `business_work_order_types` (10 rows preserved)

### Notes
- `ds_documents` and `ds_technology_signals` NOT renamed (out of scope: not business domain entities)
- `business_milestones` enrichment fields (stage_gate_json etc.) are NULL until Phase 18.4 populates them
- Phase 18.1 is now 100% complete. Phase 18.2 (writer migration) and 18.3 (file-state migration) are now unblocked.

## Phase 18.1.5 — Projection Framework (2026-05-23)

### Added
- `core/projections/framework.py` — v2 Projection ABC, ProjectionRegistry, ProjectionEngine (rewritten from pre-v2 to read from dual canonical tables)
- `core/projections/runner.py` — ProjectionRunner daemon process (5s / 100-event trigger, graceful SIGTERM shutdown, PID file lifecycle)
- `core/projections/work_order_projection.py` — First v2 projection: derives `business_work_orders` from `work_order.*` business canonical events
- Migration 068 — `projection_state`, `projection_dead_letter`, `projection_retry_queue` tables
- Migration 069 — `business_work_orders` table (L3 business entity, projection-populated)
- `ds projection list/status/rebuild/dead-letter/daemon` CLI commands
- `config/event_type_registry.py` — added `work_order.unblocked` entry
- 59 tests in `tests/unit/test_phase18_1_5_*` (framework + work order projection)

### Statistics
- Business canonical events processed: 33
- Work orders projected into business_work_orders: 14
- Schema version: 69

### Added — Phase 18.1.6 Project Entity Family Reconciliation (2026-05-22)

- **`docs/architecture/project-family-reconciliation.md`** — complete investigation and decision document for the `ds_*` vs `project_*` table family reconciliation. Enumerates both families in full (schema, row counts, writers, readers), maps all 16 concepts to their v2 placement, records the Approach A decision (ds_* canonical, project_* retires), and provides a migration plan sketch for Phases 18.4 and 18.6.
- **`.planning/data-model-v2.md` Amendment 4** — added "Project Entity Family — Reconciliation Decision" subsection confirming that `business_change_orders` is the target name, `project_*` tables drop in Phase 18.6, and `ds_*` tables rename to `business_*` with schema enrichment. Updated companion documents list to reflect the reconciliation document now exists.

### Decided — Phase 18.1.6

- **Project entity family: Approach A.** `ds_*` is the canonical operational layer. `project_*` family retires: the 8 tables (all at 0 rows) drop in Phase 18.6 after Phase 18.4 builds projection-populated `business_*` equivalents. No true concept duplicates exist — the families serve complementary purposes (operational tracking vs PRD authority specification). The prd_authority.py module (1,250+ lines, never invoked in production) is a design asset to be harvested by Phase 18.4, not lost.

### Added — Phase 18.1.3 Correlation ID Infrastructure (2026-05-22)

- **`core/correlation/composer.py`** — canonical implementation of correlation ID composition rules. Functions: `compose(parts)` builds `sess-X:wf-Y:skill-Z:agent-A:hook-H:tool-T` from a dict; `decompose(cid)` parses back to components; `extend(base, entity_type, entity_id)` adds a context level; `validate(cid)` checks format; `normalize_legacy(cid)` normalizes pre-18.1.3 IDs. Uses lookahead regex splitting so skill IDs containing colons (e.g. `ds-security:scan`) are preserved as single segments.
- **`core/correlation/__init__.py`** — public re-export of all five composer functions.
- **Ingestor delegation** (`spool/ingestor.py`) — `_extract_correlation_ids()` now delegates string composition to `core.correlation.composer.compose()` instead of building it inline. Extraction logic (reading trace/payload/top-level fields) stays in the ingestor; composition is canonical.
- **Backfill script** (`scripts/backfill_correlation_ids.py`) — best-effort correlation ID backfill for all three event tables. Per-row: if valid → kept; if malformed → normalized; if missing → reconstructed from ID columns + trace JSON; if unfixable → marked. Safe to re-run. Live result: 2770 events checked, 756 valid (kept), 0 malformed, 2014 missing (historical events without reconstructible context).
- **Validation utility** (`tools/correlation_validate.py`) — walks recent events, validates composition rules, reports malformed/missing per table. Exit 0 if all valid, exit 1 if any malformed, exit 2 on DB error. Flags: `--limit`, `--since`, `--db-path`, `--json`. Live result: 0 malformed across all three tables.
- **54 unit tests** (`tests/unit/test_phase18_1_3_correlation.py`) — covers compose/decompose/extend/validate/normalize_legacy, ingestor integration, backfill dry-run/live, and validation tool.

### Added — Phase 18.1.2 Dual Canonical Structure + Event Type Registry (2026-05-22)

- **`business_canonical_events` table** — new L2a business canonical table (migration 067). 14 columns including denormalized project_id, milestone_id, work_order_id, task_id for index-backed SDLC queries. 12 explicit indexes (correlation_id, event_type, project_id, milestone_id, work_order_id, task_id, event_timestamp, received_at, compound pairs). Does not replace `canonical_events` — both coexist during Phase 18.1.x transition.
- **`ai_canonical_events` table** — new L2b AI canonical table (migration 067). 16 columns including denormalized session_id, skill_id, workflow_id, agent_id, hook_id, model_id for index-backed AI analytics queries. 13 explicit indexes including compound (session × type, skill × time).
- **Event type registry** (`config/event_type_registry.py`) — 85-entry routing registry mapping every known event_type to its canonical destination(s). `RegistryEntry` dataclass with `routes_to` tuple, `granularity_level`, and `description`. Public API: `get_routes()`, `is_registered()`, `get_entry()`, `all_entries()`. Unknown types default to both canonicals (safe over-record). Raw-only types (tool.execution.completed, tool.execution.started, hook.tool_activity) carry `granularity_level="mechanical-detail"` per Commitment 9.
- **Ingestor dual canonical write** — `spool/ingestor.py` `_write_to_dual_canonical()` consults the event type registry on every ingest and routes to business, AI, both, or neither. Implemented as best-effort: dual canonical failure logs a warning but does not block the legacy `canonical_events` write. Raw write failure still blocks (inbox restore).
- **Backfill script** (`scripts/backfill_dual_canonical.py`) — one-time best-effort reconstruction of 1,938 existing `canonical_events` rows into the dual canonical tables. Results: 56 → business_canonical_events, 743 → ai_canonical_events, 1,139 skipped as raw-only per Commitment 9. Source column set to `"backfill"`. Safe to re-run via INSERT OR IGNORE.
- **Correlation join CLI** (`tools/canonical_join.py`) — verification utility for the dual canonical join. Supports `--stats`, `--list` (top correlation_ids by event count), `--correlation-id ID` (join both tables), `--json`, `--limit`, `--db-path`. Verified: 100 distinct correlation_ids present in ai_canonical_events after backfill.

### Added — Phase 18.1.1 Raw Layer Infrastructure (2026-05-22)

- **`raw_claude_code_events` table** — new L1 raw layer table (migration 066) that preserves the full native event shape for every Claude Code event. 14 indexes cover individual correlation ID components (session_id, project_id, workflow_id, skill_id, agent_id, hook_id, tool_id), the composed `correlation_id`, event_type, received_at, event_timestamp, and compound pairs (project × time, type × time, session × type). Part of the v2 data architecture; future adapters get their own tables.
- **Ingestor dual-write** — `spool/ingestor.py` now writes to `raw_claude_code_events` FIRST before writing to `canonical_events`. Raw write failure returns the spool file to the inbox for retry on the next ingest run; canonical write is only attempted after a successful raw write.
- **`_extract_correlation_ids()`** — new ingestor function that extracts session_id, project_id, workflow_id, skill_id, agent_id, hook_id, tool_id, model_id, adapter_id from top-level fields, trace, and payload; composes a `correlation_id` string in the form `sess-X:wf-Y:skill-Z:agent-A:hook-H:tool-T` (only non-null parts included).
- **Backfill script** (`scripts/backfill_raw_claude_code_events.py`) — one-time best-effort reconstruction of 1,909 existing `canonical_events` rows into `raw_claude_code_events` via `INSERT OR IGNORE`. Backfilled rows carry `_backfill=True` in source_payload. Safe to re-run.
- **Drill-down CLI** (`tools/raw_drilldown.py`) — interactive query tool for `raw_claude_code_events` supporting `--stats`, `--correlation-id`, `--session-id`, `--workflow-id`, `--skill-id`, `--hook-id`, `--tool-id`, `--project-id`, `--event-type`, `--limit`, `--json`, and `--db-path` flags.

### Fixed — Phase 18.0 Emergency Cleanup (2026-05-22)
- **C1 — spool/emitter.py created**: `on-context-threshold.py` imported `from spool.emitter import emit` but the module did not exist, silently failing every context threshold event. `spool/emitter.emit()` now wraps `CanonicalEventEnvelope` + `write_envelopes` with a non-raising interface (returns `True`/`False`).
- **C2 — Handoff TTL guards**: `on-prompt-validate.py` can no longer leave `pending-handoff.json` alive indefinitely. Added `HANDOFF_STALE_TTL_S=300` and `HANDOFF_INJECTION_WINDOW_S=60` constants. Files older than 300s are deleted; `in_progress` files past 60s are cleaned up. Discards logged to `DS_DIAGNOSTICS_DIR/stale-handoff.jsonl`.
- **C3 — DB contamination cleanup**: migration 065 deletes 23 test fixture rows from `ds_projects` that were written to production `studio.db` by tests bypassing isolation. `guard_real_homedir` now calls `DatabaseRuntime.reset_instance()` before/after yield. Three tests in `test_ta3_token_capture.py` fixed to pass `dream_studio_home=db_home`.
- **C4 — Guardrails evaluator dependency**: `guardrails/evaluator.py` referenced removed `activity_log` table (dropped in migration 063). `_custom_query_matches()` now checks `canonical_events` / `hook_invocations`, rejects `activity_log` references with a descriptive error.

### Added
- **Publication boundary** - added public/private publication guidance, docs index, and current product positioning for Dream Studio as a local-first AI orchestration and operational intelligence platform.
- **Pattern Enhancement (35 tasks)** — 9 foundational patterns for optimized LLM consumption with 40% token savings target (#pattern-enhancement)
  - Progressive disclosure: `quality/debug` refactored 217→65 lines with 6 reference files for on-demand loading
  - Design system library: 5 curated systems (3,561 lines) - tech-minimal, editorial-modern, brutalist-bold, playful-rounded, executive-clean
  - I-Lang discovery protocol: 8-dimension design intent capture with NLP mappings
  - Version guards: Python/Node/Power BI feature gating for 70% compatibility bug reduction
  - Decision tables: symptom→solution routing in debug (8 patterns), client-work (6 patterns), design (5 systems)
  - Response contracts: standardized output sections for security reviews, client deliverables, ship gate
  - Structured frontmatter: ds: namespace added to all 41 mode SKILL.md files
  - CI validation: SKILL.md standards enforcement (line count, YAML, banned phrases, reference links)
  - DO/DON'T lesson template: 75% scan-time reduction (2min→30sec) with visual markers
- **YAML mode config** — migrated skill metadata from SKILL.md frontmatter to dedicated `config.yml` files across all 48 skill directories; SKILL.md is now pure instructions (#83)
- **Granular skill tracking** — dashboard shows mode-level names ("core:think", "quality:debug") instead of pack-only names ("core", "quality") (#84)
- **Smart model routing** — `get_model_for_skill()` API reads `model_tier` from config.yml for subagent model selection (opus/sonnet/haiku) with telemetry tracking (#80)
- **Hook consolidation** — 3 dispatchers replace 19 subprocess calls (UserPromptSubmit 6→1, Stop 9→1, Edit|Write 4→1) with per-handler timing telemetry (#81)
- **Context trimming** — extract detailed content from 14 SKILL.md files into examples.md (44% line reduction), hook timing dashboard panel, global CLAUDE.md deduplication (#82)
- **Analytics in CI** — dashboard renders on main branch pushes and uploads as a build artifact (#85)
- **Onboarding skill** (`ds:setup`) — wizard, status, and JIT modes for guided tool installation and project setup (#46)
- **Web access module** (`skills/core/web.md`) — 3-tier fallback chain (Firecrawl → scraper-mcp → WebSearch/WebFetch) with JIT install prompts
- **Tool registry** (`skills/setup/tool-registry.yml`) — metadata for 6 optional tools with detect/install/upgrade commands

### Fixed
- **Chain suggestions restored** — `on-skill-complete.py` now reads `chain_suggests` from config.yml instead of stripped SKILL.md frontmatter (#85)
- **Installer statusLine schema** — Claude Code installer now writes `statusLine.type: "command"` alongside `statusLine.command`, satisfying the Claude Code settings schema and clearing the `/doctor` validation error on fresh installs.

### Changed
- **License** - updated current public licensing to Apache-2.0.
- **README and product docs** - replaced adapter-first language with platform-first language; Claude Code is documented as one adapter surface.
- **Visual architecture documentation** — created simplified root `ARCHITECTURE.md` with Mermaid diagrams (system overview, database ERD, session lifecycle) as visual front-door for GitHub browsers; updated `/refresh-architecture` command to maintain consistency between root and detailed docs
- **Documentation** — updated 10 files with stale "SKILL.md frontmatter" references to reflect config.yml as the metadata SSOT (#85)
- **Workflow coverage** — token efficiency improvements and feature activation gates (#48)
- **Linux gh install** — corrected install command; Mac Python symlink fix (#47)

## [0.11.0] — 2026-04-30

### Changed
- **Pack consolidation** — 37 individual skills consolidated into 7 pack-level router skills (core, quality, career, security, analyze, domains, workflow). Each pack uses a `modes/` subdirectory for sub-skill content. Total skill description budget drops from ~10,000 to ~885 chars, ensuring all skills load for every user out of the box.
- **packs.yaml** — bumped to schema_version 2; `skills` field replaced with `skill` (singular) + `modes` list per pack
- **CLAUDE.md routing table** — 35-row individual skill routing replaced with 7-row pack-based routing
- **sync-cache.ps1** — dynamic version detection, stale directory cleanup on sync
- **README.md** — updated skill documentation to reflect pack-based invocation pattern
- **plugin.json** — version 0.11.0

### Removed
- 37 top-level skill directories (moved into pack `modes/` subdirectories — content unchanged)

### Migration
- Invocations change from `ds:think` to `ds:core` with arg `think`
- Natural language routing still works — pack routers infer mode from keywords
- `workflow` remains standalone (unchanged)

## [0.10.0] — 2026-04-29

### Added
- **agents/** directory with integration README — entry point for bundled specialist agents
- **agents/data-engineer.md**, **mobile-developer.md**, **research-analyst.md**, **idea-validator.md**, **accessibility-expert.md**, **technical-writer.md**, **terraform-architect.md**, **kubernetes-expert.md**, **devops-engineer.md** — 9 bundled specialist agents synthesized from external repo patterns (infra, mobile, data, research, quality domains)
- **skills/domains/infra/**, **mobile/**, **data/**, **research/**, **quality/** — 8 domain knowledge YAMLs (patterns, gotchas, synthesis eval rubric); all ASCII-clean, yaml.safe_load validated
- **skills/domains/eval-rubric.yml** — 8 quality signals for domain synthesis assessment
- **workflows/domain-ingest.yaml** — 4-phase domain synthesis pipeline: discover → extract → synthesize → register
- **workflows/domain-refresh.yaml** — automated stale agent re-synthesis workflow
- **`type: specialist`** node in workflow execution protocol (SKILL.md)
- **On-pulse stale agent detection** — `hooks/on_pulse.py` now reports agents past their `refresh_due` date
- **README Bundled Specialists section** — documents the 9 agents, domains covered, and install instructions

### Changed
- **skills/domains/ingest-log.yml** — schema extended with `agent_type` field; 9 domain agents backfilled as entries
- **skills/coach/analysts/route-classifier.yml** — expanded with ingest-log agent install suggestion for unrecognized skill requests

## [0.9.0] — 2026-04-29

### Added
- **ARCHITECTURE.md** — Documents the two-layer design: `packs/` (Python hook runtime) vs `skills/` (Claude guidance), key paths, how they connect, and the full new-skill checklist
- **skills/domains/ingest-log.yml** — External knowledge registry tracking every repo analyzed: URL, stars, domain, files touched, analysis date, refresh-due date. Backfilled with 11 repos from the 2026-04-28 integration
- **`workflow: repo-ingest`** node in `skills/workflow/SKILL.md` — Formalizes external repo intake: domain detection, dedup check, ≤10 pattern extraction, domain YAML write, ingest-log entry. Replaces ad-hoc ingestion with a tracked, repeatable workflow
- **`.planning/specs/infra-lessons-ingest/`** — Plan and tasks for this release

### Fixed
- **`~/.dream-studio/config.json`** — Now includes `director_name` and `claude_memory_path`; silences the "Setup not complete" warning that fired every session
- **`skills/learn/config.yml`** — `harvest.projects_root` now set to `builds/`; enables `learn: harvest` to auto-discover projects

### Changed
- **skills/build/gotchas.yml** — Added `compact-at-75-percent` best practice: run `/compact` proactively between waves before context approaches 75% (promoted from 26 pending draft lessons)
- **skills/STRUCTURE.md** — Added Skill Depth Policy section: JIT enrichment only, no sprint; skill tier table (Enhanced / Standard / JIT-pending)
- **skills/polish/SKILL.md** — Now references `checklists/` directory with all 4 checklists named inline
- **skills/mcp-build/SKILL.md**, **dashboard-dev/SKILL.md**, **saas-build/SKILL.md** — Added `## Depth Status` section marking each as JIT-pending
- **skills/workflow/SKILL.md** — `repo-ingest` built-in workflow node added (see Added above)

### Meta
- 26 pending draft lessons triaged: 22 rejected (context-threshold noise + sonnet-theme), 4 high-context theme promoted to `build/gotchas.yml`
- Draft lesson queue cleared to 0

## [0.8.0] — 2026-04-29

### Added — Skill & Workflow Improvements (TR-001–TR-013)
- **skills/explain/** — New `explain` skill: traces entry point through layers to output, depth adapts to question; includes SKILL.md, metadata, gotchas, config, changelog
- **skills/coach/analysts/route-classifier.yml** — Route-classifier analyst persona for mapping unmatched intents to nearest skill
- **skills/coach/modes.yml** — `route-classify` mode entry for coach
- **skills/core/repo-map.md** — New core module: repo-map generation patterns, registered in REGISTRY.md
- **skills/domains/bi/dax-patterns.md** — DAX calculation patterns for Power BI domain knowledge base
- **skills/domains/bi/m-query-patterns.md** — M-query data transformation recipes for Power BI
- **skills/client-work/powerbi/pbip-format.md** — PBIP format reference for Power BI project files
- **hooks/lib/skill_metrics.py** — Appends skill usage records (name, duration, tokens) to `~/.dream-studio/skill-metrics.jsonl` on every invocation
- **scripts/sync-cache.ps1** — PowerShell cache sync utility

### Changed
- **CLAUDE.md** — Added routing fallback clause: unmatched intents route to `coach` with `route-classify` mode (TR-012)
- **skills/coach/SKILL.md** — Added `route-classify` mode (TR-012)
- **skills/build/SKILL.md** — Repo-map generation step at Step 0 (TR-006), per-task checkpoints at every step (TR-007), worktree isolation instruction for parallel dispatch (TR-008), auto-learn suggestion at checkpoint (TR-013)
- **skills/debug/SKILL.md** — Step 1.5 failing-test capture gate (TR-011), auto-learn suggestion (TR-013)
- **skills/verify/SKILL.md** — Red-green bug fix verification section (TR-011)
- **skills/review/SKILL.md** — JSON reviewer schema for structured findings output (TR-003)
- **skills/core/orchestration.md** — JSON agent schema, static-before-dynamic prompt ordering (TR-003/TR-004), repo-map field in implementer template (TR-006), pipeline gate check pattern (TR-009)
- **skills/core/format.md** — Task-level checkpoint format variant (TR-007)
- **skills/build/config.yml** — Checkpoint threshold set to 1 task (TR-007)
- **workflows/fix-issue.yaml** — `create-issue` node after diagnose (TR-001), write-failing-test conditional node (TR-005)
- **workflows/idea-to-pr.yaml** — Conditional security branch (TR-005)
- **settings.json** — PostToolUse metrics hook for Skill tool (TR-010)
- 30+ SKILL.md files updated with content improvements across all packs
- Updated gotchas.yml for build, debug, plan, review, secure, think, verify
- Regenerated `skills/dream-studio-catalog.md` — now covers 38 skills

## [0.7.0] — 2026-04-28

### Added — Skill Architecture Enhancement (Phase 2)
- **skills/*/metadata.yml** — Evolution tracking, quality metrics (success_rate, times_used, avg_token_usage), dependency tracking for all 37 skills
- **skills/*/gotchas.yml** — Structured lessons learned (avoid, best_practices, edge_cases, limitations, deprecated) for all 37 skills
- **skills/*/config.yml** — Runtime configuration and performance budgets for all 37 skills
- **skills/*/changelog.md** — Version history for all 37 skills
- **skills/generate-catalog.py** — Auto-generates dream-studio-catalog.md from skill metadata
- **skills/dream-studio-catalog.md** — Auto-generated searchable skill dashboard with quality metrics, dependency graph, health status
- **skills/STRUCTURE.md** — Complete architecture guide (skill structure, file purposes, creating/updating skills, best practices)
- **skills/templates/** — Templates for metadata.yml, gotchas.yml, config.yml for new skill creation
- **skills/build/examples/** — Simple + complex usage examples with input/output (also for plan, review, verify, ship)
- **skills/build/templates/** — Agent prompts (implementer, reviewer) and output formats (checkpoint, findings-report, plan-format)
- **skills/build/smoke-test.md** — Quick validation tests (also for plan, review, verify, ship)
- **skills/build/core-imports.md** — Module dependency documentation and impact analysis (also for plan, review, verify, ship)

### Changed
- **skills/core/REGISTRY.md** — Updated with Phase 2 architecture enhancement history
- **README.md** — Added Skill Architecture section documenting structured framework
- All 37 skills now follow standardized structure with metadata, gotchas, config, and changelog

### Infrastructure
- **Makefile** — standard targets: `test`, `lint`, `fmt`, `security`, `install-dev`, `status`
- **pyproject.toml** — black, flake8, pytest, and coverage config (replaces need for separate `.coveragerc`)
- **hooks/lib/time_utils.py** — `utcnow()` utility; replaced all bare `datetime.now(timezone.utc)` calls in handlers and `context_handoff.py`
- **hooks/lib/models.py** — Pydantic v2 models (`UserPromptSubmitPayload`, `PostToolUsePayload`, `StopPayload`) for stdin validation in handlers
- **hooks/lib/audit.py** — append-only event log writing to `~/.dream-studio/audit.jsonl`
- **hooks/lib/telemetry.py** — optional Sentry error tracking stub (activated by `SENTRY_DSN` env var)
- **SECURITY.md** — vulnerability disclosure process (30-day SLA, dannis.seay@twinrootsllc.com)
- **CONTRIBUTING.md** — branch naming, commit format, PR checklist, code style guide
- **requirements.txt** — runtime dependencies (pydantic, sentry-sdk) split from dev deps
- **requirements-dev.txt** — added freezegun, factory-boy, black, flake8, pip-audit, pre-commit
- **.pre-commit-config.yaml** — black and flake8 hooks
- **scripts/bom.py** — Bill of Materials script (git SHA, Python version, pip freeze, build date)
- **skills/harden/SKILL.md** — `/harden` skill: 20-item audit + gap-fill from templates
- **templates/project-standards/** — reusable template files (Makefile, pyproject.toml, SECURITY.md, CONTRIBUTING.md, requirements files, hooks/lib stubs)
- **tests/factories.py** — factory_boy factories for hook payload models
- **on-tool-activity** hook: one-time `/harden audit` nudge on first Edit/Write in unhardened projects

### Changed
- `on-token-log.py`, `on-milestone-start.py`, `on-milestone-end.py`, `on-pulse.py`, `on-meta-review.py`, `context_handoff.py` — all `datetime.now(timezone.utc)` replaced with `utcnow()` from `time_utils`
- `on-token-log.py`, `on-context-threshold.py` — added Pydantic payload validation with graceful fallback on `ValidationError`
- `test_hook_on_pulse.py`, `test_hook_on_milestone_end.py`, `test_hook_on_token_log.py` — added `@freeze_time` to time-sensitive tests

## [0.6.1] — 2026-04-19

### Added
- **skills/domain-re/** — Real estate analysis skill: forensic skeptic (sonnet) + diplomatic executor (haiku) + battle-tested strategist (sonnet); modes: lease-analysis, credit-check, renewal-economics, rollover-analysis; 3 analysts, anti-sycophancy design
- **skills/coach/** — Claude Code workflow coach: evaluates workflow-fit, context-health, pr-hygiene, agent-dispatch; `full-audit` mode runs all four in parallel with consensus-report synthesis
- **skills/secure/** — Rewritten as parallel analyst-orchestrated skill: 6 OWASP analysts (injection, auth, exposure, access-control, misconfig, dependencies) + 6 STRIDE analysts; `any-reject` verdict (any HIGH = BLOCKED); incomplete review defaults to BLOCKED; ship gate integration
- **~/.claude/agents/**: typescript-expert, python-expert, go-expert, devops-engineer, ml-engineer, bi-developer — six language and domain expert agents (global scope)
- **~/.claude/CLAUDE.md** — Claude Code patterns section: context rewind threshold (~300-400k tokens), PR size target (~120 lines), subagent dispatch at >50% context

## [0.6.0] — 2026-04-17

### Changed
- **verify** skill: added Iron Law gate, Common Failures table, Red Flags list, Rationalization Prevention table, evidence patterns (borrowed from Superpowers verification-before-completion)
- **review** skill: two-stage review ordering — spec compliance first, then code quality; subagent reviewer dispatch templates; "Do Not Trust the Report" principle (borrowed from Superpowers subagent-driven-development)
- **build** skill: subagent-driven execution with fresh agent per task, pre-inlined context injection, dependency-wave parallel execution, model selection heuristic, implementer prompt template, phase-locked transitions (borrowed from Superpowers + GSD)
- **handoff** skill: dual-output (markdown + JSON), recovery state machine for programmatic resume, context pressure triggers (borrowed from GSD pause/resume pattern)
- **on-context-threshold** hook: doubled all thresholds (WARN 1500→3000, COMPACT 2500→5000, HANDOFF 3500→7000, URGENT 4500→9000)

## [0.5.0] — 2026-04-16

### Added
- `agents/chief-of-staff.md`, `agents/engineering.md`, `agents/game.md`, `agents/client.md` — four agent personas flattened from `<name>/CLAUDE.md` layout; Dannis/SeayInsights references replaced with `{{director_name}}` placeholder resolved at skill-load time
- `agents/director.md` — fill-in-blanks Director persona template (name, role, focus, hard limits, tool preferences)
- `agents/context/director-preferences.md`, `director-corrections.md`, `session-context.md`, `session-primer.md`, `fullstack-standards.md` — ported from studio, generalized (notion-studio-mcp calls and brand-specific tokens removed; `{{director_name}}` placeholder)
- `on-context-threshold.py` slug builder now replaces spaces with `-` on both drive-letter and fallback branches (mirrors studio fix from commit `25208c9`); new unit test covers Windows-path-with-spaces, Unix-path-with-spaces, and no-spaces cases
- Integration test `test_projects_dir_slug_replaces_spaces` (52 tests total)

### Removed
- `agents/torii/` — TORII is a separate product, not shipped with dream-studio
- All `notion-studio-mcp` auto-logging calls from agent personas (log_agent_action, log_escalation, get_pending_escalations, etc.)
- References to `studio-ops`, `dannis-naomi`, specific project repos
- "SeayInsights brand tokens" section in `fullstack-standards.md` — now a fill-in-blanks block

## [0.4.0] — 2026-04-16

### Added
- 10 hook handlers ported to `hooks/handlers/`, all built on `hooks/lib`:
  - `on-pulse` — cross-project health check; `github_repo` comes from `config.json`, not hardcoded
  - `on-milestone-start` / `on-milestone-end` — DCL-matched milestone marker in `~/.dream-studio/state/`
  - `on-context-threshold` — four-band warn/compact/handoff/block with project-dir auto-detection (override via `CLAUDE_PROJECTS_DIR`)
  - `on-quality-score` — advisory diff scan (tests, debug, secrets, size, scope); writes `quality-score.json`
  - `on-token-log` — appends token usage rows to `token-log.md`
  - `on-meta-review` — weekly retrospective reading `~/.dream-studio/planning/session-context.md`
  - `on-agent-correction` — pattern accumulation with auto-draft threshold (override via `DREAM_STUDIO_CORRECTIONS_PATH`)
  - `on-skill-load` — logs skill reads; surfaces `{{director_name}}` resolution from `config.json`
  - `on-tool-activity` — rolling activity snapshot under `state/activity.json`
- `hooks/hooks.json` — declares hooks on `UserPromptSubmit`, `Stop`, and `PostToolUse` (via `${CLAUDE_PLUGIN_ROOT}/hooks/run.sh`)
- 28 integration tests (one file per hook) — `pytest tests/` now runs 51 tests total

### Removed
- `_notion.py` and `_torii_feed.py` helpers — dream-studio core no longer talks to Notion or the TORII feed

## [0.3.0] — 2026-04-16

### Added
- `hooks/lib/paths.py` — `plugin_root`, `user_data_dir` (`~/.dream-studio/`), `project_root`, `meta_dir`, `state_dir`, `planning_dir`
- `hooks/lib/python_shim.py` — `detect_python()` tries `py`, `python3`, `python` in order, raises `PythonNotFoundError` with OS-specific install hints
- `hooks/lib/state.py` — `read_config`/`write_config`, `read_pulse`/`write_pulse`, schema-version guard via `SchemaVersionError`
- `hooks/run.sh` + `hooks/run.cmd` — cross-platform handler launchers that pick a Python interpreter and exec `hooks/handlers/<name>.py`, preserving `CLAUDE_PLUGIN_ROOT`
- `tests/` — 23 unit tests (paths, python_shim, state) with 97% line coverage on `hooks/lib`
- `requirements-dev.txt` pinning pytest + pytest-cov
- `.gitattributes` enforcing LF for `.sh`/Python and CRLF for `.cmd`/`.bat`
- CI matrix now installs deps and runs `pytest --cov=hooks/lib --cov-fail-under=80`

## [0.2.0] — 2026-04-16

### Added
- 18 skills ported from studio as `skills/<name>/SKILL.md` with YAML frontmatter (`name`, `description`):
  - Process: `think`, `plan`, `build`, `review`, `verify`, `debug`
  - Domain: `saas-build`, `game-dev`, `client-work`, `design`, `mcp-build`, `dashboard-dev` (was `torii-dev`)
  - Quality: `polish`, `secure`, `ship`
  - Studio: `recap`, `handoff`, `learn`

### Changed
- Flat skills layout (`skills/<name>/SKILL.md`) instead of category folders, matching Claude Code adapter convention
- `design` skill: brand tokens table converted to fill-in template
- `mcp-build` skill: `@seayinsights/` package scope generalized to `@<your-scope>/`
- `client-work` skill: "Notion Client Projects" generalized to "the project tracker"
- `saas-build` skill: dropped the specific project list line

### Removed
- All SeayInsights-specific references (brand name, Dannis, repo URLs, Notion workspace IDs)
- TORII product branding from the dashboard skill (now `dashboard-dev`, fully generic)

## [0.1.0] — 2026-04-16

### Added
- `.claude-plugin/plugin.json` manifest (name, version, author, license, repository)
- `.claude-plugin/marketplace.json` self-hosted dev marketplace entry
- `README.md`, initial license file, `.gitignore`, `CHANGELOG.md`
- `.github/workflows/ci.yml` scaffold (lint + pytest matrix on Windows/macOS/Linux × py3.10/3.11/3.12, empty tests OK)
- Repo bootstrapped, initial commit on `main`
- Verified `claude plugins list` shows `dream-studio@0.1.0` after local install

## [0.0.1] — 2026-04-16

### Added
- Scaffolding
