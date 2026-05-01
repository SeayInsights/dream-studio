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
  ```
  py "$PLUGIN/hooks/lib/workflow_state.py" eval <key> "<gate-condition>"
  ```
  If true → continue. If false → fall back to pause behavior.

- **`pause` with `requires`** → check artifacts exist (screenshots in `.verify/`, test output). If all present → continue. If missing → pause.

**3c. Run the node**

Mark running:
```
py "$PLUGIN/hooks/lib/workflow_state.py" update <key> <node-id> running
```

**Skill node:**
1. Read `skills/<skill-name>/SKILL.md`
2. Resolve `input` field: for `{{node-id.output}}`, read the output from `workflow_state.py status <key>` or from your memory of prior node results
3. Spawn agent via Task tool with: skill content + `director-preferences.md` + resolved input
4. Set `model` from node. Use `agent` field for persona if set.
5. `context: fresh` (default) → new agent via Task tool. Pass ONLY the node's input + skill content + config — do NOT paste prior nodes' full output into the prompt. If the new agent needs a prior node's verdict, include just the verdict string, not the full response. `context: inherit` → execute in the current session (all prior context visible).
6. If the node has a `config` block, pass those key-value pairs as additional instructions to the agent prompt (e.g., `focus`, `rules`, `output_contract`).

**Command node:**
1. The `command` text is the full prompt
2. `context: fresh` → spawn as new agent via Task tool (isolated context). `context: inherit` → current session.
3. **Output contract:** The agent's final line of output MUST be one of the standard verdicts (see Output Contract below). Include this instruction in the agent's prompt.

**Specialist node** (`type: specialist` in workflow YAML):

A specialist node dispatches a Claude Code sub-agent from the `~/.claude/agents/` directory.
Specialists are resolved by name against `skills/domains/ingest-log.yml`.

Resolution:
1. Find plugin root (two directories up from skills/workflow/)
2. Read `<plugin-root>/skills/domains/ingest-log.yml`
3. Find entry where `persona_md_path` matches the node's `specialist:` field (by basename or full path)
4. Confirm `~/.claude/agents/<basename>` exists on the local filesystem

Dispatch (agent present):
- Read the agent file from `~/.claude/agents/<basename>`
- Spawn via Task tool: agent file content + node `input` field + any `config` key-values
- Record output and verdict per standard node protocol (3d)

Graceful failure (agent NOT installed):
- Do NOT fail the workflow silently
- Pause the workflow: `workflow_state.py pause <key> <node-id> agent-not-installed`
- Surface the install command to Director:
  `cp <plugin-root>/<persona_md_path> ~/.claude/agents/<basename>`
- Print: "Specialist '<name>' not installed. Install it, then run `workflow resume`."

YAML syntax for a specialist node:
  - id: infra-audit
    type: specialist
    specialist: kubernetes-expert
    depends_on: [plan]
    model: sonnet
    context: fresh
    timeout_seconds: 300
    input: "{{plan.output}}"

Note: `specialist:` names the agent by its ingest-log entry identifier (matches
`repo_name` in ingest-log). Do NOT use the `agent:` field — that field sets a persona
hint for skill nodes and is unrelated to specialist dispatch.

**For parallel review/secure nodes:** include in each agent's prompt:
> "Write your complete findings to `review-<node-id>-findings.md` in the project root. Your final line of output must be exactly PASSED or BLOCKED."

After the agent returns, verify the file exists. If not, write the agent's response to that file yourself. This ensures synthesize can find all review outputs.

**3d. Record result**

Extract the verdict from the agent's output (last non-empty line). If the verdict doesn't match a known value, treat as `UNKNOWN` and pause for Director review.

```
py "$PLUGIN/hooks/lib/workflow_state.py" update <key> <node-id> completed --output "<verdict>: <summary>" --duration <seconds>
```

Or on failure:
```
py "$PLUGIN/hooks/lib/workflow_state.py" update <key> <node-id> failed --output "FAILED: <error>"
```

