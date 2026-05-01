# Workflow — YAML Pipeline Orchestration

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Progressive disclosure check
Before executing any workflow command, check if the workflow skill is available:
```python
py "../../hooks/lib/skill_calibration.py" check-mode workflow workflow "<user-message>"
```
If exit code is non-zero, the mode is locked. Show the unlock message (from stdout) and stop.
If exit code is zero, continue. If unlock notifications are printed, show them to the user.

## Trigger
`workflow: <name>`, `workflow list`, `workflow status`, `workflow resume`, `workflow abort`

## Discovery — no name given

If the user invokes `/workflow` with no workflow name (or types just `workflow` or `workflow list`):

1. Run the registry CLI and display its output:
   ```
   py "../../hooks/lib/workflow_registry.py"
   ```
   This prints a live table: Name, Description, Est. Tokens, Last Run, Run count.
2. Then stop — do not proceed to execution.

The registry auto-discovers all `*.yaml` files in `../../workflows/` including any you just added.

## CLI Tools

All state management and validation runs through scripts at the plugin root. Resolve the plugin root from where you loaded this skill (two directories up from `skills/workflow/`).

```
PLUGIN=<plugin-root>

# Validate YAML before execution
py "../../hooks/lib/workflow_validate.py" <yaml-path>

# State management (each returns structured output)
py "../../hooks/lib/workflow_state.py" start <name> <yaml-path>
py "../../hooks/lib/workflow_state.py" update <key> <node-id> <status> [--output TEXT] [--duration SECS]
py "../../hooks/lib/workflow_state.py" pause <key> <node-id> <gate-name>
py "../../hooks/lib/workflow_state.py" resume <key>
py "../../hooks/lib/workflow_state.py" abort <key>
py "../../hooks/lib/workflow_state.py" status [<key>]
py "../../hooks/lib/workflow_state.py" eval <key> "<expression>"
py "../../hooks/lib/workflow_state.py" next <key>
```

---

## Execution Protocol

### `workflow: <name>`

#### Step 1 — Find and validate

1. Look for `<name>.yaml` in project `.workflows/` first, then plugin `workflows/`
2. Run the validator: `py "../../hooks/lib/workflow_validate.py" <yaml-path>`
3. If it exits non-zero → show errors to Director, stop

#### Step 2 — Initialize state

1. Run: `py "../../hooks/lib/workflow_state.py" start <name> <yaml-path>`
2. Capture the workflow key from the first line of output (e.g., `idea-to-pr-1713456000`)
3. Save the key — every subsequent command uses it

#### Step 3 — Execution loop

**Do not manually plan waves.** Use the `next` command — it reads state + YAML, applies trigger rules, and returns exactly which nodes are ready:

```
py "../../hooks/lib/workflow_state.py" next <key>
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
py "../../hooks/lib/workflow_state.py" eval <key> "<condition>"
```
Exit 1 (false) → skip it:
```
py "../../hooks/lib/workflow_state.py" update <key> <node-id> skipped
```
Then call `next` again — skipping a node may unblock others.

**3b. Gate check**

If the node has a `gate`, look up the gate definition in the YAML:

- **`pause`** type → pause and ask Director:
  ```
  py "../../hooks/lib/workflow_state.py" pause <key> <node-id> <gate-name>
  ```
  Print the gate status. Stop. Wait for `workflow resume`.

- **`conditional`** type → evaluate:

## Detailed Reference

See `examples.md` in this directory for detailed steps, schemas, templates, and integration points.
