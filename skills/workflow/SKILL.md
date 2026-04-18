---
name: workflow
description: YAML workflow orchestration — read DAG definitions from workflows/*.yaml, execute nodes through existing skills with gates and parallel spawning. Trigger on `workflow:`, `workflow status`, `workflow resume`, `workflow abort`.
---

# Workflow — YAML Pipeline Orchestration

## Trigger
`workflow: <name>`, `workflow status`, `workflow resume`, `workflow abort`

## DCL Commands

| Command | Action |
|---|---|
| `workflow: <name>` | Load and execute the named workflow |
| `workflow status` | Read `~/.dream-studio/state/workflows.json`, print per-node status |
| `workflow resume` | Resume a paused workflow after gate approval |
| `workflow abort` | Mark all pending/running nodes `skipped`, set status `aborted` |

---

## Execution Protocol

### Phase 1: Load

1. Find `<name>.yaml` — check project `.workflows/` first, then plugin `workflows/`
2. Read the YAML. Extract `name`, `gates`, and `nodes`.
3. Quick-check: every `depends_on` ID exists as a node `id`, every `gate` name exists in `gates:` section, every `skill` has a matching `skills/<name>/SKILL.md`
4. If anything fails → tell Director what's wrong and stop

### Phase 2: Plan waves

Group nodes into execution waves by `depends_on`:
- **Wave 1:** Nodes with no `depends_on`
- **Wave N:** Nodes whose deps all resolved in earlier waves

Within a wave, nodes run in parallel unless they both write code. Rules:
- `review` and `secure` skill nodes → read-only, share working tree
- `build` skill nodes → use `isolation: worktree` if parallel
- `command` nodes → assume write-capable unless obviously read-only
- When unsure, run sequentially

### Phase 3: Execute wave by wave

Initialize workflow state (see State Management below), then for each wave:

**For each node in the wave:**

#### 3a. Preconditions
- Check `depends_on` against `trigger_rule`:
  - `all_success` (default): every dep status is `completed`
  - `all_done`: every dep is `completed` or `failed`
  - `one_success`: at least one dep is `completed`
- Check `condition`: read the referenced value from workflow state (e.g., `{{synthesize.output}}`). If false → mark `skipped`, move on.

#### 3b. Gate check (before execution)
If node has a `gate`, look up the gate definition:
- **`pause`**: Print status block (below), stop, wait for `workflow resume`
- **`conditional`**: Evaluate condition. True → proceed. False → fall back to `pause`.
- **`pause` with `requires`**: Check for artifacts (screenshots in `.verify/`, test results in recent output). All present → proceed. Missing → pause.
- **`skip`**: No gate, continue.

Gate pause message:
```
[workflow] <name> — PAUSED at gate "<gate-name>" on node "<node-id>"
  Completed: N/M nodes
  Gate requires: <what's needed>
  → `workflow resume` to continue, `workflow abort` to cancel
```

#### 3c. Run the node

**Skill node** — dispatch agent:
1. Read `skills/<skill-name>/SKILL.md`
2. Read the `input` field, replace `{{node-id.output}}` with the stored output from workflow state
3. Spawn via Task tool with: skill content + `director-preferences.md` + resolved input + any `config`
4. Set `model` from the node. Use `agent` field for persona if set.
5. `context: fresh` (default) → new agent. `context: inherit` → current session.
6. **For review/secure nodes in parallel:** include in the agent prompt: "Write your findings to `review-<node-id>-findings.md` in the project root."

**Command node** — execute inline:
1. The `command` text is the full prompt
2. If `context: fresh`, spawn as a new agent. Otherwise run in current session.

**After the node completes:**
1. Update workflow state → set node status to `completed` or `failed`, record output summary and duration
2. If `failed` and retries remain (default 3): re-dispatch, upgrade model on capability failures (haiku→sonnet→opus)
3. If retries exhausted: mark `failed`, pause workflow, escalate to Director

### Phase 4: Completion

When all nodes are done:
1. Print final summary: each node's status, duration, and output
2. Update workflow state → status `completed` or `completed_with_failures`
3. Trigger `skills/studio/recap`

---

## State Management

**You (Chief-of-Staff) own the state file.** The `on-workflow-progress` hook only reads it and prints a status line — it does not write.

State file: `~/.dream-studio/state/workflows.json`

**On workflow start**, read the file (create if missing), add an entry:
```json
{
  "schema_version": 1,
  "active_workflows": {
    "<name>-<unix-timestamp>": {
      "workflow": "<name>",
      "started": "<ISO-8601>",
      "status": "running",
      "current_node": null,
      "nodes": {
        "<node-id>": { "status": "pending" }
      },
      "gates_passed": [],
      "gates_pending": []
    }
  }
}
```

**After each node**, read → update the node entry → write back:
```json
{
  "status": "completed",
  "output": "<summary or file path>",
  "duration_s": 120,
  "started": "<ISO-8601>",
  "finished": "<ISO-8601>"
}
```

Also update `current_node` and `gates_passed`/`gates_pending` as appropriate.

**On pause**, set workflow status to `paused` and add the gate to `gates_pending`.
**On resume**, set status back to `running` and move gate to `gates_passed`.
**On abort**, set all `pending`/`running` nodes to `skipped`, workflow status to `aborted`.

---

## Error Handling

**Node failure:** Retry up to 3 times (or node's `retry` value). Upgrade model on each retry. After exhaustion → mark `failed`, pause workflow, tell Director.

**Dependency failure:**
- `all_success` → skip the dependent node
- `all_done` → run it anyway (it reads the failure context)
- `one_success` → run if any dep succeeded
