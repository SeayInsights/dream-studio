---
name: ds-workflow
description: 'Observability, session management, and shared hook infrastructure. Use for: workflow:, run workflow:, idea-to-pr:, studio-onboard:, feature-research:, start workflow:'
---

# Workflow — YAML Pipeline Orchestration

## Output Contract

Workflow execution state: a workflow key printed by `start`, then per-node status
(`pending` / `running` / `completed` / `skipped` / `unverified` / `blocked` / `failed`)
visible through `status`/`list`, and an overall run status (`running` / `completed` /
`completed_with_failures` / `completed_with_unverified` / `blocked`) printed by
`advance`/`run`. No separate report file — the state lives in
`~/.dream-studio/state/workflows.json`, keyed by the workflow key.

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## The real command surface

`ds workflow` has exactly five subcommands — read directly off
`interfaces/cli/ds_workflow.py`'s argparse definitions, not assumed:

| Subcommand | What it actually does |
|---|---|
| `start <yaml-path> [--name NAME] [--work-order ID]` | Initializes workflow state and prints the workflow key as the first line of stdout, e.g. `idea-to-pr-1713456000`. If a non-terminal workflow with the same `--name` (or YAML stem) is already running, **resumes it instead** — prints the same key plus `... resumed — X/Y nodes already complete`. This is also how you resume after a session break — there is no separate `resume` subcommand. |
| `status [KEY]` | With a key: one summary line plus a per-node line (status, a 60-character preview of its recorded output, duration, and `[dispatched, not executed]` where that applies). Without a key: one line per active workflow. |
| `list` | Today, identical to `status` with no key. |
| `advance <KEY> [--dry-run]` | Executes exactly one wave of ready nodes and returns. Prints `[workflow] executed: <id>, <id>, ...` or `[workflow] no nodes ready (workflow may be done or blocked)`. |
| `run <KEY> [--dry-run]` | Loops the same wave logic internally until the workflow is blocked, still has nodes running, or is done. Prints `[workflow] final status: <status>`. |

There is **no** `next`, `eval`, `update`, `pause`, `resume`, or `abort` subcommand
under `ds workflow` — do not try to call them. (A lower-level module,
`control.execution.workflow.state`, implements those verbs as its own direct CLI,
`py -m control.execution.workflow.state <cmd>`, but `ds workflow` never calls into
it for anything except the state read/write that backs `start`/`status`, so they are
not part of the surface this skill drives.)

## Trigger
`workflow: <name>`, `workflow list`, `workflow status`

## Discovery — no name given

If the user invokes `/workflow` with no workflow name (or types just `workflow` or `workflow list`):

1. List workflow templates from project `.workflows/` first, then plugin `workflows/`. Display each template's filename, `name`, and `description` fields from YAML.
2. Then stop — do not proceed to execution.

The registry auto-discovers all `*.yaml` files in `../../workflows/` including any you just added.

## Validate before you start

`ds workflow start` does **not** validate the YAML — it only extracts node ids to
seed state, and will happily start a workflow with a dependency cycle, a `gate:`
that isn't declared under `gates:`, or a `skill:` that resolves to no `SKILL.md`.
Catch that first:

```
py -m control.execution.workflow.validate <yaml-path>
```

Exits 0 and prints `OK: <path> — N nodes, G gates` when clean; exits 1 and prints
one `FAIL:` line per problem otherwise. Fix and re-run before `ds workflow start`.

---

## Execution Protocol

### Step 1 — Start

```
ds workflow start <yaml-path> --name <name> [--work-order <id>]
```

Capture the printed key from the first line of output — every subsequent command
needs it.

### Step 2 — Advance one wave at a time

```
ds workflow advance <key>
```

A single `advance` call does all of this itself, before it returns:

1. Computes every `pending` node whose dependencies are satisfied for its
   `trigger_rule`: `all_success` (default, deps `completed` or `unverified`),
   `all_done` (deps `completed`/`failed`/`skipped`/`unverified`), or `one_success`
   (any dep `completed`).
