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

## Node Observation and the Operator Rules

**Status: Enforced by the runtime, in `--execute` runs only.**

Two fields decide whether a node's completion is believed, and one rule plane judges what
happened.

- `completion_check` — a shell command run after the node, observing state from OUTSIDE
  the node's own account (a git ref, a status query, a gate's last line). It must be a
  cheap read, never the work itself: it runs under a 60s cap
  (`_COMPLETION_CHECK_TIMEOUT`), and a check that times out reports blocked forever.
- `completion_unobservable: "<reason>"` — the recorded escape for a node that genuinely
  cannot be checked yet. Eight of `execute-work-orders`' 14 nodes carry one; most need the
  active work order id the runner cannot template, and `pre-push` runs a gate that takes
  minutes. A reason under 12 characters is refused, the same shape as
  `--accept-structure` at close: an escape is a reason a later reader can weigh, never a
  bare flag.

**A node must do one or the other.** `absence_is_not_clean` fails a node recorded complete
with neither, because "nobody looked" and "nothing was wrong" are different facts.

These reasons were YAML COMMENTS until 2026-09-02, and `yaml.safe_load` drops comments —
so the rule that asks "was anything declared here" could not see a single one of the eight
stated reasons, and enforcing the rules would have flipped every correctly-documented node
to blocked. A declaration a parser cannot read is not a declaration. The test guarding the
gap searched the raw file text for the comment and passed throughout.

### A completion check's interpolated values are shell-quoted

`completion_check` supports `{{node.field}}` templates so a check can name the thing it
is checking — "does the PR exist" needs the PR number the previous node printed. Those
values are prior nodes' output: agent-generated text, or whatever a command node
captured. The check is then run with `shell=True`.

Until 2026-09-02 the resolved value went into that string raw, so an output containing
`; rm -rf ~`, `$(...)` or backticks became **shell syntax** in a command this runner
executes unattended during an `--execute` run (WO `e4e85949` task `52f2c484`).
`resolve_templates` now takes a `transform`, and `_verify_completion` passes
`shlex.quote`, so each substituted value is exactly one argument and never syntax.

Two things are deliberately NOT quoted, and the distinction is load-bearing:

- **The template around the values.** It is authored in the repo and its pipes and
  redirects are intended; quoting the whole string would break every check, which all
  pipe into `grep`.
- **`completion_contains`.** It is compared as a substring against the check's output and
  never executed, so quoting it would add literal quote characters to the thing being
  matched.

`transform` defaults to none, because the PROMPT path resolves the same templates and
wants the raw text — quoting there would corrupt every prompt that references a prior
node.

### The rules run where the status is decided

`control/execution/workflow/autonomy.py::OPERATOR_RULES` holds six predicates —
`no_false_done`, `gates_not_prose`, `absence_is_not_clean`, `defect_is_registered`,
`never_force`, `never_push`. `WorkflowRunner._execute_wave` evaluates them against each
finished node, and a violation on a node that reported `completed` makes it `blocked`. The
text handed to a reviewing agent (`stance_brief()`) is DERIVED from the same rules, so it
cannot drift from them.

`evaluate_operator_rules` had no call site until 2026-09-02: only `stance_brief()` was
wired, so the operator's positions reached a run as prose for an agent to follow and never
as checks — the exact substitution the rules exist to prevent. The `reachability` gate
caught it.

**Scope: `--execute` runs only.** A dry run marks nodes completed having executed nothing,
and prompt-delivery mode hands a node's prompt to a human. Neither asserts that work
happened, so judging them flags every node and halts both modes. Same scoping as
`_verify_with_retry`, and the same lesson as the structural invariants at close: a rule
belongs at the moment the claim is made.

**Retry budget 2, then diagnose — never move on.** On exhaustion a FRESH reviewer is
invoked rather than another execution attempt, and it walks the eight-class falsification
taxonomy (`core/work_orders/scenario_taxonomy.py`) by name rather than improvising a
checklist. The diagnosis is then registered in the authority via `prescribe()` — one
finding becomes a task, several become a work order.

**An executing node cannot push.** `remote_head` is read before and after execution; if
the remote-tracking ref moved, the node fails with the violation named. Opening a pull
request is the reviewing step's decision.

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

<!-- Last reviewed 2026-07-19 — WO-HOOK-ENFORCE-EXEC-STATS (d1150c16): the on-edit-enforce (PreToolUse) and on-stop-enforce (Stop) hooks now best-effort emit system.hook.execution.logged so they appear in the DuckDB hook_executions view. No workflow engine, template, or execution-graph change — this is a hook-telemetry addition; full detail in docs/HOOK_RUNTIME.md. -->


