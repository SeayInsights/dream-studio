# Agent Orchestration — Core Module

Reusable patterns for spawning, coordinating, and collecting results from subagents.

## Usage

When a skill needs multi-agent orchestration, reference this module:
```
## Imports
- core/orchestration.md — agent orchestration
```

## Core Principles

- **Fresh subagent per task** — Never inherit session history
- **Controller stays lean** — Delegate heavy lifting, preserve own context
- **Pre-inline context** — Don't make agents Read files, provide full text
- **Static before dynamic** — In every subagent prompt, put static content (core module text, project context, repo map) BEFORE dynamic content (task text, decisions so far). Claude caches the longest common prefix across consecutive calls; consistent ordering enables automatic caching of the static prefix.
- **Model selection** — Right model for the task complexity

## Model Selection

**Primary method: read `model_tier` from the target skill's `config.yml`.**

Every skill's `config.yml` declares `model_tier: haiku | sonnet | opus`. When spawning a subagent for a skill, use that tier:

```python
# Python (hooks): from hooks.lib.model_selector import get_model_for_skill
tier = get_model_for_skill("dream-studio:core think")  # → "opus"

# CLI: py hooks/lib/model_selector.py --skill="dream-studio:core think"
```

When dispatching an Agent tool call, set the `model` parameter to the skill's declared tier:
```
Agent({
  description: "Think through architecture",
  model: get_model_for_skill("dream-studio:core think"),  // "opus"
  prompt: `...`
})
```

**Fallback heuristic** (when no specific skill is targeted):

| Task type | Model | Signal |
|-----------|-------|--------|
| Mechanical (1-2 files, clear spec) | Haiku | Isolated function, straightforward |
| Integration (multi-file, patterns) | Sonnet | Coordination, debugging |
| Architecture, design, review | Opus | Judgment calls, broad understanding |
| Fast exploration | Haiku | Quick codebase lookup, file search |
| Code implementation | Sonnet | Default for code changes |
| Complex analysis | Opus | Security review, multi-perspective analysis |

## Patterns

