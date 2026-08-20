# ds-workorder:close — Close a work order

**Wraps:**
- `core.work_orders.close.check_close_gates(work_order_id=..., source_root=..., dream_studio_home=..., planning_root=...)` — preview gate status without mutating.
- `core.work_orders.close.close_work_order(work_order_id=..., force=False, source_root=..., dream_studio_home=..., planning_root=...)` — verify gates + mutate to closed + emit spool events.

---

## When to invoke this mode

An active work order is done — the user said so ("close work order", "finish the auth WO", "wrap up this WO"), or `ds-workorder:execute` just reported `all_tasks_complete: True` (chain into close directly, no confirmation needed).

**Every task must be marked done first.** Close enforces a `tasks_done` gate: a WO with any
task not yet `complete` (or deliberately `cancelled`) cannot close without `force=True` — there
are no 0/N or partial closes. Both the CLI close path and the autonomous execute-work-orders
loop go through the same `close_work_order`, so this is enforced identically everywhere. If you
believe the WO is done but close reports a `tasks_done` failure, mark the remaining tasks via
`ds-workorder:execute` rather than force-closing.

## What to do

1. **Preview gates first.** Call `check_close_gates(work_order_id=<wo>, source_root=..., dream_studio_home=..., planning_root=...)`. The returned dict tells you whether the WO would close cleanly without actually mutating anything.

2. **If `gates_pass is True`:** call `close_work_order(work_order_id=<wo>, source_root=..., dream_studio_home=..., planning_root=...)` directly — no confirmation on the normal path. Surface the result dict (see contract below).

3. **If `gates_pass is False`:** present the `gate_failures` list verbatim — one bullet per failure. Then offer two paths:
   - **Fix the gates** (preferred): suggest the skill that addresses each failure. For example, `tasks_done` → invoke `ds-workorder:execute` and mark the remaining tasks done (do NOT force past hanging tasks); `design_brief_locked` → invoke `ds-project:brief` to fill and then `ds-project:brief` lock mode; `design_critique` → invoke `website:critique`; `security_scan` → invoke `security:scan`; `api_contract_exists` → write the contract spec (from `docs/specs/SPEC-000-template.md`) and **ratify** it (set Status: `Ratified`) — for WOs created on/after the 2026-08-02 cutover the gate blocks a non-Ratified spec (see `docs/specs/README.md`); `change_impact_affirmed` → run `ds work-order affirm-impact <id> [--auth] [--contract] [--migration] [--changelog]` to record the change's impact classes (CLAUDE.md's Code History & Impact Guardrail; WOs created before the 2026-08-02 cutover are grandfathered).
   - **Force close** (requires explicit user approval — this is a stop condition): explain that `force=True` will bypass the failed gates and emit `gate.bypassed` spool events. Confirm: *"Bypass these gates? This is recorded for audit. (yes/no)"* — only on explicit yes, call `close_work_order(work_order_id=<wo>, force=True, ...)`.

4. **Surface the close result.** Close is **report-only** — it never auto-starts the next work order (that side effect used to pile up dangling in-progress WOs on every close).
   - If `gaps_block` is present, print it verbatim — the independent review found gaps and registered a remediation WO (`spawned_work_orders`). Surface its `next_command` so the operator can start it when ready.
   - If `main_ci_warning` is present, **print it verbatim.** It is advisory — it never blocks the close and never means this WO failed. A red `main` from someone else's merge must not stop unrelated work; the defect it fixes was invisibility, not permissiveness. The line states whether the failing run **includes your local HEAD** (your own work is in it) or **predates** it, and says so when that is unknown. Do not paraphrase it into a verdict, and do not re-run gates because of it.
   - If `milestone_complete` is present, the milestone is done: surface `next_command` (milestone close) and stop.
   - Otherwise surface `next_block` / `next_command` (the ready-set next WO) so the user knows what's next, then **stop** — starting the next WO is an explicit operator decision on the interactive path.
   - **Autonomous execute-work-orders loop only:** the workflow's `next-iteration` node starts the advertised next WO and re-invokes the loop. The interactive close path does not chain.

## Stop conditions

Close is report-only: after a clean close on the interactive path, surface `next_command` and **stop** — the operator decides what to start next. Only the autonomous execute-work-orders workflow chains (its `next-iteration` node starts the advertised next WO and re-invokes). Places the agent waits for the operator:
- Force-close approval (gate bypass).
- `requires_brief_confirmation` on start.
- `milestone_complete` (milestone done — milestone close is an operator decision).
- A blocked WO.
- A genuine blocking question the agent cannot resolve from the WO, the code, or sensible defaults.

## Surface contract

`check_close_gates` returns::

    {
      "ok": True,
      "work_order_id": str,
      "title": str,
      "type_id": str | None,
      "project_id": str,
      "milestone_id": str | None,
      "pre_gate": str | None,
      "post_gate": str | None,
      "gates_pass": bool,
      "gate_failures": [str, ...],
    }

`close_work_order` returns one of three shapes:

- WO not found: `{"ok": False, "error": "Work order not found: <id>"}`
- Gates failed without force: `{"ok": False, "error": "Gate check failed", "failures": [...]}`
- Success or forced::

      {
        "ok": True,
        "work_order_id": str,
        "title": str,
        "status": "closed",
        "forced": bool,
        "bypassed_gates": [str, ...],          # populated when forced
        "verify_warning": str | absent,        # inline verify was unreviewable (no commit evidence) — surface verbatim
        "main_ci_warning": str | absent,       # post-merge Full CI for main is RED — surface verbatim, advisory
        "test_execution_warning": str | absent, # the review certified by reading, not running — verbatim, advisory
        "main_ci": {...} | absent,             # the reading behind it (status/red/head_sha/run_url/as_of/age_seconds/local_head_includes_run)
        "next_work_order": {...} | absent,     # next open WO in same milestone
        "next_command": str | absent,          # explicit next-step hint
        "next_block": str,                     # printable NEXT WORK ORDER / MILESTONE COMPLETE / none-found block
        "milestone_complete": True | absent,
        "milestone_id": str | absent,
        "gaps_block": str | absent,            # printable GAPS FOUND block when independent review failed
        "spawned_work_orders": [{...}] | absent,  # remediation WOs registered from review gaps
      }

    # Close is REPORT-ONLY: it advertises the next WO (`next_work_order` = the ready-set
    # pick) and how to start it (`next_command`/`next_block`) but never starts it — there
    # is no `auto_started`/`auto_start_error` key. Starting the next WO is an explicit
    # operator action (or the execute-work-orders workflow's next-iteration node).

## `design_brief_locked` failed on a brief that IS locked {#brief-currency}

The gate asks two questions now, and the failure text says which one failed (WO-BRIEF-CURRENCY):

| Failure text | Meaning | Remedy |
|---|---|---|
| `no locked design brief found` | none exists | `ds-project:brief` — fill and lock |
| `existence but not currency` | one is locked, but UI work closed since | re-lock, **or** declare reviewed-no-change |

**DON'T** send the operator to fill-and-lock a brief that is already locked. The second failure names the UI-class work orders that moved the surface — surface those, because they are what has to be reviewed against.

**DO** pick the remedy by what actually changed:

- **Re-lock** (`ds-project:brief`) when the design language moved. This does not require re-running the whole wizard.
- **Declare no-change** when the surface moved but the brief still holds:
  `ds design-brief reviewed-no-change <project_id> --note "<why it still holds>"`
  The note is required and recorded, and the declaration carries its own timestamp — so later UI work stales the brief again. It is a judgement on the record, not a mute button.

**DON'T** reach for the declaration to avoid a re-lock. A recorded "still holds" about a brief that no longer does is worse than a stale lock, because it looks like someone checked.

## What the tests rest on {#separate-test-runner}

`all_tests_pass` **executes** the TEST-CHECKs — no report is read, and the "a file containing PASSED" fallback is retired, so a self-reported pass cannot satisfy it. Two things still need your eyes. **What the review rested on:** close returns `test_execution_warning` when the verdict certified by reading rather than running (no TEST-CHECK registered, or none executed at verify) — print it verbatim; it never blocks, and `ds work-order merge-check` says the same thing earlier. **Who ran them:** whoever wrote the change does not run its own suite as the evidence — spawn a runner and hand it node ids, not a conclusion.

## After the merge: pr-smoke green is not proof main is green

**DO** check the post-merge Full CI run for `main` after every merge:

    gh run list --branch main --workflow "Full CI" --limit 3

or read `checks.main_ci` (`ds doctor`) or `main_ci` (`ds project state`) — both carry the same reading, and both may serve a cached answer that states its own age.

**DON'T** treat a green 3-platform matrix as proof `main` is healthy. Merge authorization and main's health are different claims measured by different suites:

| Stage | What runs | What it proves |
|---|---|---|
| pre-push gates | 20 gates, local | this change set passes the local bar |
| `pr-smoke` matrix (3 platforms) | ~11 focused files | **merge authorization** |
| `full-ci` (post-merge, ubuntu only) | the full suite (~5,400 tests) | main is actually green |

A merge can be correctly authorized and still break `main` — the full suite never ran before it landed. On 2026-08-19 `main` sat red across **eight** merges before an operator noticed, and twice more that day a red was found only because someone thought to look. Every one of those was a single failing test out of ~5,386.

**DO** treat a red `main` you caused as the next thing you work on. **DON'T** let someone else's red block your close — `main_ci_warning` is advisory precisely so it cannot.

## Side effects

- Runs a projection tick (`sync_tick`) before reading task statuses so freshly marked-done tasks are reflected (no false `tasks_done` failure from projection lag).
- Blocks the close when any task is not done (`tasks_done` gate) unless `force=True`; a forced close records the bypass via a `gate.bypassed` event carrying the `tasks_done` reason.
- For an **escalated** WO (reopened because the deterministic verifier said NOT FIXED), re-close REQUIRES a passing independent review: the unreviewable/gap bypasses are skipped and `force=True` cannot bypass the `independent_review` gate (the result carries `escalated: True`). Get a passing `review-verdict.json` rather than forcing.
- Sets the WO row's `status` to `closed`.
- Emits a `work_order.closed` spool event.
- When `force=True` with failures, emits one `gate.bypassed` event per failure for audit.
- When the post-build gate is `independent_review`, runs the fresh-context verify inline; review gaps register remediation WOs, reported via `gaps_block` + `spawned_work_orders` (not started — run the reported `next_command` to begin remediation).
- When verify passes, advertises the project-wide ready-set next WO via `next_work_order` / `next_command` / `next_block` — **report-only, the WO is not started** (the autonomous execute-work-orders workflow starts it in its next-iteration node).
- Reads the post-merge Full CI verdict for `main` (advisory) and, when it is RED, adds `main_ci_warning` + `main_ci` to the result. Reads **live** (never from the status cache that `ds doctor` / `ds project state` may use), because declaring work done is the one moment that must not be told about main by a cache. Never blocks, never fails a gate, never fabricates green: an unavailable/unauthenticated/timed-out `gh` yields `status="unknown"` **with a reason**.