<!-- Last reviewed 2026-05-20 — repo-wide `py -m black .` formatting applied; no behavior or policy change required here. -->

<!-- Last reviewed 2026-05-20 — A3: `control/execution/workflow/runner.py:_invoke_skill` no longer self-shells via `subprocess.run(['ds','skill','invoke', specifier])`; instead it calls `core.skills.invocation.load_skill_content` + `record_skill_invocation` directly in-process. ~40x faster per node, tracebacks intact, mockable. dry_run path unchanged. No policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — B.3: `ds workflow run pre-push --non-interactive` is a deterministic-gate dispatch that bypasses the model-driven workflow engine and invokes `core.gates.pre_push.run_pre_push_gates()` directly. Other workflow names with --non-interactive are rejected (exit 2). No runtime contract change here. -->

<!-- Last reviewed 2026-05-22 — TA3 reviewed; no changes required for this doc. -->

<!-- Last reviewed 2026-05-28 — 18.4.4 reviewed; no workflow runtime changes in this PR. The on-context-inject hook is UserPromptSubmit-only and does not interact with the workflow engine, state, or orchestration layer. -->

<!-- Last reviewed 2026-05-22 — Phase 18.0: spool/emitter.py created (C1 fix). on-context-threshold.py imported from spool.emitter but the module did not exist; every context threshold event silently failed. spool/emitter.emit() wraps CanonicalEventEnvelope + write_envelopes with a non-raising interface (returns True/False). No workflow YAML or hook registration change required. -->

<!-- Last reviewed 2026-05-23 — Phase 18.1.9: control/execution/workflow/runner.py _BARE_TO_PACK entries corrected to use ds-* prefixed pack names (e.g., "core" → "ds-core", "quality" → "ds-quality") matching packs.yaml as of Slice 9. Fallback pack updated from "core" to "ds-core". Workflows using bare mode names in skill specifiers now route to the correct pack at runtime. No workflow YAML, gate, or state contract change. -->

<!-- Last reviewed 2026-05-23 — Phase 18.1.12: No workflow runtime changes. Hook fail-open hardening (BaseException catch, sys.exit(2) removal, individual hook defensive wrappers) is confined to runtime/hooks/ and control/execution/dispatch_tracking.py. No workflow YAML, engine, state, validator, gate, or retry contract change required. -->

<!-- Last reviewed 2026-05-28 — fix/linux-ci-failures-batch2: on-context-threshold.py hook updated (see HOOK_RUNTIME.md for details). No workflow YAML, engine, state, validator, gate, or retry contract change. -->

<!-- Last reviewed 2026-07-19 — WO-AUTOACT-B: on-prompt-route added to the UserPromptSubmit HANDLERS list (hook addition only, see HOOK_RUNTIME.md). It is UserPromptSubmit-only and injects a routing directive; it does not interact with the workflow engine, execution graph, state, validator, or gate policy. No workflow YAML, engine, state, validator, gate, or retry contract change. -->

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

<!-- Reviewed 2026-07-05 — WO 6d978483 (PEP 585/604 modernization [2/2]): source files in this domain received mechanical type-annotation modernization only (PEP 585 builtin generics, PEP 604 unions, datetime.UTC) via ruff UP safe autofixes. No contract, behavior, schema, routing, API-shape, or CLI-surface change — reviewed, no doc content change needed. -->

<!-- Last reviewed 2026-07-21 — WO-CLOSE-REPORT-ONLY (fix/close-report-only-no-autostart): `canonical/workflows/execute-work-orders.yaml` next-iteration node now runs `py -m interfaces.cli.ds work-order start <next_id>` explicitly (for the parsed next_work_order) BEFORE re-invoking the loop. This is required because `core/work_orders/close.py::close_work_order` is now report-only (it no longer auto-starts the next WO — that side effect piled up dangling in_progress WOs on directed closes), so the loop must start the next WO itself or the re-invoked workflow's start-less implement-tasks node would find no in_progress WO. No node added/removed (count stays 13), no dependency/trigger_rule/model/timeout change — one command line added to next-iteration. -->


