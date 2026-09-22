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

## Creating a milestone

`ds milestone create <project_id> --title ... --description ...`, or
`core.milestones.mutations.create_milestone`. There is no mode for it: creation is a
single call, and the contract below is the whole of what an agent needs.

**`--description` is REQUIRED and is the milestone's PROMPT.** The hierarchy is a prompt
chain — a task is a specific instruction, a work order is the goal those instructions add
up to, a milestone is the goal those work orders add up to. A milestone carrying only a
title gives every work order beneath it nothing to derive its own goal from.

- **DO** say what the milestone is for and what it delivers, in at least 50 characters.
- **DON'T** restate the title. `create_milestone` refuses anything shorter than the floor
  and returns `{"ok": false, "error": "description is required: ..."}` — surface that
  error verbatim, as rule 4 requires, rather than retrying with padding.
- **DO** expect the same refusal one layer down: a work order needs its own prompt
  (60 characters), and a task needs an executable acceptance criterion or a declared
  `--why`.

The floor is measured, not chosen: of the milestones on the authority that carry a
description, the shortest real one is 54 characters, and everything below that was a test
fixture. It refuses an absence, never a style.

---

## Rules that apply to every mode

1. **Read functions before you write.** Every state-surfacing instruction names the specific query function being called. Never describe milestone progress from session context.
2. **Present returned dicts. Don't invent fields.** The functions return dicts with a known shape. Show those fields. If the user asks for a field that isn't there, say so.
3. **Milestone close is high-stakes.** It runs gate checks before mutating: security audit + hardening on every milestone, and design audit + Core Web Vitals for UI milestones only (a milestone with no `ui_component`/`ui_page` work order is not required to produce a `website:critique` design audit). Always preview gate status before mutating and require explicit user approval for `--force`.
4. **Errors are operator-visible.** When a function returns `ok=False`, surface the `error` field verbatim. List the `failures` or `open_work_orders` exactly as returned.
5. **No raw UUIDs to the user unless asked.** Refer to milestones by `title` in conversation; use the ID internally.
