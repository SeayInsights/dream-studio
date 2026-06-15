# ds-workorder — Work Order Lifecycle

**Type:** Function-backed skill pack
**Invocation:** matched by per-mode triggers in `modes/*/metadata.yml`
**Not a CLI command.** The AI invokes one of the five modes below by calling the named function in `core.work_orders.*` and presenting the returned dict to the user.

The Dream Studio source-of-truth is the SQLite authority. This pack does not reason about work-order state from session memory or training knowledge. Every mode calls a named query or mutation function and surfaces its returned data.

---

## Mode dispatch

| Mode | File | Wraps | Keywords |
|------|------|-------|----------|
| start | `modes/start/SKILL.md` | `core.work_orders.start.start_work_order` | start work order:, begin work order: |
| execute | `modes/execute/SKILL.md` | `core.work_orders.mutations.mark_task_done` | mark task done:, task done:, complete task: |
| close | `modes/close/SKILL.md` | `core.work_orders.close.close_work_order` (+ `check_close_gates`) | close work order:, finish work order: |
| block | `modes/block/SKILL.md` | `core.work_orders.mutations.block_work_order` | block:, blocked by: |
| status | `modes/status/SKILL.md` | `core.work_orders.queries.list_work_orders` (+ `list_tasks`) | work order status:, show tasks: |

---

## Rules that apply to every mode

1. **Read functions before you write.** If a state-surfacing instruction below does not name the specific query function being called, stop and add it. Never narrate state from session context or training data.
2. **Present returned dicts. Don't invent fields.** The function returns a dict with a known shape. Show those fields. If the user asks for a field that isn't there, say so — don't fabricate it.
3. **Mutations require explicit user confirmation.** start, execute, close, block all mutate state. Confirm intent before calling the function, then call it, then show the user the returned dict so they can verify the change.
4. **Errors are operator-visible.** When a function returns `ok=False`, surface the `error` field verbatim. Do not paraphrase or soften the message.
5. **No raw UUIDs to the user unless asked.** Use the work_order_id internally; refer to the work order by its `title` in conversation. The user can ask for the ID.
6. **Task descriptions should include behavioral acceptance criteria.** When authoring tasks (via scope or during a WO), each task description should include an "Acceptance:" clause stating what the operator observes when the task is done. The independent review completion grader will emit a warning gap if feature/infrastructure WOs have no observable behavioral AC — this is not a fail, but it signals that the grader could not verify expected operator outcomes.

7. **SQL-CHECK lines for DB-state ACs.** A task's `acceptance_criteria` field may include one or more `SQL-CHECK:` lines (format: `SQL-CHECK: <SELECT statement>`). The completion grader executes these read-only against the authority DB before analyzing the diff. A query returning a non-zero/non-null first column passes; zero/null/no rows or any error fails. A `SQL-CHECK RESULT: FAIL` annotation forces that task to verdict `"missing"` regardless of diff evidence. Use SQL-CHECK when the task outcome is a database state change not visible in the diff (e.g. a migration row, a column added by bootstrap). See `docs/authoring/work-orders.md` for the full convention.

8. **Executable acceptance criteria BLOCK close (always-on AC gate).** `close_work_order` runs every task's `acceptance_criteria` as executable checks and blocks close on any failure, regardless of WO type. Three line-prefixes are supported: `SQL-CHECK: <SELECT>` (read-only DB query, passes on truthy first column), `TEST-CHECK: <pytest-node-id>` (runs that pytest node in a subprocess; passes iff exit 0), and `API-CHECK: <METHOD path -> [status]>` (boots the API via TestClient; passes on 2xx/expected status + non-empty body). A WO **cannot close without `force=True` unless it has at least one executable check** across its tasks — author at least one SQL/TEST/API-CHECK AC per WO. `force=True` bypasses and emits `gate.bypassed`. The legacy `all_tests_pass` gate now executes the WO's TEST-CHECKs instead of grepping `test-results.md`.

<!-- Last reviewed 2026-06-12 — WO-SPAWN-DEDUPE: _insert_gap_work_orders in core/work_orders/verify.py gains title-match dedup; merges tasks into existing open WO instead of spawning duplicate. merged_into_existing field added to result. No skill instruction change required — existing mutation discipline unchanged. -->

<!-- Last reviewed 2026-06-12 — WO-VIEW-GHOSTS: no work-order skill instruction change. core/work_orders/verify.py _CORRECTNESS_PROMPT_TEMPLATE gains rule (8) for dead-table resurrection detection. Skill surface and mutation discipline unchanged. -->

<!-- Last reviewed 2026-06-12 — WO-2dbcdc63: core/work_orders/verify.py _find_migration_files gains Path(source_root) coercion to handle os.getcwd() returning str. Pure bug fix, no skill interface change. -->

<!-- Last reviewed 2026-06-13 — WO-AUTHORITY-GRADER: core/work_orders/verify.py gains _run_sql_checks() and _format_sql_checks(). SQL-CHECK: lines in acceptance_criteria are now executed against the authority DB before graders run. Results injected into task_list_str as ground truth. Rule 7 added above; docs/authoring/work-orders.md created. -->

<!-- Last reviewed 2026-06-13 — WO-VERIFY-NOSUMMARY: core/work_orders/verify.py _collect_grader now treats empty/whitespace LLM output as unreviewable ({"unreviewable": True, "reason": "grader_no_summary"}) instead of raising ValueError. _run_graders_parallel retries once on unreviewable with a 30s timeout. verify_work_order detects unreviewable graders after retry and writes an unreviewable verdict (unreviewable_graders: [...]) mirroring the existing no-commits-found path — close proceeds without force. close_work_order surfaces unreviewable_graders in result when set. The independent_review gate already passes on unreviewable: True. No skill surface change. -->

<!-- Last reviewed 2026-06-14 — WO-SYMPTOM-RESOLUTION (feat/symptom-resolution): close_work_order() in core/work_orders/close.py gains _check_originating_symptom() — a new implicit gate that re-runs the originating_symptom SQL-CHECK after regular gate evaluation. If the symptom SQL still returns 0/falsy (or errors), close is blocked with failures=[...originating_symptom...]. Bypassed by force=True consistent with other gates. mutations.py gains: (1) originating_symptom param on create_work_order() — included in the work_order.created event payload and materialized by WorkOrderProjection; (2) set_originating_symptom(work_order_id, symptom, source_root) — direct UPDATE for post-creation backfills. Skill surface unchanged: close mode still calls close_work_order(); mutations mode still calls create_work_order() and mark_task_done(). No new mode, no new routing keyword, no new CLI subcommand added. -->

<!-- Last reviewed 2026-06-15 — WO-AC-EXECUTABLE (feat/ac-executable-gate): core/work_orders/verify.py gains run_executable_checks() dispatching SQL-CHECK / TEST-CHECK (pytest node via subprocess, sys.executable) / API-CHECK (FastAPI TestClient), fail-closed on unknown/malformed CHECK lines. core/work_orders/close.py wires an always-on AC gate (_run_ac_gate + _read_wo_tasks) into both close_work_order and check_close_gates regardless of WO type: any failing executable check blocks close, and a WO with zero executable checks cannot close without force=True. The all_tests_pass gate now executes TEST-CHECKs (run_gate_check gains optional db_path) instead of grepping test-results.md. force=True bypasses and emits gate.bypassed per failure. Rule 8 added above. Skill surface (modes/routing/CLI) unchanged — close mode still calls close_work_order(). -->