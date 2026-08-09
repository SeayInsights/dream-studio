# ds-milestone — Milestone Lifecycle

**Type:** Function-backed skill pack
**Invocation:** matched by per-mode triggers in `modes/*/metadata.yml`
**Not a CLI command.** The AI invokes one of the two modes below by calling the named function in `core.milestones.*` and presenting the returned dict to the user.

A milestone is a verifiable delivery boundary that bundles several work orders. The Dream Studio SQLite authority is the source of truth for milestone state. This pack does not narrate milestone status from session memory; every mode calls a query or close function and surfaces what it returned.

---

## Mode dispatch

| Mode | File | Wraps | Keywords |
|------|------|-------|----------|
| status | `modes/status/SKILL.md` | `core.milestones.queries.get_milestone_status` (+ `list_milestones`) | milestone status:, milestone progress: |
| close | `modes/close/SKILL.md` | `core.milestones.close.close_milestone` | close milestone:, milestone done: |

---

## Rules that apply to every mode

1. **Read functions before you write.** Every state-surfacing instruction names the specific query function being called. Never describe milestone progress from session context.
2. **Present returned dicts. Don't invent fields.** The functions return dicts with a known shape. Show those fields. If the user asks for a field that isn't there, say so.
3. **Milestone close is high-stakes.** It runs gate checks before mutating: security audit + hardening on every milestone, and design audit + Core Web Vitals for UI milestones only (a milestone with no `ui_component`/`ui_page` work order is not required to produce a `website:critique` design audit). Always preview gate status before mutating and require explicit user approval for `--force`.
4. **Errors are operator-visible.** When a function returns `ok=False`, surface the `error` field verbatim. List the `failures` or `open_work_orders` exactly as returned.
5. **No raw UUIDs to the user unless asked.** Refer to milestones by `title` in conversation; use the ID internally.

<!-- Last reviewed 2026-06-20 — WO-P20-CLOSE-LAG (fix/wo-p20-close-lag): core/milestones/close.py close_milestone() now calls sync_tick() after emitting the milestone.completed spool event so business_milestones.status reflects 'complete' immediately — callers no longer need a manual flush. No skill-surface, mode, routing, or gate behavior change — close mode still calls close_milestone(). -->

<!-- Reviewed 2026-07-05 — WO 6d978483 (PEP 585/604 modernization [2/2]): source files in this domain received mechanical type-annotation modernization only (PEP 585 builtin generics, PEP 604 unions, datetime.UTC) via ruff UP safe autofixes. No contract, behavior, schema, routing, API-shape, or CLI-surface change — reviewed, no doc content change needed. -->

<!-- Reviewed 2026-07-23 — WO-FILESDB-P3 S3b-2 (feat/milestone-gate-docstore-reader): the four close gate checks (design-audit / security-audit / harden-results / cwv-results) now read their artifacts via core.milestones.artifacts.read_milestone_artifact — the files.db docstore first (name 'milestones/<id>/<file>'), disk-fallback during the .planning→docstore transition. Same four gate checks, same pass/fail semantics; only the artifact READ path moved. No skill-surface, mode, routing, or gate-behavior change — close mode still calls close_milestone(). -->

<!-- Reviewed 2026-07-23 — WO 05fc434d (fix/milestone-close-deleted-terminal): core/milestones/close.py::close_milestone open-WO precondition now treats "deleted" as terminal alongside "closed"/"cancelled" (_TERMINAL_WO_STATUSES). A work order retired via a work_order.deleted event (status='deleted') is removed, not outstanding, so it must not block milestone close — the open-WO check is a hard precondition (not force-bypassable), so the terminal set must be complete. Surfaced closing the Files-in-Database milestone (a deleted stale-advisory WO blocked it). Same close flow + gate sequence; only the open-WO terminal-status set widened. No ds-milestone mode, routing keyword, or CLI-surface change — close mode still calls close_milestone(). -->

<!-- Reviewed 2026-08-08 — WO-GATE-HAS-UI (Platform Gate Corrections): core/milestones/close.py::_evaluate_milestone_artifacts CHECK 1 (design audit) is now has_ui-aware — a non-UI infrastructure milestone (no ui_component/ui_page WO) is no longer REQUIRED to produce a website:critique design-audit.md, mirroring the existing Core Web Vitals check. A design-audit present on any milestone still has its Score: N/M >= 3 bar enforced; security-audit + harden-results stay universal. core/milestones/queries.py get_milestone_status open_gate_checks preview drops design_audit for non-UI milestones to match. close/main SKILL.md gate list updated (design audit is UI-only). No ds-milestone mode, routing keyword, or CLI-surface change — close mode still calls close_milestone(); status mode still calls get_milestone_status(). -->


<!-- Reviewed 2026-08-05 — WO 4d495283 / P3 (feat/prd-rescore-engine): additive read-path param only, NO milestone-surface change. core/milestones/artifacts.py::read_milestone_artifact gains an OPTIONAL db_path keyword so the PRD+SOW rescore engine (core/prd/) and isolated tests can read a non-default files.db docstore; default db_path=None preserves the exact existing behavior, and the milestone close gates still read their artifacts through the same helper unchanged. No ds-milestone mode, routing keyword, CLI surface, or close/gate-behavior change — close mode still calls close_milestone(). -->

<!-- Reviewed 2026-08-05 — WO 742c84f8 / P4 (feat/prd-cli-and-autorefresh): core/milestones/close.py::close_milestone gains a best-effort PRD+SOW auto-refresh on its SUCCESS path (after sync_tick, before return): it calls core/prd/rescore.py::rescore_prd for the milestone's project so the derived PRD+Statement-of-Work living document (docstore prd/prd-sow.md) reflects the just-completed milestone. Wrapped in try/except and swallowed (SPEC-0001 R12) — it can NEVER block, fail, or change the outcome of a milestone close; the returned result dict is unchanged. No new gate, no ds-milestone mode/routing/CLI-surface change, no studio.db table. The refresh is also runnable on demand via the new `ds prd rescore` / `ds prd show` command group (interfaces/cli/commands/prd.py). -->

<!-- Reviewed 2026-08-08 — WO-SECGATE-BLOCKED-TOKEN (Gate & CI Hardening): core/milestones/close.py CHECK 2 (security audit) now flags a BLOCKED *finding marker* via the shared core/gates/security_verdict.py::is_security_blocked, not a naive `"BLOCKED" in text` substring — so an honest "No BLOCKED findings" / "0 BLOCKED" summary no longer false-fails the gate (it blocked the Attribution Coherence milestone close). close mode gate list updated (item 3). No ds-milestone mode, routing keyword, or CLI-surface change — close mode still calls close_milestone(); same gate, sharper predicate. -->
