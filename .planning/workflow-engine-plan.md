# Plan: YAML Workflow Engine

Spec: `.planning/workflow-engine.md`
Date: 2026-04-18

## Dependency Graph

```
Wave 1 (parallel):  [T1: Workflow Skill]    [T2: Progress Hook]
                          │                        │
Wave 2 (parallel):  [T3: CoS Update]──┐   [T4: hooks.json]   [T5: idea-to-pr.yaml]
                                       │                             │
Wave 3 (parallel):              [T6: fix-issue]  [T7: comprehensive-review]  [T8: safe-refactor]
```

---

## Tasks

### 1. Create workflow orchestration skill
- **Files:** `skills/workflow/SKILL.md` (new)
- **Depends on:** none
- **Acceptance:**
  - File exists at `skills/workflow/SKILL.md` with valid frontmatter (name, description)
  - Contains: YAML schema reference, DAG resolution protocol, gate system instructions, parallel execution rules, node lifecycle, state reporting format, error/retry protocol
  - Covers all DCL commands: `workflow: <name>`, `workflow status`, `workflow resume`, `workflow abort`
  - References existing skills by path (not inline content)
  - Instructs Chief-of-Staff to write node outputs to `review-{node-id}-findings.md` for parallel review nodes

### 2. Create workflow progress hook
- **Files:** `hooks/handlers/on-workflow-progress.py` (new)
- **Depends on:** none
- **Acceptance:**
  - File exists with standard hook boilerplate (imports from `lib.paths`, `lib.state`)
  - Reads/writes `~/.dream-studio/state/workflows.json`
  - Schema matches spec: `schema_version`, `active_workflows` dict with per-workflow entries containing `workflow`, `started`, `status`, `current_node`, `nodes` (per-node status/output/duration), `gates_passed`, `gates_pending`
  - Prints structured summary to stdout: `[workflow] <name> — Node <id> <STATUS> (N/M nodes done)`
  - Prints JSON status line for Claude Code to ingest
  - Handles missing/empty state file gracefully
  - Functions: `read_workflows()`, `write_workflows()`, `update_node()`, `workflow_summary()`

### 3. Update Chief-of-Staff DCL dispatch
- **Files:** `agents/chief-of-staff.md` (modify)
- **Depends on:** Task 1
- **Acceptance:**
  - New "Workflow" section in DCL Dispatch table with commands: `workflow: *`, `workflow status`, `workflow resume`, `workflow abort`
  - All workflow commands route to Main Session with skill `skills/workflow`
  - New "Workflow orchestration protocol" section describing how Chief-of-Staff executes a workflow (read YAML → resolve DAG → execute nodes → report at gates)
  - Existing DCL sections unchanged
  - Auto-trigger added: "After workflow completes → trigger `skills/studio/recap`"

### 4. Register progress hook in hooks.json
- **Files:** `hooks/hooks.json` (modify)
- **Depends on:** Task 2
- **Acceptance:**
  - `on-workflow-progress` added to `Stop` hooks array
  - Follows existing pattern: `{"type": "command", "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/run.sh\" on-workflow-progress"}`
  - Existing hooks unchanged
  - JSON is valid (no trailing commas, proper nesting)

### 5. Create idea-to-pr workflow template
- **Files:** `workflows/idea-to-pr.yaml` (new)
- **Depends on:** Task 1
- **Acceptance:**
  - File exists in `workflows/` directory at plugin root
  - Contains `name`, `description`, `version` header
  - Defines 3 gate policies: `director-approval` (pause), `auto-pass` (conditional on quality-score > 3), `evidence-required` (pause, requires screenshots + test-results)
  - 12 nodes matching spec: think, plan, build, review-code, review-security, review-tests, review-perf, review-docs, synthesize, fix-findings (conditional), verify, ship
  - 5 review nodes share `depends_on: [build]` (parallel execution)
  - `synthesize` depends on all 5 review nodes with `trigger_rule: all_done`
  - `fix-findings` has `condition` that only fires if synthesize outputs BLOCKED
  - `verify` uses `trigger_rule: one_success` on synthesize + fix-findings
  - Model routing: opus for think/plan, sonnet for build/review-code/review-security/synthesize/fix/verify/ship, haiku for review-tests/review-perf/review-docs
  - All nodes have `context: fresh`

### 6. Create fix-issue workflow template
- **Files:** `workflows/fix-issue.yaml` (new)
- **Depends on:** Task 5 (pattern reference)
- **Acceptance:**
  - Header: name `fix-issue`, description, version 1
  - Gate policies: `director-approval` (pause), `auto-pass` (conditional)
  - Nodes (6): diagnose (debug skill), plan-fix (plan skill, depends diagnose), implement-fix (build skill, depends plan-fix), review (review skill, depends implement-fix), verify (verify skill, depends review, gate evidence-required), report (inline command summarizing fix, depends verify)
  - Model routing: sonnet for diagnose/implement-fix/review, haiku for plan-fix/report, sonnet for verify
  - All nodes `context: fresh`

### 7. Create comprehensive-review workflow template
- **Files:** `workflows/comprehensive-review.yaml` (new)
- **Depends on:** Task 5 (pattern reference)
- **Acceptance:**
  - Header: name `comprehensive-review`, description, version 1
  - No gates (review-only workflow)
  - Nodes (7): review-code, review-security, review-tests, review-perf, review-docs (all parallel, no depends_on), synthesize (depends on all 5, trigger_rule all_done), report (depends synthesize, inline command posting summary)
  - Model routing: sonnet for review-code/review-security/synthesize, haiku for review-tests/review-perf/review-docs/report
  - All nodes `context: fresh`

### 8. Create safe-refactor workflow template
- **Files:** `workflows/safe-refactor.yaml` (new)
- **Depends on:** Task 5 (pattern reference)
- **Acceptance:**
  - Header: name `safe-refactor`, description, version 1
  - Gate policies: `director-approval` (pause), `auto-pass` (conditional)
  - Nodes (7): plan-refactor (think skill, gate director-approval), implement (build skill, depends plan-refactor), type-check (inline command running type checker, depends implement), test (inline command running test suite, depends implement — parallel with type-check), review (review skill, depends type-check + test), verify (verify skill, depends review, gate evidence-required), report (inline command, depends verify)
  - Model routing: opus for plan-refactor, sonnet for implement/review/verify, haiku for type-check/test/report
  - All nodes `context: fresh`

---

## Summary

| # | Task | Depends on | Files | Complexity |
|---|------|-----------|-------|------------|
| 1 | Workflow orchestration skill | none | `skills/workflow/SKILL.md` | high |
| 2 | Progress hook | none | `hooks/handlers/on-workflow-progress.py` | medium |
| 3 | Chief-of-Staff DCL update | 1 | `agents/chief-of-staff.md` | medium |
| 4 | Register hook in hooks.json | 2 | `hooks/hooks.json` | low |
| 5 | idea-to-pr template | 1 | `workflows/idea-to-pr.yaml` | medium |
| 6 | fix-issue template | 5 | `workflows/fix-issue.yaml` | low |
| 7 | comprehensive-review template | 5 | `workflows/comprehensive-review.yaml` | low |
| 8 | safe-refactor template | 5 | `workflows/safe-refactor.yaml` | low |

**Execution waves:**
- **Wave 1** (parallel): Tasks 1 + 2
- **Wave 2** (parallel): Tasks 3 + 4 + 5
- **Wave 3** (parallel): Tasks 6 + 7 + 8

**Estimated total:** 8 tasks across 3 waves