### Spawn single subagent
```
Agent({
  description: "Short 3-5 word description",
  model: "haiku" | "sonnet" | "opus",
  prompt: `Detailed instructions here
  
  Context: [provide full context, don't reference files]
  Task: [what needs to be done]
  Output: [expected format]
  `
})
```

### Spawn parallel subagents (independent work)
```
Agent({
  description: "Implement task 1",
  model: "sonnet",
  prompt: `...`
})

Agent({
  description: "Implement task 2",  
  model: "sonnet",
  prompt: `...`
})
```

**When to use parallel:**
- Tasks touch different files
- No dependencies between tasks
- Results can be collected independently

**Never parallel if:**
- Tasks modify the same files
- One task depends on another's output
- Order matters

### Spawn sequential subagents (dependent work)
```
// First agent
const result1 = await Agent({
  description: "Implement feature",
  model: "sonnet",
  prompt: `...`
})

// Use result1 to inform second agent
const result2 = await Agent({
  description: "Review implementation",
  model: "sonnet",
  prompt: `Review this implementation:
  
  ${result1}
  
  Check for: ...
  `
})
```

### Review loop pattern
```
1. Dispatch implementer agent
2. Parse result.signal:
   - done → proceed to step 3
   - done_with_concerns → address result.concerns if correctness/scope, then step 3
   - needs_context / blocked → resolve, re-dispatch
3. Dispatch spec compliance reviewer
4. Parse reviewer result.signal:
   - compliant → proceed to step 5
   - non_compliant → re-dispatch implementer with result.issues, go to step 3
5. Dispatch code quality reviewer
6. Parse reviewer result.signal:
   - compliant → commit
   - non_compliant → re-dispatch implementer with result.issues, go to step 5
7. Commit
```

### Parallel analyst pattern (think, secure, analyze skills)
```
const analysts = [
  { role: "Skeptic", lens: "What could go wrong?" },
  { role: "Optimist", lens: "What's the best case?" },
  { role: "Pragmatist", lens: "What's practical?" }
]

// Spawn all in parallel
analysts.forEach(analyst => {
  Agent({
    description: `${analyst.role} analysis`,
    model: "sonnet",
    prompt: `Analyze from the ${analyst.role} perspective:
    
    Lens: ${analyst.lens}
    Input: [the thing to analyze]
    Output: [findings in this format]
    `
  })
})

// Collect and synthesize results
```

### Compiled Prompt Pattern (automated)

When `hooks/lib/context_compiler.py` and `hooks/lib/prompt_assembler.py` are available, use them instead of manually assembling prompts:

```bash
# 1. Compile static context (run ONCE per session)
py hooks/lib/context_compiler.py --skill=build --pack=core --repo-context=repo-context.json > compiled.md

# 2. Assemble per-task prompt (run per dispatch)
py hooks/lib/prompt_assembler.py --template=implementer --static-context=compiled.md --task-text="Task 3: Build login form"
```

**Why:** The compiled context strips boilerplate (~77% reduction) and produces a byte-identical static prefix. Claude automatically caches the longest common prefix across consecutive calls, so tasks in the same wave share cache hits.

**Templates:** `implementer` (build tasks), `reviewer` (code review), `auditor` (security/quality audits), `explorer` (codebase questions).

**Model selection:** Use `get_model_for_skill(skill_specifier)` which reads from `config.yml` (priority) then SKILL.md frontmatter (fallback). Without the frontmatter flag, the CLI queries historical success rates from SQLite for a data-driven recommendation.

**Fallback:** If scripts are unavailable or error, use the manual templates below — they work identically, just without automatic caching optimization.

### Implementer prompt template (build skill)

**Ordering rule:** Static content FIRST, dynamic content LAST. Assemble the static prefix
(project context + repo map + architecture) ONCE per session and prepend it identically to
every dispatch — this enables Claude's automatic prompt caching on the common prefix.

```
You are implementing Task N: [task name]

## Project Context (static — same for every task in this session)
- Project: [project description]
- Architecture: [key patterns]
- Repo Map (see core/repo-map.md for generation):
  [paste compact repo map — one line per symbol, generated once at build Step 0]

## Working directory
[absolute path]

## Task (dynamic — specific to this dispatch)
[Full task specification pasted here — not a file path]

## Acceptance criteria
[How to verify this is done]

## Dependencies resolved
[what prior tasks produced that this task needs]

## Decisions made so far
[any architecture decisions that affect this task]

## Output format
Respond with a JSON object:
{
  "signal": "done | done_with_concerns | needs_context | blocked",
  "confidence": 0.0-1.0,
  "summary": "One sentence on what was completed or what the issue is",
  "concerns": ["list if signal = done_with_concerns — specific, actionable"],
  "missing": ["what context is needed if signal = needs_context"],
  "blocker": "why blocked if signal = blocked — specific enough to act on"
}
```

### Reviewer prompt template (review skill)
```
You are reviewing an implementation.

## Spec
[Full task specification]

## Implementation
[Code changes or diff — pasted inline, not a file path]

## Job
Verify code matches spec. Read the actual code, not the implementer's report.

Critical rule: Do not trust the report. Verify independently.

## Output format
Respond with a JSON object:
{
  "signal": "compliant | non_compliant",
  "confidence": 0.0-1.0,
  "summary": "One sentence verdict",
  "issues": [
    {
      "requirement": "the requirement from spec",
      "issue": "what is wrong",
      "location": "file:line",
      "fix": "specific, actionable fix"
    }
  ]
}

issues array is empty when signal = compliant.
```

## Handling agent responses

Parse `result.signal` from the JSON output.

### done
Proceed to review stage.

### done_with_concerns
Read `result.concerns[]`. If any concern affects correctness or scope, address before review.
If style/preference only, proceed to review.

### needs_context
Read `result.missing[]`. Provide the missing information and re-dispatch with updated prompt.

### blocked
Read `result.blocker`. Assess:
- **Context problem:** Re-dispatch with more info
- **Capability problem:** Re-dispatch with more capable model (Haiku → Sonnet → Opus)
- **Task too large:** Break task into smaller pieces
- **Plan is wrong:** Escalate to Director (user)

## Background agents

For long-running work that doesn't need immediate results:
```
Agent({
  description: "Long analysis",
  model: "sonnet",
  run_in_background: true,
  prompt: `...`
})
```

You'll be notified when it completes — don't poll or wait.

## Dependency analysis for parallel execution

Group tasks into waves:
1. **Wave 1:** Tasks with no dependencies (can run parallel if independent files)
2. **Wave 2:** Tasks depending on Wave 1
3. **Wave N:** Continue until all ordered

**Rule:** Independent tasks within a wave MAY run parallel IF they touch different files.

## Context preservation

Why subagents:
- They get only task-specific state — no session history, no conversation baggage
- Preserves your own context for coordination
- Each agent stays focused
- Failed agents don't pollute controller context

## Pipeline gate check (soft)

At the start of any skill that has a pipeline prerequisite, output a gate check:

```
Pipeline: [current stage] | Expected prerequisite: [prior stage]
Prior stage complete? [YES / NO / UNKNOWN]
```

- **YES** → proceed
- **NO / UNKNOWN** → "Recommend running [prior skill] first. Continue anyway? (Director can override)"

**Usage:** Add to skill's "Before you start" section — "Check pipeline gate: [this stage] requires [prior stage] complete."

**Why soft (not blocking):** The Director may legitimately skip stages (e.g., running `review` on pre-existing code without a `build` run). The gate surfaces the gap without enforcing it.

## Used by
build, review, secure, think, analyze, career-ops
