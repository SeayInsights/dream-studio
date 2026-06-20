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
3. **Milestone close is high-stakes.** It runs four gate checks (design audit, security audit, hardening, Core Web Vitals for UI milestones). Always preview gate status before mutating and require explicit user approval for `--force`.
4. **Errors are operator-visible.** When a function returns `ok=False`, surface the `error` field verbatim. List the `failures` or `open_work_orders` exactly as returned.
5. **No raw UUIDs to the user unless asked.** Refer to milestones by `title` in conversation; use the ID internally.

<!-- Last reviewed 2026-06-20 — WO-P20-CLOSE-LAG (fix/wo-p20-close-lag): core/milestones/close.py close_milestone() now calls sync_tick() after emitting the milestone.completed spool event so business_milestones.status reflects 'complete' immediately — callers no longer need a manual flush. No skill-surface, mode, routing, or gate behavior change — close mode still calls close_milestone(). -->
