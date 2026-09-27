# workflow — Detailed Reference

Extracted from SKILL.md to reduce context injection size.

**None of this is driven through a `next`/`eval`/`update`/`pause` command loop** —
`ds workflow` has no such subcommands (see SKILL.md's "The real command surface").
`ds workflow advance`/`run` compute the ready wave, auto-skip condition-false
nodes, dispatch each ready node, and record its status themselves. What follows
here is what happens on the node's content once it has been dispatched to you —
not a CLI sequence you drive by hand.

**Gates declared in a workflow's `gates:` section (`type: pause`, `requires: [...]`,
etc.) are schema only** — parsed and validated for existence, never read by
`advance`/`run`. There is no engine behavior to describe here: if a node names a
gate, treat that as an instruction to yourself to stop and ask the Director before
doing the node's work, because nothing else will stop for it.

**3c. Do the node's work**

By the time a node is in a wave `advance` reported, its status is already one of
`completed`/`blocked`/`unverified` (or `skipped`/`failed`) — set by the runner
itself as part of dispatching it. There is no `update ... running` call for you to
make; the runner already recorded that transition.

**Skill node:**
1. Read `skills/<skill-name>/SKILL.md`
2. Resolve `input` field: for `{{node-id.output}}`, read the output via `ds workflow status <key>` (a 60-character preview) or from your memory of prior node results.
3. Spawn agent via Task tool with: skill content + `director-preferences.md` + resolved input
4. Set `model` from node. Use `agent` field for persona if set.
5. `context: fresh` (default) → new agent via Task tool. Pass ONLY the node's input + skill content + config — do NOT paste prior nodes' full output into the prompt. If the new agent needs a prior node's verdict, include just the verdict string, not the full response. `context: inherit` → execute in the current session (all prior context visible).
6. If the node has a `config` block, pass those key-value pairs as additional instructions to the agent prompt (e.g., `focus`, `rules`, `output_contract`).

**Command node:**
1. The `command` text is the full prompt
2. `context: fresh` → spawn as new agent via Task tool (isolated context). `context: inherit` → current session.
3. **Output contract:** The agent's final line of output MUST be one of the standard verdicts (see Output Contract below). Include this instruction in the agent's prompt. Know before you do this that the runner itself never reads that line — see the Output Contract section below for why a verdict can only ever be checked through a node's own `completion_check`, never through `{{this-node.output}}`.

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
- Do NOT fail the workflow silently, and do NOT call `ds workflow advance`/`run`
  again until this is resolved — there is no `pause` command to record the reason
  mechanically, so saying it plainly to the Director is the only record there is.
- Surface the install command to Director:
  `cp <plugin-root>/<persona_md_path> ~/.claude/agents/<basename>`
- Print: "Specialist '<name>' not installed. Install it, then re-run `ds workflow advance <key>`."

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

There is no `update` command — you cannot write a verdict onto the node record
yourself. Extract the verdict from the agent's output (last non-empty line)
for your own tracking and for anything downstream that reads it from your
summary, but know that `{{this-node.output}}` inside a later `condition:` will
never see it (see Output Contract below). If the verdict doesn't match a known
value, treat it as `UNKNOWN` and stop for Director review rather than continuing.

On failure: there is no engine-enforced retry (`retry:` is validated, not
enforced — see SKILL.md Step 3). If you choose to retry the work yourself, do so
and note the attempt count; after exhausting the node's declared `retry.max` (or
3 attempts if none is declared), stop and escalate to the Director instead of
continuing the workflow.

---

## Output Contract

Every workflow node — skill or command — should still end its own output with a
**verdict line** (`PASSED`, `BLOCKED`, `FAILED`, ...) for a human or a later node's
`input: "{{this-node.output}}"` reference to read. But be clear about what that
buys you: `{{node.output}} == BLOCKED` is real condition syntax (`_evaluate` in
`control/execution/workflow/engine.py` supports `== != > < >= <=` with
colon-delimited prefix matching, so `BLOCKED: 2 critical findings` matches
`== BLOCKED`), **and it is real for a node that emitted a value through
`resolve_templates`/state (a `command:` node's own recorded field, or another
node's declared output) — but `advance`/`run` never write an agent's verdict into
`node.output`.** They dispatch a node by loading its skill/command text into
`output`; the shipped `execute-work-orders.yaml` documents the same finding after
trying the opposite: "`_invoke_skill` LOADS a skill and returns its SKILL.md text
... the agent that would print the token reads the runner's output out of band."
So a `condition:` can safely reference an **upstream** node whose YAML gave it a
literal, already-resolved field, but it cannot reliably branch on a verdict an
agent prints during dispatched work — that agent's stdout goes to you, not into
state. If a real gate is needed, declare a `completion_check` that reads the
effect independently (a git ref, an authority query, a stored artifact) instead of
trying to match on `{{node.output}}`.

**Standard verdicts (for your own tracking and for the Director, not for the engine):**

| Verdict | Meaning | Next action |
|---------|---------|-------------|
| `PASSED` | Node completed successfully, no issues | Continue to dependents |
| `BLOCKED` | Critical/high issues found that must be fixed | Fix, or stop and ask |
| `FAILED` | Node could not complete its work | Redo the work, or escalate |
| `SKIPPED` | Node was not applicable (condition false) | Continue, treat as non-blocking |
| `VERIFIED` | Evidence-based confirmation (verify skill) | Continue to ship |
| `UNKNOWN` | Agent didn't produce a clear verdict | Stop for Director review |

**Prompt injection for command nodes:** When writing `command:` blocks in workflow YAML, always end the prompt with:
```
Your final output line MUST be exactly one of: PASSED, BLOCKED, FAILED.
Format: VERDICT: one-line summary of what you found.
```

This keeps your own record unambiguous even though the runner itself never reads it.

**3e. Loop** — after doing the node's work, call `ds workflow advance <key>` again. Repeat from 3a until it reports no nodes ready and `ds workflow status <key>` shows the workflow done.

#### Step 4 — Complete

When `ds workflow status <key>` (or the final line from `ds workflow run <key>`) shows the workflow `completed`, trigger `ds-core recap`.

---

## Error Handling

**Node failure:** `ds workflow` does not retry automatically — `retry:` is
validated as well-formed but never enforced by the runner. If you choose to redo
the work yourself, track the attempt count against the node's declared
`retry.max` (default: treat 3 attempts as the ceiling if none is declared); after
exhausting it, stop and escalate to the Director rather than continuing. There is
no `update` command to reset a failed or blocked node back to `pending`, so a
node that comes back `blocked` or `failed` stays that way for the rest of the run.

**Dependency failure by trigger rule:**
- `all_success` → dependent stays un-ready forever (a `failed`/`blocked` dep never satisfies it)
- `all_done` → dependent becomes ready once the dep reaches any terminal status (`completed`/`failed`/`skipped`/`unverified`)
- `one_success` → dependent becomes ready once any dep is `completed`

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
| GitHub Actions, CI/CD, DevOps | `infra/devops/` |
| Testing, E2E, unit testing | `domains/testing/` |
| Technical writing, docs | `core/documentation/` |
| Power BI, DAX, M-query | `domains/bi/` or `domains/powerbi/` |
| UI design systems, CSS, layout | `website/design/` |
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
