# Workflow Runtime Authority

Phase 5.5A — Workflow Runtime Reliability audit and classification.

**2026-06-10 (WO-CONSTITUTION-GATES):** `canonical/workflows/pre-push.yaml` extended with four dependency rule gates
(`rule1`–`rule4`). Implementation: `core/gates/dependency_rules.py`. Tests: `tests/unit/test_release_gates_dependency_rules.py`.

**2026-06-14 (WO-LESSONS-DB-UNIFY):** `canonical/workflows/daily-close.yaml` node `daily-learn` updated: step 5 now uses `INSERT OR IGNORE` via `insert_lesson()` for dedup (was: file dedup against draft-lessons directory); step 6 now says "Record ≤5 new lessons via insert_lesson()" (was: "Write ≤5 new drafts to meta/draft-lessons/"). `canonical/workflows/self-audit.yaml` node `collect-signal` step 3 updated: draft lesson count now comes from `raw_lessons WHERE status='draft'` DB query (was: glob of draft-lessons/*.md). No workflow structural change (node dependencies, trigger_rule, model, timeout unchanged).

**2026-07-04 (WO 9f47a1a0, emission fix):** `control/execution/workflow/state.py`'s terminal-run archival path (`_try_archive_and_prune`) no longer calls `archive_workflow()` — that function wrote to `raw_workflow_runs`/`raw_workflow_nodes`, which had been write-orphaned since 2026-05-18 (every INSERT silently failed inside a shared best-effort try/except, and the exception was swallowed). Both tables were dropped in migration 141 (`core/event_store/migrations/141_drop_orphaned_workflow_raw_tables.sql`). Workflow runs now emit canonical events again: on every terminal state (`completed`, `completed_with_failures`, `aborted`), state.py writes `workflow.completed` (+ one `workflow.node.completed` per node) canonical event envelopes directly to the spool (`emitters/shared/spool_writer.py`), decoupled from any SQLite write — a future schema failure in a legacy table can no longer silently swallow event emission. `archive_workflow()` and its `_emit_workflow_telemetry()` helper are deleted from `core/event_store/studio_db.py`; the `execution_events` dual-write (`emit_workflow_invocation`) moved into state.py's new `_emit_execution_events_telemetry()` helper. Readers repointed off the dropped tables: `projections/core/collectors/workflow_collector.py`, `projections/core/sla/tracker.py` (`workflows_success_rate`), and `studio_db.py::last_run`/`run_count` (used by `control/execution/workflow/registry.py::list_workflows()`) now read `ai_canonical_events` filtered by `event_type IN ('workflow.completed', 'workflow.node.completed')`.

## Workflow Authority Model

### Canonical

| Component | Path | Role |
|-----------|------|------|
| Workflow templates | `workflows/*.yaml` | Declarative DAG definitions |
| Engine (pure logic) | `control/execution/workflow/engine.py` | File locking, template resolution, condition evaluation, ready-node computation |
| State CLI | `control/execution/workflow/state.py` | State read/write, start/update/pause/resume/abort/next |
| Validator | `control/execution/workflow/validate.py` | YAML parsing, cycle detection, field validation |
| Cost estimator | `control/execution/workflow/cost.py` | Token cost estimation |
| Registry | `control/execution/workflow/registry.py` | Workflow metadata enrichment |

### Runtime Integration

| Component | Path | Role |
|-----------|------|------|
| Execution graph | `core/execution/graph.py` | Persistent DAG (project → phase → wave → task) |
| Workflow integration | `core/execution/workflow_integration.py` | Workflow-to-graph bridge |
| Context compiler | `core/execution/context_compiler.py` | Smart context assembly (70-85% token savings) |
| Dream exec CLI | `interfaces/cli/dream_exec.py` | Execution graph visibility |
| Exec graph CLI | `interfaces/cli/exec_graph.py` | Graph CRUD operations |
| GitHub adapter | `core/execution/github_adapter.py` | gh CLI wrapper (subprocess) |
| CI collector | `core/execution/ci_collector.py` | Test/CI signal collector |
| Tracking hook | `control/execution/workflow/tracking.py` | Hook context extraction |

Hook launchers are part of the workflow/runtime boundary because workflow and
skill events can be routed through adapter hook surfaces. On Windows,
`hooks/run.cmd` must resolve its plugin root from the launcher path before
argument shifting. Adapter apps such as Codex may invoke `UserPromptSubmit`
from a workspace outside the Dream Studio repo, so launcher root resolution must
not depend on the current working directory.

## Workflow Inventory (23 templates)

| Workflow | Nodes | Gates | Retry | Timeout | Dashboard Dep | Models |
|----------|-------|-------|-------|---------|---------------|--------|
| idea-to-pr | 13 | director-approval, auto-pass | max:1 | 300-600s | No | opus, sonnet, haiku |
| safe-refactor | 7+ | director-approval, auto-pass | max:1 | 600s | No | sonnet |
| comprehensive-review | 7 | synthesis | No | 180-300s | No | sonnet, haiku |
| game-feature | 7+ | director-approval, qa-gate | max:1 | 600s | No | sonnet |
| prototype | 7+ | director-approval | max:1 | 600s | No | sonnet |
| security-audit | multi | pre-scan, pre-dashboard | No | varies | **Yes** (Power BI) | sonnet |
| domain-ingest | 4 | director-review | No | 300-600s | No | haiku, opus, sonnet |
| domain-refresh | 4 | — | No | 120-900s | No | haiku, sonnet |
| fix-issue | 3+ | director-approval, auto-pass | max:1 | 600s | No | sonnet |
| hotfix | 3 | evidence-required | max:1 | 600s | No | sonnet |
| audit-to-fix | chain | director-approval | max:1 | varies | No | sonnet |
| client-deliverable | multi | director-approval, deliver-gate | max:1 | 120-600s | No | haiku, sonnet |
| optimize | 3+ | director-approval, evidence-required | No | 600s | No | sonnet |
| project-audit | 3+ | review-findings | No | 300-600s | No | sonnet |
| ui-feature | 7+ | director-approval, polish-gate | max:1 | 600s | No | sonnet, haiku |
| daily-standup | 3+ | priorities-confirmed | No | 60-120s | No | haiku, sonnet |
| self-audit | multi | — | No | — | No | — |
| studio-analytics | multi | data-harvest | No | — | **Yes** (localhost:8000) | — |
| daily-close | multi | — | No | — | No | — |
| feature-research | 12 | synthesis, director | No | — | **Yes** (GitHub API) | sonnet |
| studio-onboard | multi | — | No | — | No | — |
| production-readiness | 5 | no implicit execution gate | No | 60-120s | Yes (SQLite/dashboard read models) | adapter-agnostic |
| execute-work-orders | 13 | preflight-check (halt on critical/high), migration-class-check (operator go), run-gates (halt on gate failure), independent-review (halt on REVIEW_FAIL) | max:1 (implement-tasks) | 30-600s | No | haiku, sonnet |

The `production-readiness` workflow is the canonical workflow template for the
secure production readiness gate. It classifies impact, builds the gate, persists
SQLite authority records when authorized, hydrates dashboard/project detail
surfaces, and creates proposed remediation Work Order records. It does not run
Docker, inspect secrets, mutate external projects, or execute remediation.

## Retry Behavior Assessment

**Status: Declared and validated, NOT enforced by runtime.**

- 13/21 workflows declare `retry: {max: 1, backoff_seconds: 15}`
- `validate.py` validates retry fields (max must be positive int)
- `state.py` does NOT implement retry logic — `cmd_update` marks nodes as failed, `cmd_next` does not re-queue failed nodes
- Retry is a **hint for the orchestrating agent** (Claude), not engine-enforced

**Recommendation:** Document this as a declared-but-advisory field. If enforcement is needed, add to `cmd_next` in Phase 6 — check if a failed node has retry.max > retry_count and re-queue it.

## Timeout Behavior Assessment

**Status: Declared and validated, NOT enforced by runtime.**

- Most workflows declare `timeout_seconds: 300-600` per node
- `validate.py` validates timeout_seconds (must be positive int)
- Neither `engine.py` nor `state.py` enforces timeouts
- Timeout is a **hint for the orchestrating agent**, not engine-enforced
- Context budget guard (`_check_context_budget`) is a separate mechanism — blocks parallel dispatch at high context, unrelated to node timeouts

**Recommendation:** Timeout enforcement belongs in `cmd_next` or a wrapper around agent dispatch. Phase 6 scope.

## Gate / Pause / Resume Behavior

**Status: Fully implemented.**

- `cmd_pause(key, node_id, gate_name)` — sets workflow status to "paused", records gate in gates_pending
- `cmd_resume(key)` — pops gate from gates_pending, moves to gates_passed, sets status to "running"
- `cmd_next` — reports paused state with gate name
- Gates are validated against the `gates:` section in YAML
- No timeout on gate pauses (manual resume required)

## Dashboard Dependency Assessment

Three workflows reference external services:

| Workflow | Dependency | Risk |
|----------|-----------|------|
| `security-audit` | Power BI dashboard generation | Medium — fails silently if Power BI unavailable |
| `studio-analytics` | `http://localhost:8000` dashboard API | Medium — fails silently if dashboard not running |
| `feature-research` | GitHub API via gh CLI | Low — gh CLI returns clear error if unauthenticated |

**Dashboard remains a projection surface, not canonical authority.** Workflow failures from unavailable dashboard are operational, not architectural.

## State Persistence / Locking Assessment

**Status: Well-implemented, single-user adequate.**

| Aspect | Implementation |
|--------|---------------|
| State file | `~/.dream-studio/state/workflows.json` |
| Checkpoint file | `~/.dream-studio/state/workflow-checkpoint.json` |
| Lock mechanism | `_file_lock()` — `O_CREAT\|O_EXCL\|O_WRONLY` (atomic creation) |
| Lock timeout | 5 seconds |
| Force-unlock | After timeout, deletes stale lock and retries |
| PID tracking | Lock file contains PID of holder |
| Corruption risk | Low — atomic write pattern, single-user |
| Archive | Terminal workflows emit `workflow.completed`/`workflow.node.completed` canonical events to the spool (WO 9f47a1a0, 2026-07-04 — `archive_workflow()`/`raw_workflow_runs`/`raw_workflow_nodes` removed, migration 141) |
| Schema version | v1 |

## AI/Model Portability Notes (Phase 7 Scope)

All 21 workflows use Claude-specific model names:

| Model Name | Usage Count | Workflows |
|------------|-------------|-----------|
| `sonnet` | 19 | Nearly all |
| `haiku` | 12 | Quick/parallel tasks |
| `opus` | 2 | domain-ingest, idea-to-pr |

These are **not abstracted** — they're passed directly to the orchestrating agent. Abstraction requires:
1. A model capability mapping (fast/balanced/powerful)
2. Adapter layer to resolve capability → concrete model
3. No second tool consumer exists yet — premature to abstract

**This is Phase 7 adapter/portability work, not Phase 5.5A.**

## Phase 5.5A Changes

1. Created this documentation
2. Added workflow runtime reliability tests

## Phase 6 Recommendations

1. Implement retry enforcement in `cmd_next` (re-queue failed nodes with retry budget)
2. Implement timeout enforcement (track node start time, mark timed-out in `cmd_next`)
3. Add dashboard preflight check to studio-analytics workflow
4. Add structured logging for workflow state transitions
5. Clean up stale workflow docs references

<!-- Last reviewed 2026-05-27 — Phase 18.1.16: canonical/skills/workflow/docs/contracts/workflow-contract.md promoted from installed-only to canonical source. Defines the portable primitive contract for workflow skills (required fields, authority boundaries, portable rendering table, validation expectations). No engine, state, or gate policy change in this PR. -->

<!-- Last reviewed 2026-05-28 — Phase 18.4.5: on-memory-ingest added to Stop HANDLERS (position 10). No workflow engine change — this is a hook addition, not a workflow template or execution graph change. Hook doc updates in docs/HOOK_RUNTIME.md. -->


<!-- Last reviewed 2026-05-20 — repo-wide `py -m black .` formatting applied; no behavior or policy change required here. -->

<!-- Last reviewed 2026-05-20 — A3: `control/execution/workflow/runner.py:_invoke_skill` no longer self-shells via `subprocess.run(['ds','skill','invoke', specifier])`; instead it calls `core.skills.invocation.load_skill_content` + `record_skill_invocation` directly in-process. ~40x faster per node, tracebacks intact, mockable. dry_run path unchanged. No policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — B.3: `ds workflow run pre-push --non-interactive` is a deterministic-gate dispatch that bypasses the model-driven workflow engine and invokes `core.gates.pre_push.run_pre_push_gates()` directly. Other workflow names with --non-interactive are rejected (exit 2). No runtime contract change here. -->

<!-- Last reviewed 2026-05-22 — TA3 reviewed; no changes required for this doc. -->

<!-- Last reviewed 2026-05-28 — 18.4.4 reviewed; no workflow runtime changes in this PR. The on-context-inject hook is UserPromptSubmit-only and does not interact with the workflow engine, state, or orchestration layer. -->

<!-- Last reviewed 2026-05-22 — Phase 18.0: spool/emitter.py created (C1 fix). on-context-threshold.py imported from spool.emitter but the module did not exist; every context threshold event silently failed. spool/emitter.emit() wraps CanonicalEventEnvelope + write_envelopes with a non-raising interface (returns True/False). No workflow YAML or hook registration change required. -->

<!-- Last reviewed 2026-05-23 — Phase 18.1.9: control/execution/workflow/runner.py _BARE_TO_PACK entries corrected to use ds-* prefixed pack names (e.g., "core" → "ds-core", "quality" → "ds-quality") matching packs.yaml as of Slice 9. Fallback pack updated from "core" to "ds-core". Workflows using bare mode names in skill specifiers now route to the correct pack at runtime. No workflow YAML, gate, or state contract change. -->

<!-- Last reviewed 2026-05-23 — Phase 18.1.12: No workflow runtime changes. Hook fail-open hardening (BaseException catch, sys.exit(2) removal, individual hook defensive wrappers) is confined to runtime/hooks/ and control/execution/dispatch_tracking.py. No workflow YAML, engine, state, validator, gate, or retry contract change required. -->

<!-- Last reviewed 2026-05-28 — fix/linux-ci-failures-batch2: on-context-threshold.py hook updated (see HOOK_RUNTIME.md for details). No workflow YAML, engine, state, validator, gate, or retry contract change. -->

<!-- reviewed: 2026-05-30, migration 084 (project model unification A2). reg_projects deleted; business_projects is the sole project authority. Session hooks now use marker-based UUID resolution. No semantic changes to this document required. -->

<!-- reviewed: 2026-06-06, WO-C orphan rot sweep. control/execution/workflow/learning.py deleted (zero importers confirmed). Removed its row from Runtime Integration table. sibling tracking.py is live and retained. No workflow YAML, engine, state, validator, gate, or retry contract change. -->

<!-- reviewed: 2026-05-30, brownfield vertical slice migration 085. Stack profile + security_scan_runs. No semantic changes required to this document. -->

<!-- 2026-06-05: Wave 2 career annihilation — career_ops module, 15 career_* tables (migration 100), ds-career skill pack, /career-ops route, career_ops contract+profile, and career expert workflow removed. capability_center/scoped_agents/github_repo_intake unchanged. No career content in this doc; no semantic change required. -->

<!-- 2026-06-06: Wave 5b legacy module removal — wave_executor.py and wave_executor_enhanced.py deleted (zero importers; Audit 3 confirmed). Removed their two rows from the Runtime Integration table. wave.* event types retained (additive-only registry). -->

<!-- 2026-06-06: WO-A telemetry write-path honesty fixes. runtime/hooks/meta/* changes (on-session-end.py, on-skill-metrics.py, on-context-threshold.py, on-post-compact.py) and runtime/dispatch/hooks.py (tool_name snake_case fix). No workflow YAML, engine, state, validator, cost, registry, or retry contract change. Workflow runtime contract unchanged. -->

<!-- Last reviewed 2026-06-07 — WO-O (feat/wo-o-two-tier-gates): pre-push.yaml updated to v2 with advisory tier field. Gate runner and test file updated. No change to hook runtime behavior or workflow execution model — only gate classification metadata added. -->

<!-- 2026-06-07: WO-T autonomous WO-execution workflow. Added execute-work-orders.yaml (9 nodes): capability-probe → preflight-check → migration-class-check → implement-tasks → run-gates → create-branch → push-and-pr → watch-ci → merge → close-work-order → next-iteration. GitHub path is conditional on CapabilityResult (github_repo config + gh CLI auth). Stop conditions: gate failure, migration-class WO (operator go), unresolved critical/high preflight findings. Never --force-close autonomously. inventory count: 22 → 23. -->
<!-- Last reviewed 2026-06-07 — WO-HS (feat/wo-hs-handoff-spawner): on-stop-dispatch.py _dispatch_handoff_continuation() de-silenced. No workflow YAML, engine, state, validator, cost, registry, or retry contract change. Workflow runtime contract unchanged. -->

<!-- 2026-06-07: WO-T2 (feat/wo-t2-autonomous-loop-hardening): execute-work-orders.yaml updated. (1) Added independent-review node (after run-gates, before close nodes): spawns a fresh sonnet agent with no prior work context that reads context.md + git diff HEAD~3..HEAD, verifies each task against acceptance criteria, writes .planning/work-orders/<id>/independent-review.md with VERDICT: PASS/FAIL, prints REVIEW_PASS or REVIEW_FAIL. (2) close-work-order-github and close-work-order-local nodes updated: both depend on [independent-review] and require REVIEW_PASS in output before closing. (3) next-iteration node updated: documents the WO-ORD ready-set selector (sequence_order + work_order_dependencies, scoped to lowest order_index milestone with open WOs); prohibits created_at fallback. New gate in core/work_orders/close.py: independent_review_passed (checks .planning/work-orders/<id>/independent-review.md for "VERDICT: PASS"). Node count: 9 → 13 (split close-work-order into github/local variants + independent-review + corrected count). inventory count: 23 (unchanged). -->

<!-- Last reviewed 2026-06-08 — WO-HS2 handoff-to-authority: No workflow YAML, engine, state, validator, cost, registry, or retry contract change. Hook behavior changes: on-context-threshold.py separates 'handoff' and 'compact' bands; on-stop-dispatch.py _dispatch_handoff_continuation() now reads pending-handoff.json pointer and spawns claude "resume:" (reference-only); on-prompt-validate.py _check_pending_handoff() instruction updated. Workflow runtime contract unchanged. -->

<!-- Last reviewed 2026-06-09 — WO-V (feat/wo-v-onboarding-activation): studio-onboard.yaml updated — two new parallel nodes added after `discovery`: (1) overhead-check: calls core/health/overhead.py::run_overhead_checks(), surfaces advisory MCP footprint + permission sprawl + skill-YAML findings; (2) mcp-auto-wire: probes each mcpServer via probe_mcp_server(), classifies wire-ready/skip/already-wired, deduplicates already-installed skills. synthesis node depends_on extended to include both new nodes and references their output. No changes to workflow engine, state machine, validator, cost, registry, retry contract, or existing node structure. -->

<!-- Last reviewed 2026-06-09 — WO-TS2 PR2 (feat/wo-ts2-p2-engine-boundary): canonical/workflows/pre-push.yaml gains advisory authority-boundary gate — runs core.gates.authority_boundary_check (AST scan of projections/api/ and interfaces/cli/ for connect_analytics(read_only=False) calls outside core/projections/runner.py). Tier: advisory. No workflow engine, state machine, validator, cost, registry, retry contract, or existing gate behavior change. -->

<!-- Last reviewed 2026-06-10 — WO-SETUP2 (feat/wo-setup2-safe-install-uninstall): No workflow YAML, engine, state, validator, cost, registry, or retry contract change. hooks/hooks.json updated with dream_studio_managed markers (see HOOK_RUNTIME.md). Workflow runtime contract unchanged. -->
<!-- Last reviewed 2026-06-11 — WO-GATE-PARITY (fix/wo-gate-parity): canonical/workflows/pre-push.yaml docs-drift gate escalated from tier: advisory to tier: blocking. Root cause of PR #263's local-green/CI-red split: both sides run interfaces/cli/contract_docs_drift_gate.py with the same origin/main...HEAD merge-base change set, but CI enforces the exit code while the local advisory tier only warned. No change to gate ordering, commands, env, or the two-tier runner semantics in core/gates/pre_push.py — manifest tier value only. fail_hint replaces warn_hint accordingly. -->
<!-- Last reviewed 2026-06-11 — WO-EVAL-LOOP (feat/wo-eval-loop): canonical/workflows/pre-push.yaml gains one new blocking gate: rubric-immutability (tier: blocking; command: py -m core.gates.rubric_immutability_gate), inserted before rule4-ingestor-sole-event-writer. Gate detects changes to canonical/skills/domains/eval-rubric.yml without the [rubric-update] commit token; writes a guardrail_decisions row for audit on every run. New file: core/gates/rubric_immutability_gate.py. No workflow engine, state machine, validator, cost, registry, retry contract, or existing gate behavior changed. -->

<!-- Last reviewed 2026-06-12 — WO b57c60eb (feat/wo-b57c60eb-wire-rubric-guardrail-pipeline): no workflow YAML, engine, state, validator, cost, registry, or retry contract change. runtime/hooks/meta/on-edit-dispatch.py gains _check_rubric_guardrail() call (see HOOK_RUNTIME.md). Workflow runtime contract unchanged. --><!-- Last reviewed 2026-06-12 — WO 577b90c3 (feat/wo-577b90c3-dispatch-guardrail-tests): no workflow YAML, engine, state, validator, cost, registry, or retry contract change. runtime/hooks/meta/on-edit-dispatch.py gains is_operator propagation (see HOOK_RUNTIME.md). Workflow runtime contract unchanged. -->

<!-- Last reviewed 2026-06-17 — WO-ESCALATION-LADDER (feat/escalation-ladder): canonical/workflows/execute-work-orders.yaml gains one new node, escalation-probe (model: haiku, context: fresh, depends_on: [capability-probe]; preflight-check now depends_on: [escalation-probe]). It runs `py -m interfaces.cli.ds work-order executor <id>` to resolve the escalation-aware executor and emits EXECUTOR: <model>. The implement-tasks node input gains a "HONOR THE ESCALATION EXECUTOR" instruction so an escalated WO's retry runs on Opus. No engine, state machine, validator, cost, registry, or retry-contract change — one additive node + one dependency rewire + an instruction line. The manual path honors the same flag via start_work_order's executor field (see HOOK_RUNTIME.md is unaffected). -->

<!-- Last reviewed 2026-06-12 — WO-VIEW-GHOSTS: no workflow runtime change. canonical/workflows/pre-push.yaml gains test-fixture-resurrection gate (blocking tier). No workflow engine, state, validator, or cost contract change. -->

<!-- Last reviewed 2026-06-17 — WO-CONTEXT-THRESHOLD-SCALE (fix/context-threshold-scale): no workflow runtime change. The change scales the context-handoff KB thresholds (control/context/handoff.py + monitor.kb_to_band) to the active context window and touches the on-context-threshold hook caller (see HOOK_RUNTIME.md). No workflow YAML, engine, state, validator, cost, registry, or retry-contract change. -->

<!-- Last reviewed 2026-06-21 — db-realignment foundation (chore/schema-cut-to-core): canonical/workflows/pre-push.yaml gains an advisory leanness gate (tier: advisory; command: py -m core.gates.leanness). It points ruff (SIM/C4/PERF/RET/PIE/UP) and vulture (>=80% confidence) at the source tree and prints over-engineering / dead-symbol counts as a hygiene signal; always exits 0. One additive advisory gate entry — no workflow engine, state machine, validator, cost, registry, or retry-contract change. -->
<!-- reviewed 2026-06-26: migration 128 dead-tables removal — no content changes required -->

<!-- Last reviewed 2026-06-27 — Wave 2 substrate realignment (migration 131, worktree-agent-a910d590fedb5c672): no workflow engine/state-machine/validator/retry-contract change. migration 131 retires the dormant execution-graph cluster (execution_nodes/dependencies/outputs/event_links) whose only callers were the unregistered dream_exec.py/exec_graph.py CLIs (now deleted); no registered workflow or node-runner referenced those tables. -->

<!-- Last reviewed 2026-07-02 — WO-ENFORCE-SQLITE (feat/issue-441-enforce-hooks, #441): no workflow engine, state machine, validator, gate-runner, or retry-contract change. The change set adds two blocking hooks (on-edit-enforce PreToolUse, on-stop-enforce Stop) as direct hooks.json entries plus projection/installer propagation — hook runtime only; see HOOK_RUNTIME.md 'SQLite Enforcement Hooks'. No canonical/workflows/*.yaml touched. -->

<!-- Last reviewed 2026-07-03 — WO-PREPUSH-SCHEMA-PINS (3c71fc1b): canonical/workflows/pre-push.yaml gains a blocking pin-tests gate (py -m pytest over the five exact-set schema/contract pin files: duckdb_business_schema, packs_yaml_integrity, plugin_manifest, schema_debt_doc, hook_runtime_reliability; ~60-75s). Rationale: two post-merge full-ci reds in one day (#442-followup, #450-followup) came from pins the pr-smoke matrix does not run; a pin only drifts when a change set adds an object without updating the expected set — a pre-push-time mistake. No workflow engine, state machine, validator, or retry-contract change; one additive blocking gate entry. -->

<!-- Last reviewed 2026-07-03 — WO-TOMBSTONE-GUARD (e5b24ab1): the pin-tests gate in canonical/workflows/pre-push.yaml gains tests/unit/test_schema_tombstones.py (170 frozen dropped-table names; fresh-chain resurrection check + production-creator scan; files.db-scoped ds_documents* exceptions documented in schema_tombstones_data.py). Operator directive: dropped tables must never resurface. No workflow engine/state-machine/validator change; one file added to an existing gate's pytest list. -->

<!-- Last reviewed 2026-07-03 — WO 468ce225-795d-402f-af91-acf69ec78099: canonical/workflows/studio-analytics.yaml's healthcheck and harvest command prompts edited to drop raw_token_usage row-count and `--sessions`-flag references (migration 138 dropped the table; backfill_token_sessions.py's raw_sessions backfill is now unconditional, no flag needed). No workflow engine/state-machine/validator/gate change — the edits are inside existing `command:` prompt text for the healthcheck and harvest steps. -->

<!-- Last reviewed 2026-07-04 — WO-CI-457-FOLLOWUP (667d04e9): pin-tests gate gains tests/unit/test_module_registry_contract.py + tests/unit/test_contract_atlas.py (third post-merge red from the exact-set/contract class — module registry contracts now block at push). No engine change. -->

<!-- Last reviewed 2026-07-04 — WO-CI-460-FOLLOWUP (d033e6f8): pin-tests gate gains tests/unit/test_state_contract_boundaries.py (fourth post-merge red from grep-based contract tests outside pr-smoke; boundary greps now block at push). Comment-substring parser weakness tracked in WO f1037037. No engine change. -->

<!-- Last reviewed 2026-07-04 — WO-CI-462-FOLLOWUP (dce86173): pre-push gains a blocking unit-collect gate (pytest tests/unit --collect-only) — the #462 squash red was 7 phase-19x tests reading deleted migration files, an import-time error invisible to evals/pin-tests/pr-smoke. The 7 files now inline the deleted migrations 095-098 verbatim (recovered from git history) to preserve their hand-built scaffolds. No engine change. -->
