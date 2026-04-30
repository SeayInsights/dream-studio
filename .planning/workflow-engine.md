# Spec: YAML Workflow Engine for Dream-Studio

**Status:** PENDING APPROVAL
**Date:** 2026-04-18
**Approach:** YAML Skill + Progress Hook (Approach A)

## Problem Statement

Dream-studio's 18 skills execute sequentially via manual DCL commands. Each stage requires the Director to type the next command (`think:` → wait → `plan:` → wait → `build:` → ...). This creates three gaps vs. the market:

1. **No automated pipelines** — Archon runs idea-to-PR in one command. Cursor has Background Agents. Devin runs fully autonomous. Dream-studio requires constant attendance.
2. **No parallel execution within a stage** — Review runs one agent at a time. Archon spawns 5 review agents in parallel and synthesizes.
3. **No shareable/reusable workflow definitions** — Process knowledge lives in skill markdown, not in composable pipeline definitions teams can version-control.

## Chosen Approach

A new `workflow` skill + `on-workflow-progress` hook that teaches Chief-of-Staff to read `.workflows/*.yaml` DAG definitions and execute them through existing skills.

**Why this over alternatives:**
- Stays within plugin architecture (no external process)
- YAML files are shareable, per-project overridable
- Chief-of-Staff already handles parallel spawning + worktree isolation
- Zero new runtime dependencies

## Architecture

```
.workflows/*.yaml          ← Declarative pipeline definitions (ship with plugin + per-project overrides)
        │
        ▼
skills/meta/workflow/       ← Instructions to Chief-of-Staff on how to parse + orchestrate
        │
        ▼
Chief-of-Staff              ← Reads YAML, resolves dependency graph, spawns agents per node
   ├── Node A (think)       ← Sequential: gate = director-approval
   ├── Node B (plan)        ← Sequential: depends on A, gate = director-approval
   ├── Node C (build)       ← Sequential: depends on B, gate = auto-pass (quality > 3)
   ├── Node D (review-code) ← PARALLEL: depends on C
   ├── Node E (review-sec)  ← PARALLEL: depends on C (runs simultaneously with D)
   ├── Node F (synthesize)  ← Sequential: depends on D+E, merges findings
   ├── Node G (verify)      ← Sequential: depends on F, gate = evidence-required
   └── Node H (ship)        ← Sequential: depends on G
        │
        ▼
on-workflow-progress hook   ← Writes state to .dream-studio/state/workflows.json after each node
```

## YAML Schema

```yaml
# .workflows/idea-to-pr.yaml
name: idea-to-pr
description: Feature concept through implementation to merged PR
version: 1

# Gate policies — configurable per workflow
gates:
  director-approval:
    type: pause               # pause | auto-pass | skip
    prompt: "Approve to continue?"
  auto-pass:
    type: conditional
    condition: quality-score > 3
  evidence-required:
    type: pause
    requires: [screenshots, test-results]  # artifact types that must exist

nodes:
  - id: think
    skill: think
    gate: director-approval
    model: opus
    context: fresh

  - id: plan
    skill: plan
    depends_on: [think]
    gate: director-approval
    model: opus
    context: fresh
    input: "{{think.output}}"    # spec file path from think

  - id: build
    skill: build
    depends_on: [plan]
    gate: auto-pass
    model: sonnet
    context: fresh
    input: "{{plan.output}}"     # plan file path

  - id: review-code
    skill: review
    depends_on: [build]
    model: sonnet
    context: fresh
    agent: engineering

  - id: review-security
    skill: secure
    depends_on: [build]
    model: sonnet
    context: fresh
    agent: engineering

  - id: review-tests
    skill: review
    depends_on: [build]
    model: haiku
    context: fresh
    config:
      focus: test-coverage-only

  - id: review-perf
    skill: review
    depends_on: [build]
    model: haiku
    context: fresh
    config:
      focus: performance-only

  - id: review-docs
    skill: review
    depends_on: [build]
    model: haiku
    context: fresh
    config:
      focus: docs-impact-only

  - id: synthesize
    depends_on: [review-code, review-security, review-tests, review-perf, review-docs]
    trigger_rule: all_done       # runs when ALL deps finish (even if some fail)
    command: |
      Read all review reports. Synthesize into one findings document with severity tags.
      If any Critical/High findings: output BLOCKED with fix list.
      If all clean: output PASSED.
    model: sonnet
    context: fresh

  - id: fix-findings
    skill: build
    depends_on: [synthesize]
    condition: "{{synthesize.status}} == BLOCKED"
    model: sonnet
    context: fresh
    input: "{{synthesize.output}}"

  - id: verify
    skill: verify
    depends_on: [synthesize, fix-findings]
    trigger_rule: one_success
    gate: evidence-required
    model: sonnet
    context: fresh

  - id: ship
    skill: ship
    depends_on: [verify]
    model: sonnet
    context: fresh
```

