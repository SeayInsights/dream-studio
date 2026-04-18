---
name: workflow
description: YAML workflow orchestration — parse DAG definitions, resolve dependencies, execute nodes through existing skills with gates, parallel spawning, and state tracking. Trigger on `workflow:`, `workflow status`, `workflow resume`, `workflow abort`.
---

# Workflow — YAML Pipeline Orchestration

## Trigger
`workflow: <name>`, `workflow status`, `workflow resume`, `workflow abort`

## DCL Commands

| Command | Action |
|---|---|
| `workflow: <name>` | Load and execute the named workflow |
| `workflow status` | Print current workflow state from `workflows.json` |
| `workflow resume` | Resume a paused workflow after gate approval |
| `workflow abort` | Cancel the active workflow, mark all pending nodes as `skipped` |

---

## YAML Schema Reference

Workflow files live in `workflows/` at the plugin root. Per-project overrides go in `.workflows/` at the project root (project files take precedence).

```yaml
name: string          # Unique workflow identifier
description: string   # Human-readable purpose
version: number       # Schema version (currently 1)

gates:                # Named gate policies
  <gate-name>:
    type: pause | conditional | skip
    condition: string       # For conditional type — expression to evaluate
    requires: [string]      # For evidence-required — artifact types that must exist
    prompt: string          # For pause type — message shown to Director

nodes:                # Ordered list of execution steps
  - id: string              # Unique node identifier (required)
    skill: string           # Skill to invoke (from skills/ directory)
    command: string          # Inline instruction (if no skill)
    depends_on: [string]    # Node IDs that must complete first
    gate: string            # Gate policy name (from gates section)
    model: opus | sonnet | haiku
    context: fresh | inherit  # fresh = new agent, inherit = continue session
    agent: string           # Agent persona (engineering, game, client)
    trigger_rule: string    # all_success (default), all_done, one_success
    condition: string       # Expression — node only runs if true
    input: string           # Template referencing prior node outputs: {{node-id.output}}
    config: object          # Skill-specific configuration passed to agent
    retry: number           # Max retries before escalation (default: 3)
    isolation: shared | worktree  # Git isolation strategy (default: shared)
```

**Exactly one of `skill` or `command` must be set per node.**

---

## Workflow Execution Protocol

When Chief-of-Staff receives `workflow: <name>`:

### Phase 1: Load and validate

1. Search for `<name>.yaml` in project `.workflows/` first, then plugin `workflows/`
2. Parse the YAML file — extract `name`, `gates`, and `nodes`
3. Validate:
   - Every node has a unique `id`
   - Every `depends_on` reference points to an existing node `id`
   - Every `gate` reference points to a defined gate in the `gates` section
   - Every `skill` reference corresponds to an existing skill directory
   - No circular dependencies exist
4. If validation fails → report errors to Director and stop

### Phase 2: Build dependency graph (DAG)

1. Construct a directed acyclic graph from `depends_on` edges
2. Topologically sort nodes into execution waves:
   - **Wave 1:** Nodes with no `depends_on` (roots)
   - **Wave N:** Nodes whose dependencies are all in earlier waves
3. Within each wave, identify parallelizable groups:
   - Nodes with `skill` only (read-only like `review`, `secure`) → share main working tree
   - Nodes with `command` or write-capable skills (`build`) touching different files → parallel in worktrees if `isolation: worktree`
   - Nodes touching the same files → must be sequential within the wave

### Phase 3: Execute nodes wave by wave

For each wave, for each node:

#### 3a. Check preconditions
- **`depends_on`**: All listed nodes must have completed (or match `trigger_rule`)
- **`condition`**: Evaluate expression against prior node outputs. If false → mark node `skipped`
- **`trigger_rule`**:
  - `all_success` (default): All deps must have status `completed`
  - `all_done`: All deps must have status `completed` or `failed` (runs regardless of dep outcome)
  - `one_success`: At least one dep must have status `completed`

#### 3b. Pre-gate check
If the node has a `gate`, evaluate it **before** execution:
- **`pause`**: Stop execution. Report workflow status to Director. Wait for `workflow resume`.
- **`conditional`**: Evaluate the condition expression. If true → continue. If false → fall back to `pause`.
- **`skip`**: Gate is disabled, continue execution.
- **Evidence-required (`pause` with `requires`)**: Check for required artifacts. If all exist → auto-continue. If missing → pause for Director.