2. For each such node with a `condition:`, evaluates it itself and marks a
   condition-false node `skipped`. Conditions only support `== != > < >= <=`
   against `{{node_id.field}}`/`{{workflow.key}}` references (`==`/`!=` also treat
   a colon-delimited prefix as a match, so `{{node.output}} == BLOCKED` matches an
   output of `BLOCKED: 2 findings`) — there is **no** `contains` operator, whatever
   an individual workflow's YAML comments might suggest. There is no separate
   `eval` step and nothing for you to mark `skipped` yourself; this has already
   happened by the time `advance` returns.
3. **Dispatches — does not execute** — every node still ready: it loads the
   target `skill:`'s `SKILL.md` content, or the node's `command:` prompt, and
   records that text on the node. It never spawns an agent. Every dispatch's
   recorded output starts with the runner's own header: "NOT EXECUTED. This node
   was DISPATCHED, not run ... An agent reading this output performs the work."
   **You are that agent.** Read the node's `skill:`/`command:` field from the
   YAML (or the truncated preview from `status`) and go do what it says, exactly
   as if you had been told to run that skill directly.
4. If the node declares a `completion_check`, runs it **immediately, in this same
   call** — not on some later call, so only a check that can already be true the
   instant the node is dispatched makes sense (inspecting what an *earlier* node
   produced, or that a resource is reachable at all — the shipped
   `execute-work-orders.yaml` is explicit that its own checks are "the weakest
   honest check", e.g. confirming a task list is *readable*, not that every task
   is *done*). Records `completed` (check passed), `blocked` (check failed,
   errored, or timed out), or, when no `completion_check` is declared,
   `unverified`. `unverified` is not a failure — it still satisfies
   `all_success`/`all_done` dependents, so the workflow keeps moving; it only
   means nothing but you attests the work happened. `blocked` is a hard stop:
   nothing under `ds workflow` re-attempts a blocked node or its dependents, so
   never give a node a `completion_check` for the work its *own* dispatch is
   asking you to go do — that check will run before you've done anything and the
   node will block itself immediately, permanently.

Repeat: do the dispatched node's real work, then call `advance` again to pick up
the next wave. Use `ds workflow status <key>` any time to see where things stand.

### Step 3 — Gates are not enforced

A node's `gate:` field is validated at YAML-authoring time (it must name
something declared under the workflow's `gates:` section) but **`advance`/`run`
never read it** — nothing pauses execution for a gate, whatever the gate's
declared `type` (`pause`, `conditional`, ...) says. If a node needs Director
sign-off before the workflow continues, that discipline is entirely on you:
dispatch the node, then stop and ask before doing its work or calling `advance`
again. There is no `pause`/`resume` subcommand to enforce this mechanically.

The same is true of `retry:` and `timeout_seconds:` — both are validated as
well-formed but neither is enforced by the runner. A failed or blocked node is
never automatically retried or timed out; if you want to redo one, you must redo
the work yourself (there is no `ds workflow` command to reset a node back to
`pending`).

### Step 4 — Run to completion, when that's actually appropriate

```
ds workflow run <key>
```

loops Step 2 with **no pause in between waves** until the workflow is blocked,
still has nodes `running`, or is done. That makes it the right tool for a
`--dry-run` preview of the whole graph (a dry run auto-completes every node with
no dispatch at all — nothing is ever loaded or checked) or for a workflow made
entirely of command nodes with real, externally-observable `completion_check`s.
It is the wrong tool for an ordinary pipeline whose nodes need you to actually do
work between waves — every skill/command node dispatched during one `run` call
happens back-to-back with no chance for you to act on it before the next wave is
computed. Use `advance` one wave at a time for that case.

`run` prints `[workflow] final status: <status>` — one of `completed`,
`completed_with_failures`, `completed_with_unverified`, `blocked`, `running` — and,
for `blocked`, a `waiting on:` block naming the stuck node(s) and why; for
`completed_with_unverified`, the list of nodes nobody ever confirmed.

### Step 5 — Complete

When `advance`/`run`/`status` shows the workflow `completed` (read the
`completed_with_unverified` node list before treating that variant as fully done),
trigger `ds-core recap`.

---

## Detailed Reference

See `examples.md` in this directory for node-type reference, specialist dispatch,
the condition/output-contract convention used inside `command:` prompts, and the
built-in `repo-ingest` workflow.