## Node Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `id` | string | yes | Unique node identifier |
| `skill` | string | no | Skill to inject (from `skills/` directory) |
| `command` | string | no | Inline instruction (if no skill) |
| `depends_on` | string[] | no | Node IDs that must complete first |
| `gate` | string | no | Gate policy name (from `gates:` section) |
| `model` | string | no | Model override (opus/sonnet/haiku) |
| `context` | string | no | `fresh` (new agent) or `inherit` (continue session) |
| `agent` | string | no | Agent persona (engineering/game/client) |
| `trigger_rule` | string | no | `all_success` (default), `all_done`, `one_success` |
| `condition` | string | no | Expression that must be true for node to run |
| `input` | string | no | Template referencing prior node outputs |
| `config` | object | no | Skill-specific configuration |
| `retry` | number | no | Max retries before escalation (default: 3) |
| `isolation` | string | no | `worktree` (isolated git branch) or `shared` (default) |

## Gate System

Three gate types, all configurable per workflow:

### `pause` (default for director-approval)
Pipeline stops. Chief-of-Staff reports status and asks Director for approval. Resumes on explicit "go."

### `conditional`
Pipeline continues automatically if condition is met. Condition reads from:
- `quality-score` — from `on-quality-score` hook output
- Prior node status/output
- Artifact existence checks

If condition fails → falls back to `pause`.

### `skip`
Gate is disabled for this workflow. Use sparingly.

### `evidence-required`
Pipeline pauses and checks for required artifacts:
- `screenshots` — image files in `.verify/`
- `test-results` — test output logs
- `playwright` — Playwright report

If artifacts exist and pass → auto-continue. If missing → pause for Director.

## Parallel Execution Rules

Nodes with the same `depends_on` and no dependencies on each other run in parallel. Chief-of-Staff applies existing rules:

1. **Read-only nodes** (review, secure) — share main working tree, no worktree needed
2. **Write nodes** touching different files — can run in parallel in separate worktrees
3. **Write nodes** touching same files — MUST be sequential

The workflow skill instructs Chief-of-Staff to analyze node types and apply the right isolation strategy.

## State Tracking

### Workflow state file: `~/.dream-studio/state/workflows.json`

```json
{
  "schema_version": 1,
  "active_workflows": {
    "idea-to-pr-1713456000": {
      "workflow": "idea-to-pr",
      "started": "2026-04-18T12:00:00Z",
      "status": "running",
      "current_node": "review-code",
      "nodes": {
        "think": { "status": "completed", "output": ".planning/dark-mode.md", "duration_s": 120 },
        "plan": { "status": "completed", "output": ".planning/dark-mode-plan.md", "duration_s": 90 },
        "build": { "status": "completed", "output": "6 commits", "duration_s": 600 },
        "review-code": { "status": "running", "started": "2026-04-18T12:15:00Z" },
        "review-security": { "status": "running", "started": "2026-04-18T12:15:00Z" },
        "review-tests": { "status": "running", "started": "2026-04-18T12:15:00Z" },
        "review-perf": { "status": "pending" },
        "review-docs": { "status": "pending" },
        "synthesize": { "status": "blocked_by_deps" },
        "verify": { "status": "blocked_by_deps" },
        "ship": { "status": "blocked_by_deps" }
      },
      "gates_passed": ["think:director-approval", "plan:director-approval", "build:auto-pass"],
      "gates_pending": []
    }
  }
}
```

### Progress hook: `on-workflow-progress`

Triggered on `Stop` event. Reads workflow state, updates `workflows.json`, prints summary:

```
[workflow] idea-to-pr — Node review-code COMPLETED (3/11 nodes done)
  -> Next: waiting for review-security, review-tests to complete
  -> Gate pending: none
  -> ETA: ~15 minutes
```

## File Inventory

### New files (6)