On failure: retry up to 3 times (or node's `retry` value). Upgrade model each retry (haiku→sonnet→opus). After exhaustion → pause workflow, escalate to Director.

---

## Output Contract

Every workflow node — skill or command — must end its output with a **verdict line**. This is what conditions (`{{node.output}} == BLOCKED`) match against. The verdict is the first word of the `--output` value stored in state.

**Standard verdicts:**

| Verdict | Meaning | Next action |
|---------|---------|-------------|
| `PASSED` | Node completed successfully, no issues | Continue to dependents |
| `BLOCKED` | Critical/high issues found that must be fixed | Trigger fix node or pause |
| `FAILED` | Node could not complete its work | Retry or escalate |
| `SKIPPED` | Node was not applicable (condition false) | Continue, treat as non-blocking |
| `VERIFIED` | Evidence-based confirmation (verify skill) | Continue to ship |
| `UNKNOWN` | Agent didn't produce a clear verdict | Pause for Director review |

**How conditions match:** `{{node.output}} == BLOCKED` checks if the stored output equals `BLOCKED` OR starts with `BLOCKED:` (colon-delimited prefix). So `BLOCKED: 2 critical findings` matches `== BLOCKED`. This is symmetric — the shorter string is always treated as a potential prefix of the longer string. Always store as `VERDICT: detail`.

**Prompt injection for command nodes:** When writing `command:` blocks in workflow YAML, always end the prompt with:
```
Your final output line MUST be exactly one of: PASSED, BLOCKED, FAILED.
Format: VERDICT: one-line summary of what you found.
```

This prevents ambiguous outputs that break condition evaluation.

**3e. Loop** — after recording, call `next` again. Repeat from 3a until `next` returns `done`.

#### Step 4 — Complete

When `next` returns `done`, run `workflow_state.py status <key>` to print the final summary. Then trigger `skills/studio/recap`.

---

### `workflow status`

```
py "$PLUGIN/hooks/lib/workflow_state.py" status [<key>]
```
Print the output. If no key given, shows all workflows.

### `workflow resume`

Works for both gate pauses and session recovery (fresh session picking up a prior workflow):

1. Run `workflow_state.py status` to find the workflow key and current state
2. If paused at a gate: run `workflow_state.py resume <key>` to clear the gate
3. Run `workflow_state.py next <key>` to get the next ready nodes
4. Continue the execution loop from Step 3 of the `workflow:` protocol

You do NOT need the original session context. The state file + YAML have everything: which nodes ran, what they output, what's next. The `next` command does the graph math.

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

---

## Built-in Workflow: `repo-ingest`

### Trigger
`workflow: repo-ingest <url-or-path>`

### Purpose
Formalize external knowledge intake — extract reusable patterns from a repo or resource and write them into the correct `skills/domains/` YAML. Prevents ad-hoc, untracked ingestion.

### 5-Step Process

**Step 1 — Identify domain**
Scan the repo README and top-level structure. Map to a domain from the routing table below.
If no existing domain fits, propose a new one to Director before proceeding.

**Step 2 — Dedup check**
Read the relevant `skills/domains/<domain>/*.yml` file. Grep for key terms from the repo.
If ≥80% of patterns already exist → report "already captured" and stop. Do not create duplicate entries.

**Step 3 — Extract patterns (≤10 per run)**
Read the repo's most authoritative source (README, best-practices doc, or primary config files).
Extract patterns as YAML entries using the existing file's structure as the template.
Rank by: most battle-tested (highest star count / most referenced) first.
Cap at 10 new patterns per ingestion run — prioritize quality over completeness.

**Step 4 — Write to domain YAML**
Append extracted patterns to `skills/domains/<domain>/<file>.yml`.
Preserve existing structure. Do not restructure the file.

**Step 5 — Log the ingestion**
Add an entry to `skills/domains/ingest-log.yml`:
```yaml
- repo_name: "<name>"
  url: "<url>"
  stars: <count>
  domain: "<domain>"
  files_touched:
    - "domains/<domain>/<file>.yml"
  analyzed_date: "<YYYY-MM-DD>"
  refresh_due: "<YYYY-MM-DD>"  # 6 months from analyzed_date
  notes: "<what was extracted, what was skipped>"
```

### Domain Routing Table

| Repo type | Target domain folder |
|-----------|---------------------|
| GitHub Actions, CI/CD, DevOps | `domains/devops/` |
| Testing, E2E, unit testing | `domains/testing/` |
| Technical writing, docs | `domains/documentation/` |
| Power BI, DAX, M-query | `domains/bi/` or `domains/powerbi/` |
| UI design systems, CSS, layout | `domains/design/` |
| Data visualization, charts | `domains/data-visualization/` |
| API patterns, backend | `domains/` (create `backend/` if needed) |
| Security tools, binary analysis | skills/binary-scan or skills/scan SKILL.md directly |
| Planning, spec-driven dev | skills/think or skills/plan templates |

### Anti-bloat Rules
- Never ingest a repo with <100 stars unless it has unique content not found elsewhere
- ≤10 patterns per run — rank by evidence count, take top 10
- Dedup before writing — if the pattern already exists in any form, skip it
- Domain-specific lessons stay in the domain YAML — never promote to core modules
- If the repo is stale (no commits in 1+ year), flag it to Director before ingesting

### Output
- Updated `skills/domains/<domain>/<file>.yml` with new patterns appended
- New entry in `skills/domains/ingest-log.yml`
- Summary to Director: N patterns extracted, M skipped (already existed), refresh due date

## Communication Modes

### Caveman mode
For when AI verbosity is getting in the way — long explanations, summaries of what was just done, preamble before every response.

**Activate:** User says `caveman mode on`
**Deactivate:** User says `caveman mode off`

**In caveman mode:**
- Respond with the action done, nothing else
- No summaries, no "here's what I did", no "let me know if you need anything"
- Status updates only: `done.` / `blocked: [one word reason]` / `need: [one thing]`
- Code and file changes still happen in full — only the prose response is compressed

**When to suggest it:** When the user says the AI is being too wordy, or when the session is deep into execution and explanations add no value.
