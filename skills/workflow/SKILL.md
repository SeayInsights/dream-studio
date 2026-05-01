---
name: workflow
model_tier: sonnet
description: YAML workflow orchestration — validate, execute DAG nodes through existing skills with gates and parallel spawning, track state via CLI. Trigger on `workflow:`, `workflow status`, `workflow resume`, `workflow abort`.
pack: meta
---

# Workflow — YAML Pipeline Orchestration

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Trigger
`workflow: <name>`, `workflow list`, `workflow status`, `workflow resume`, `workflow abort`

## Discovery — no name given

If the user invokes `/workflow` with no workflow name (or types just `workflow` or `workflow list`):

1. Run the registry CLI and display its output:
   ```
   py "$PLUGIN/hooks/lib/workflow_registry.py"
   ```
   This prints a live table: Name, Description, Est. Tokens, Last Run, Run count.
2. Then stop — do not proceed to execution.

The registry auto-discovers all `*.yaml` files in `$PLUGIN/workflows/` including any you just added.

## CLI Tools

All state management and validation runs through scripts at the plugin root. Resolve the plugin root from where you loaded this skill (two directories up from `skills/workflow/`).

```
PLUGIN=<plugin-root>

# Validate YAML before execution
py "$PLUGIN/hooks/lib/workflow_validate.py" <yaml-path>

# State management (each returns structured output)
py "$PLUGIN/hooks/lib/workflow_state.py" start <name> <yaml-path>
py "$PLUGIN/hooks/lib/workflow_state.py" update <key> <node-id> <status> [--output TEXT] [--duration SECS]
py "$PLUGIN/hooks/lib/workflow_state.py" pause <key> <node-id> <gate-name>
py "$PLUGIN/hooks/lib/workflow_state.py" resume <key>
py "$PLUGIN/hooks/lib/workflow_state.py" abort <key>
py "$PLUGIN/hooks/lib/workflow_state.py" status [<key>]
py "$PLUGIN/hooks/lib/workflow_state.py" eval <key> "<expression>"
py "$PLUGIN/hooks/lib/workflow_state.py" next <key>
```

---

## Execution Protocol

### `workflow: <name>`

#### Step 1 — Find and validate

1. Look for `<name>.yaml` in project `.workflows/` first, then plugin `workflows/`
2. Run the validator: `py "$PLUGIN/hooks/lib/workflow_validate.py" <yaml-path>`
3. If it exits non-zero → show errors to Director, stop

#### Step 2 — Initialize state

1. Run: `py "$PLUGIN/hooks/lib/workflow_state.py" start <name> <yaml-path>`
2. Capture the workflow key from the first line of output (e.g., `idea-to-pr-1713456000`)
3. Save the key — every subsequent command uses it

#### Step 3 — Execution loop

**Do not manually plan waves.** Use the `next` command — it reads state + YAML, applies trigger rules, and returns exactly which nodes are ready:

```
py "$PLUGIN/hooks/lib/workflow_state.py" next <key>
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
py "$PLUGIN/hooks/lib/workflow_state.py" eval <key> "<condition>"
```
Exit 1 (false) → skip it:
```
py "$PLUGIN/hooks/lib/workflow_state.py" update <key> <node-id> skipped
```
Then call `next` again — skipping a node may unblock others.

**3b. Gate check**

If the node has a `gate`, look up the gate definition in the YAML:

- **`pause`** type → pause and ask Director:
  ```
  py "$PLUGIN/hooks/lib/workflow_state.py" pause <key> <node-id> <gate-name>
  ```
  Print the gate status. Stop. Wait for `workflow resume`.

- **`conditional`** type → evaluate:

## Detailed Reference

See `examples.md` in this directory for detailed steps, schemas, templates, and integration points.