When paused at a gate, print:
```
[workflow] <name> — PAUSED at gate "<gate-name>" on node "<node-id>"
  Completed: N/M nodes
  Gate requires: <condition or artifacts>
  → Use `workflow resume` to continue, `workflow abort` to cancel
```

#### 3c. Execute node

**If node has `skill`:**
1. Resolve the skill path: `skills/<skill-name>/SKILL.md`
2. Determine the agent: use `agent` field if set, otherwise execute in main session
3. Set model: use `model` field if set, otherwise follow `director-preferences.md` routing
4. Resolve `input` template: replace `{{node-id.output}}` with the referenced node's output value from workflow state
5. Spawn agent with:
   - Skill content (read from skill path)
   - `director-preferences.md`
   - Input context from `input` field
   - Skill-specific `config` if present
   - `context: fresh` → new agent via Task tool; `context: inherit` → continue in current session

**If node has `command`:**
1. Execute the inline instruction in the current session (or a fresh agent if `context: fresh`)
2. The command text is the full prompt — no skill injection needed

**For parallel nodes within a wave:**
- Spawn all eligible nodes simultaneously via Task tool
- Each parallel node gets its own agent (fresh context)
- Read-only nodes share the working tree
- Write nodes get worktrees if `isolation: worktree` is set
- For parallel review nodes: each agent writes findings to `review-{node-id}-findings.md`

#### 3d. Handle node result

Each node produces a result with:
- **status**: `completed`, `failed`, or `blocked`
- **output**: Summary string or file path (stored in workflow state)
- **duration_s**: Execution time in seconds

On completion:
1. Update workflow state via `on-workflow-progress` hook (automatic on Stop)
2. If node `failed` and `retry` > 0 → re-execute with retry count decremented
3. If node `failed` and retries exhausted → escalate to Director with full context
4. Print progress: `[workflow] <name> — Node <id> COMPLETED (N/M nodes done)`

### Phase 4: Workflow completion

When all nodes are done (completed, skipped, or failed):
1. Print final summary with per-node status and durations
2. Update workflow state to `completed` or `completed_with_failures`
3. Trigger `skills/studio/recap` automatically

---

## State Reporting Format

After each node completes, report:

```
[workflow] <name> — Node <id> <STATUS> (N/M nodes done)
  Duration: Xs
  Output: <summary or path>
  Next: <list of now-unblocked nodes or "waiting for <deps>">
  Gates pending: <gate names or "none">
```

---

## Error and Retry Protocol

1. **Node failure**: If a node's agent reports `BLOCKED` or fails:
   - Check `retry` count (default: 3)
   - If retries remain: re-spawn with the same context + error details from the failed attempt
   - On retry, upgrade model if the failure suggests capability limitations (haiku → sonnet → opus)
   - If all retries exhausted: mark node `failed`, report to Director, pause workflow

2. **Dependency failure**: If a required dependency failed:
   - `all_success` trigger rule: mark dependent node `skipped`
   - `all_done` trigger rule: execute dependent node anyway (it can read the failure)
   - `one_success` trigger rule: execute if at least one dep succeeded

3. **Workflow abort**: On `workflow abort`:
   - Mark all `pending` and `running` nodes as `skipped`
   - Mark workflow status as `aborted`
   - Report final state

---

## Template Variables

Nodes can reference outputs from prior nodes using `{{node-id.output}}` and `{{node-id.status}}` in their `input` and `condition` fields.

Resolution:
1. Look up the referenced node in workflow state
2. Replace the template with the node's stored `output` or `status` value
3. If the referenced node hasn't run yet → validation error (caught in Phase 1)

---

## Parallel Execution Safety

Before spawning parallel nodes, verify:
1. No two parallel nodes modify the same files (check skill type + config)
2. Read-only skills (`review`, `secure`) are safe to parallelize on shared tree
3. Write skills in parallel require `isolation: worktree` or explicit file-disjointness
4. When in doubt, run sequentially — correctness over speed

---

## Per-Project Overrides

Projects can override plugin-bundled workflows:
1. Create `.workflows/<name>.yaml` in the project root
2. Project file completely replaces the plugin version (no merging)
3. This allows teams to customize gate policies, add/remove nodes, or adjust model routing
