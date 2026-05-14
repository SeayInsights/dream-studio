# Workflow — YAML Pipeline Orchestration

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Progressive disclosure check
Before executing any workflow command, apply the portable skill contract. If a current calibration interface is available in this checkout, use it; otherwise rely on this workflow contract and the available workflow templates. If workflow execution support is unavailable, report that as future implementation work instead of calling retired helper paths.

## Trigger
`workflow: <name>`, `workflow list`, `workflow status`, `workflow resume`, `workflow abort`

## Discovery — no name given

If the user invokes `/workflow` with no workflow name (or types just `workflow` or `workflow list`):

1. List workflow templates from project `.workflows/` first, then plugin `workflows/`. If a maintained registry CLI is available in this checkout, use it; otherwise display the template filename, `name`, and `description` fields from YAML.
2. Then stop — do not proceed to execution.

The registry auto-discovers all `*.yaml` files in `../../workflows/` including any you just added.

## Execution Support

Workflow templates are portable Dream Studio primitives. A workflow runner must implement the workflow contract in `docs/contracts/workflow-contract.md`, including validation, state transitions, gates, artifacts, stop conditions, and event emissions. If no maintained runner is available in this checkout, do not execute the workflow; validate the YAML shape by inspection, explain the missing runner, and stop.

---

## Execution Protocol

### `workflow: <name>`

#### Step 1 — Find and validate

1. Look for `<name>.yaml` in project `.workflows/` first, then plugin `workflows/`
2. Validate the YAML against the workflow contract using the maintained runner/validator if available; otherwise check required fields by inspection.
3. If it exits non-zero → show errors to Director, stop

#### Step 2 — Initialize state

1. Initialize workflow state through the maintained workflow runner.
2. Capture the workflow key from the first line of output (e.g., `idea-to-pr-1713456000`)
3. Save the key — every subsequent command uses it

#### Step 3 — Execution loop

**Do not manually plan waves.** Use the `next` command — it reads state + YAML, applies trigger rules, and returns exactly which nodes are ready:

```
<maintained-runner> next <key>
```

Output tells you what to do:
- `ready: think` → one node to execute
- `ready: review-code, review-security, ...` + `(parallel)` → dispatch simultaneously
- `paused: plan (gate: director-approval)` → waiting for Director
- `waiting: review-code still running` → agents haven't finished
- `done` → workflow complete

**For each ready node:**

**3a. Condition check** — if `next` shows `condition=...` on a node, evaluate it:
```
<maintained-runner> eval <key> "<condition>"
```
Exit 1 (false) → skip it:
```
<maintained-runner> update <key> <node-id> skipped
```
Then call `next` again — skipping a node may unblock others.

**3b. Gate check**

If the node has a `gate`, look up the gate definition in the YAML:

- **`pause`** type → pause and ask Director:
  ```
  <maintained-runner> pause <key> <node-id> <gate-name>
  ```
  Print the gate status. Stop. Wait for `workflow resume`.

- **`conditional`** type → evaluate:

## Detailed Reference

See `examples.md` in this directory for detailed steps, schemas, templates, and integration points.
