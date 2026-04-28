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
- **Model selection** — Right model for the task complexity

## Model Selection

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
2. Implementer returns DONE or DONE_WITH_CONCERNS
3. Dispatch spec compliance reviewer
4. If reviewer finds issues:
   - Re-dispatch implementer with fixes needed
   - Go to step 3 (repeat until ✅)
5. Dispatch code quality reviewer
6. If reviewer finds issues:
   - Re-dispatch implementer with fixes needed
   - Go to step 5 (repeat until ✅)
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

### Implementer prompt template (build skill)
```
You are implementing Task N: [task name]

## Context
- Project: [project description]
- Architecture: [key patterns]
- Dependencies: [what this task depends on]
- Plan: [link or full task text]

## Task
[Full task specification pasted here — not a file path]

## Acceptance criteria
[How to verify this is done]

## Working directory
[absolute path]

## Decisions made so far
[any architecture decisions that affect this task]

## Output format
When done, respond with ONE of:
- DONE — task complete, ready for review
- DONE_WITH_CONCERNS — task complete but concerns noted (explain)
- NEEDS_CONTEXT — missing information (specify what)
- BLOCKED — cannot complete (explain why)
```

### Reviewer prompt template (review skill)
```
You are reviewing an implementation.

## Spec
[Full task specification]

## Implementation
[Code changes or link to diff]

## Job
Verify code matches spec. Read the actual code, not the implementer's report.

Critical rule: Do not trust the report. The implementer finished suspiciously quickly.

## Output format
✅ COMPLIANT — code matches spec exactly
❌ NON-COMPLIANT — issues found

If non-compliant, list each issue with:
- Requirement: [from spec]
- Issue: [what's wrong]
- Location: file:line
- Fix: [what needs to change]
```

## Handling agent responses

### DONE
Proceed to review stage.

### DONE_WITH_CONCERNS
Read concerns. If they affect correctness or scope, address before review. If they're style/preference, proceed to review.

### NEEDS_CONTEXT
Provide missing information and re-dispatch with updated prompt.

### BLOCKED
Assess blockers:
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

## Used by
build, review, secure, think, analyze, career-ops