<!-- Reviewed 2026-07-23 — WO-FILESDB-P3 S4a (feat/planning-zero-disk-enforce): the on-edit-enforce hook change (deny .planning/** disk writes, docstore_only) touches runtime/hooks/**, which shares the workflow_and_hooks contract domain with this doc. Reviewed: no workflow-runtime change — no node/dependency/trigger/model/timeout/registration change to any canonical/workflows/** or control/execution/workflow/**. Hook-only edit; see docs/HOOK_RUNTIME.md. -->

<!-- Last reviewed 2026-08-08 — WO-PREPUSH-DIST-FRESH (Gate & CI Hardening): the pin-tests gate in canonical/workflows/pre-push.yaml gains tests/unit/test_plugin_dist.py so the committed dist/plugin freshness guard (test_committed_dist_plugin_is_fresh) runs at push time, not only in the full ubuntu suite. #610 edited canonical skills without re-projecting dist/plugin; the freshness test lived only in full-ci, so pre-push AND the pr-smoke matrix went green while main's full-ci went red. Same file also added to the pr-smoke focused-smoke set (.github/workflows/ci.yml) so it fails on all three platforms before merge. No workflow engine, state machine, validator, cost, registry, or retry-contract change — one file added to an existing gate's pytest list (same class as WO-TOMBSTONE-GUARD / WO-PREPUSH-SCHEMA-PINS). -->

<!-- Reviewed 2026-08-19 — WO-BYPASS-TELEMETRY (2f6b5a8a): no workflow-runtime change. The two enforce hooks gained bypass/fail-open telemetry (DS_ENFORCE=0 short-circuit, lib-import failure, missing authority DB now emit HOOK_EXECUTION_LOGGED records with decision=bypass) and the migration-risk / docs-drift gates record their acknowledgment escapes as gate.bypassed events — see docs/HOOK_RUNTIME.md for the full record/read-surface map. Workflow dispatch, node semantics, and the pre-push manifest are unchanged; no gate was added or removed and no gate outcome changed. -->

<!-- Reviewed 2026-08-19 — WO-HOOK-COVERAGE (f2dda052): no workflow-runtime change. The PreToolUse enforcement matcher widened (Bash + MCP write tools) and on-edit-enforce gained write-target extraction + the module_boundary advisory — see docs/HOOK_RUNTIME.md. Workflow dispatch, nodes, and the pre-push manifest are unchanged. -->

<!-- Reviewed 2026-08-19 — WO-HOOK-DRIFT-STOP (e294b06e): no workflow-runtime change. Hook-projection drift detection widened to the full copied tree and the stop hook re-blocks while violations persist (capped, loud allow) — see docs/HOOK_RUNTIME.md. Workflow dispatch, nodes, and the pre-push manifest unchanged. -->

<!-- Reviewed 2026-08-19 — WO-CI-COMPLETENESS (04953426): pre-push manifest gains the blocking test-list-completeness gate (listed-path existence + post-merge-only visibility; see docs/operations/lightweight-github-ci-strategy.md). No other workflow-runtime change. -->

<!-- Reviewed 2026-08-19 — WO-LOCALE-DECODE-SILENT-LOSS (d771b2da, Adversarial Verification Integrity): pre-push manifest gains the blocking locale-decode gate (py -m core.gates.locale_decode_gate), inserted between test-list-completeness and atlas-leak. It AST-scans for subprocess run/check_output/Popen/check_call calls passing text=True or universal_newlines=True without encoding=. Rationale, measured not assumed: text=True alone decodes the child with locale.getpreferredencoding(False) — cp1252 on Windows — and on a byte cp1252 leaves unmapped (0x81/0x8D/0x8F/0x90/0x9D, i.e. the UTF-8 continuation bytes of the cross mark U+274C, the left arrow U+2190, and the emoji variation selector U+FE0F, all of which appear in this repo's own gate output) the reader thread dies while run() returns returncode=0 with stdout=None. Effect on THIS runner: core/gates/pre_push.py did `completed.stdout or ""`, so a failing gate's stdout_tail/stderr_tail silently became empty — exit codes still carried every verdict, so no gate verdict flipped; the diagnostic was what vanished. 62 product sites across 37 files (eleven of them gate files) plus 56 test sites now name utf-8 with errors="replace". Gate carries an inline exemption marker (`# locale-decode-gate: intentional`) used only by its own test, and PRINTS every exemption on pass and fail alike. tests/unit/test_locale_decode_gate.py added to the pr-smoke focused set so the repo-wide check also runs on all three platforms. No workflow engine, state machine, validator, cost, registry, or retry-contract change — one additive blocking gate entry (same class as WO-CI-COMPLETENESS). -->

<!-- Reviewed 2026-08-27 - WO-GITIGNORE-PHANTOM (bab28970) + WO-EVIDENCE-BACKED-OUTPUT (f7af0888), feat/multiroot-grading: pre-push manifest gains TWO blocking gates, taking canonical/workflows/pre-push.yaml from 21 to 23. (1) gitignore-phantom (command: py -m core.gates.gitignore_phantom) fails a push whose CHANGED files read or assert an on-disk path that git will not ship - green locally where the file exists, broken on a fresh checkout for every other user. Observed twice before it existed: nine verify_*.py split siblings untracked under the .gitignore rule verify_*.py, so a clean clone raised ModuleNotFoundError; and a review-rules profile authored under .dream-studio/, which .gitignore excludes as private runtime state, asserted by a committed test that passed locally. Uses git ls-files and git check-ignore -v, so the failure names the file, line, referenced path, and the excluding rule with its own line number. Write targets are excluded deliberately (a writer naming its output is not a phantom reference); runtime-built paths and non-Python references are accepted false negatives, documented in the module. (2) evidence-backed-output (command: py -m core.gates.evidence_backed_output --staged) implements the operator ruling that anything pushed to GitHub must be backed by evidence, show it, and be verified. --staged audits what a push actually publishes - the COMMIT MESSAGES of commits being pushed, plus lines ADDED to CHANGELOG.md - because a PR body does not live in the repository; a PR body is auditable by path through the same CLI. A claim is backed by a command and its output, a test count with its unit, a file.py:line, a commit sha, a run id, or a named artifact. A hedge inside a quotation is exempt, since quoting the offending line is how a document explains the rule. NO hook dispatch, hook entry point, hook projection, or fail-open policy change - manifest entries and two new gate modules only. The gate runner (core/gates/pre_push.py) is unchanged; both entries are ordinary blocking gates it already knows how to execute. -->

<!-- Reviewed 2026-08-28 - WO-UNVERIFIED-CLAIMS + WO-MULTIROOT-REVIEW tasks 8-9, feat/type-aware-standards: a new advisory check and no hook-dispatch change. core/gates/unverified_claims.py::audit_claims flags an ASSERTED ABSENCE that cites nothing -- "nothing does X", "no gate covers this", "has no caller", "does not exist". It is the inverse of evidence-backed-output: that gate catches an author who is unsure and says so without citation; this catches an author confident about the existing system who never checked, which is worse because confident-and-wrong reads as fact. Wired into core/work_orders/mutations.py::create_work_order and ::create_task, which return an `unverified_claims` note. IT NEVER BLOCKS: a defect must always be registerable, and refusing a registration would trade a small error for an unrecorded defect. Not a pre-push gate and not a hook -- no entry in canonical/workflows/pre-push.yaml, no hook registration, no fail-open policy change; it runs inside the two authority-write functions only. A rule is not a claim ("must not happen" states intent) and a correction is not a new claim, or the check would penalise the behaviour it exists to encourage. The shared citation vocabulary in core/gates/evidence_backed_output.py gained grep/rg/ls-files/check-ignore/find/wc and the "-> N hits" form: it previously could not recognise the most common way an absence is established, so a properly-checked claim was reported as unchecked. -->

<!-- Reviewed 2026-08-28 - WO-NODE-COMPLETION-EVIDENCE (1db6de49) tasks 1-3, feat/type-aware-standards: control/execution/workflow/runner.py changes WHEN a node is reported complete. No hook dispatch, hook registration, or fail-open policy change; the dependency logic, ready-node computation and state file are untouched.

BEFORE: _execute_wave set `status = "completed" if success else "failed"`, where success meant _invoke_skill had LOADED the node's text. That text ends "The AI reading this output has the skill instructions above and should now execute them" -- so a node was marked completed when its PROMPT WAS PRINTED, not when its work happened. Measured: all 14 nodes of canonical/workflows/execute-work-orders.yaml are prose-for-an-agent and none is executable as written.

AFTER: a node may declare `completion_check` (a shell command whose exit status is the evidence) and optionally `completion_contains` (text its output must carry, for a command that exits 0 while printing 'Overall: FAIL'). Three outcomes: check passes -> completed; check fails -> BLOCKED with what was expected and what was seen; NO check declared -> `unverified`, NOT completed, because a node whose effect nobody observed has not been shown to have happened. Node status vocabulary gains `unverified` and `blocked` alongside running/completed/failed/skipped.

BLOCKED IS NOT FAILED: failed means the work was attempted and went wrong; blocked means the effect is not there yet. A driver must stop at blocked without recording a failure.

WHY THIS PRECEDES A DRIVER. `ds workflow run --until-blocked` is deliberately sequenced AFTER these three tasks. A loop calling `advance` over unverified completion would march through fourteen nodes printing prompts and declaring success with no work done -- the assert-instead-of-verify defect at the orchestration layer, where it is hardest to notice. The completion check is what makes a driver safe. Checks are bounded at _COMPLETION_CHECK_TIMEOUT=60s and must be cheap reads (a git ref, a status query), never the work itself. -->
