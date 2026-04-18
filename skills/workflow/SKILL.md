---
name: workflow
description: YAML workflow orchestration — validate, execute DAG nodes through existing skills with gates and parallel spawning, track state via CLI. Trigger on `workflow:`, `workflow status`, `workflow resume`, `workflow abort`.
---

# Workflow — YAML Pipeline Orchestration

## Trigger
`workflow: <name>`, `workflow status`, `workflow resume`, `workflow abort`

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

#### Step 3 — Plan waves

Read the YAML. Group nodes by `depends_on`:
- **Wave 1:** Nodes with no `depends_on`
- **Wave N:** Nodes whose deps all resolved in earlier waves

Within a wave, parallel rules:
- `review`/`secure` skill nodes → read-only, share working tree, safe to parallelize
- `build` skill nodes → need `isolation: worktree` if running parallel
- When unsure → run sequentially

#### Step 4 — Execute wave by wave

For each node in the current wave:

**4a. Check preconditions**

If the node has `depends_on`, check the trigger rule:
- `all_success` (default): all deps must be `completed`
- `all_done`: all deps must be `completed` or `failed`
- `one_success`: at least one dep `completed`

If the node has `condition`, evaluate it:
```
py "$PLUGIN/hooks/lib/workflow_state.py" eval <key> "<condition>"
```
If exit code 1 (false) → skip the node:
```
py "$PLUGIN/hooks/lib/workflow_state.py" update <key> <node-id> skipped
```

**4b. Gate check**

If the node has a `gate`, look up the gate definition in the YAML:

- **`pause`** type → pause and ask Director:
  ```
  py "$PLUGIN/hooks/lib/workflow_state.py" pause <key> <node-id> <gate-name>
  ```
  Print the gate status. Stop. Wait for `workflow resume`.

- **`conditional`** type → evaluate:
  ```
  py "$PLUGIN/hooks/lib/workflow_state.py" eval <key> "<gate-condition>"
  ```
  If true → continue. If false → fall back to pause behavior.

- **`pause` with `requires`** → check artifacts exist (screenshots in `.verify/`, test output). If all present → continue. If missing → pause.

**4c. Run the node**

Mark running:
```
py "$PLUGIN/hooks/lib/workflow_state.py" update <key> <node-id> running
```

**Skill node:**
1. Read `skills/<skill-name>/SKILL.md`
2. Resolve `input` field: for `{{node-id.output}}`, read the output from `workflow_state.py status <key>` or from your memory of prior node results
3. Spawn agent via Task tool with: skill content + `director-preferences.md` + resolved input + `config`
4. Set `model` from node. Use `agent` field for persona if set.
5. `context: fresh` (default) → new agent. `context: inherit` → current session.

**Command node:**
1. The `command` text is the full prompt
2. `context: fresh` → spawn as new agent. Otherwise current session.

**For parallel review/secure nodes:** include in each agent's prompt:
> "Write your complete findings to `review-<node-id>-findings.md` in the project root."

After the agent returns, verify the file exists. If not, write the agent's response to that file yourself. This ensures synthesize can find all review outputs.

**4d. Record result**

```
py "$PLUGIN/hooks/lib/workflow_state.py" update <key> <node-id> completed --output "<summary>" --duration <seconds>
```

Or on failure:
```
py "$PLUGIN/hooks/lib/workflow_state.py" update <key> <node-id> failed --output "<error>"
```

On failure: retry up to 3 times (or node's `retry` value). Upgrade model each retry (haiku→sonnet→opus). After exhaustion → pause workflow, escalate to Director.

#### Step 5 — Complete

When all nodes are done, run `workflow_state.py status <key>` to print the final summary. Then trigger `skills/studio/recap`.

---

### `workflow status`

```
py "$PLUGIN/hooks/lib/workflow_state.py" status [<key>]
```
Print the output. If no key given, shows all workflows.

### `workflow resume`

1. Find the active paused workflow key from `workflow_state.py status`
2. Run: `py "$PLUGIN/hooks/lib/workflow_state.py" resume <key>`
3. Continue execution from the paused node

### `workflow abort`

```
py "$PLUGIN/hooks/lib/workflow_state.py" abort <key>
```

---

## Error Handling

**Node failure:** Retry up to 3× with model upgrade. After exhaustion → `update <key> <node-id> failed`, pause workflow, tell Director.

**Dependency failure by trigger rule:**
- `all_success` → skip the dependent node
- `all_done` → run it anyway
- `one_success` → run if any dep succeeded