| File | Type | Purpose |
|------|------|---------|
| `skills/workflow/SKILL.md` | Skill | Workflow orchestration instructions for Chief-of-Staff |
| `hooks/handlers/on-workflow-progress.py` | Hook | State tracking + progress reporting |
| `workflows/idea-to-pr.yaml` | Template | Full pipeline: think → build → parallel review → verify → ship |
| `workflows/fix-issue.yaml` | Template | Debug → fix → review → verify |
| `workflows/comprehensive-review.yaml` | Template | 5-way parallel review + synthesis |
| `workflows/safe-refactor.yaml` | Template | Plan → build → type-check → test → review |

### Modified files (2)

| File | Change |
|------|--------|
| `agents/chief-of-staff.md` | Add `workflow:` to DCL dispatch + workflow orchestration protocol |
| `hooks/hooks.json` | Register `on-workflow-progress` on `Stop` event |

### Optional future files (not in v1)

| File | Purpose |
|------|---------|
| `workflows/client-deliverable.yaml` | Power Platform intake → build → polish → ship |
| `workflows/game-sprint.yaml` | Design → blockout → implement → QA |
| `hooks/handlers/on-workflow-validate.py` | YAML schema validation before execution |

## Scope

### In scope
- Workflow skill with YAML parsing instructions
- Gate system (pause, conditional, evidence-required)
- Parallel node execution via existing Chief-of-Staff parallel spawning
- Fresh context per node (already supported by subagent mode)
- State tracking hook + JSON state file
- 4 workflow templates (idea-to-pr, fix-issue, comprehensive-review, safe-refactor)
- Chief-of-Staff dispatch update for `workflow:` command
- Hooks.json registration

### Out of scope (v2+)
- Visual DAG editor / web dashboard
- External platform triggers (Slack, Discord, GitHub webhooks)
- Programmatic YAML validation hook
- Workflow marketplace / sharing
- Domain-specific templates (client, game)
- Conditional branching (if/else nodes)
- Loop nodes (retry-until patterns)

## Risk Flags

1. **LLM YAML parsing reliability** — Claude reading YAML and resolving deps is less deterministic than code. Mitigation: keep templates simple (< 15 nodes), use clear naming, add validation guidance in the skill.

2. **Context budget** — A 12-node workflow with fresh context per node means 12 agent spawns. Each spawn consumes tokens. Mitigation: model routing (haiku for read-only nodes) keeps costs manageable.

3. **Gate interruption UX** — When a `pause` gate fires mid-workflow, the Director needs clear context on what happened and what's next. Mitigation: the skill requires Chief-of-Staff to present a workflow status summary at every gate.

4. **Parallel agent coordination** — 5 parallel review agents need to write findings to separate files to avoid conflicts. Mitigation: naming convention in the skill (`review-{node-id}-findings.md`).

## What This Preserves From Dream-Studio

| Discipline | How it's preserved |
|---|---|
| No code before spec approval | `think` + `plan` nodes with `director-approval` gate |
| 3-retry cap | `retry: 3` per node (default) |
| Drift detection | Build skill still enforces drift checks within its node |
| Evidence-based verification | `evidence-required` gate on verify node |
| Two-tier review | Can compose fast-scan + full-review as sequential nodes |
| Atomic commits | Build skill still enforces per-task commits within its node |
| Learning loop | Workflow completion triggers recap; handoff still fires on context threshold |
| Scientific debugging | Debug skill unchanged; `fix-issue` template chains it properly |

## What This Adds From Archon

| Feature | How it's implemented |
|---|---|
| Parallel multi-agent review | 5 review nodes with same `depends_on` → Chief-of-Staff spawns in parallel |
| Fresh context per node | `context: fresh` → subagent mode (already supported) |
| Declarative YAML workflows | `.workflows/*.yaml` read by workflow skill |
| Fire-and-forget pipelines | `auto-pass` gates on low-risk nodes + conditional gates |
| Per-project overrides | Project `.workflows/` overrides plugin defaults |
| Workflow state tracking | `on-workflow-progress` hook writes to `workflows.json` |

## DCL Commands

| Command | Action |
|---|---|
| `workflow: idea-to-pr` | Start the idea-to-pr workflow |
| `workflow: fix-issue` | Start the fix-issue workflow |
| `workflow: comprehensive-review` | Start the comprehensive-review workflow |
| `workflow: safe-refactor` | Start the safe-refactor workflow |
| `workflow status` | Show current workflow state |
| `workflow resume` | Resume a paused workflow after gate approval |
| `workflow abort` | Cancel the active workflow |
