# Tasks: dream-studio Improvements

**Input**: `.planning/specs/dream-studio-improvements/plan.md`
**Branch**: `feat/dream-studio-improvements`
**Total tasks**: 26 | **Traceability**: Active

---

## Phase 1: Setup

- [ ] T001 Create branch `feat/dream-studio-improvements` and verify clean working tree
  - Depends: none
  - Files: git only
  - Acceptance: `git branch --show-current` returns `feat/dream-studio-improvements`; `git status` is clean

---

## Phase 2: P1 Fixes + P2 Core Schema + Independent P3 Starts

*All tasks in this phase touch different files and can run in parallel after T001.*
*T004 is the Wave 2 bottleneck — Wave 3 cannot start until T004 is complete.*

- [ ] T002 [P] workflows/fix-issue.yaml — add `create-issue` node after `diagnose`
  - Implements: TR-001
  - Depends: T001
  - Files: `workflows/fix-issue.yaml`
  - Content: New node runs `gh issue create --title "[Bug] {{diagnose.summary}}" --body "{{diagnose.full_log}}"` unconditionally after diagnose, before plan-fix. Node id: `create-issue`, model: haiku, timeout: 60s.
  - Acceptance: fix-issue.yaml `create-issue` node exists between `diagnose` and `plan-fix`; `diagnose` has `create-issue` in its dependents

- [ ] T003 [P] skills/explain/* — create new explain skill with routing entry
  - Implements: TR-002
  - Depends: T001
  - Files: `skills/explain/SKILL.md`, `skills/explain/metadata.yml`, `skills/explain/gotchas.yml`, `skills/explain/config.yml`, `skills/explain/changelog.md`; `CLAUDE.md`
  - Content:
    - SKILL.md: Purpose is "Trace how X works — from entry point through layers to output, at the depth the Director needs." Trigger: `explain:`, `how does X work`, `walk me through`, `what is this doing`. Steps: (1) Identify the entry point, (2) Trace the call chain — max 3 hops unless asked deeper, (3) Identify the SSOT for each layer, (4) Ask if Director wants more depth or a different angle. No code written. Output: layered explanation in conversation.
    - metadata.yml: name: explain, version: 1.0.0, pack: core, status: draft, health: active, triggers: ["explain:", "how does", "walk me through", "what is this doing"]
    - gotchas.yml: avoid reading every file speculatively — trace the call chain, read only what you land on; don't explain what the code does line-by-line — explain why it's structured that way
    - config.yml: max depth: 5 hops, default model: haiku (lookup) → sonnet (synthesis)
    - changelog.md: v1.0.0 initial
    - CLAUDE.md routing table: add explain row mapping `explain:`, `how does X work`, `walk me through`, `what is this doing` to `dream-studio:explain`
  - Acceptance: `ls skills/explain/` shows 5 files; CLAUDE.md routing table has explain row; CLAUDE.md global (`~/.claude/CLAUDE.md`) routing table updated to include explain

- [ ] T004 core/orchestration.md — JSON agent schema + prompt ordering rule (P2-a + P2-b)
  - Implements: TR-003, TR-004
  - Depends: T001
  - Files: `skills/core/orchestration.md`
  - Content — two changes in one commit to keep the file consistent:
    1. **Implementer prompt template** — replace `Output format: DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED` block with JSON schema:
       ```json
       {
         "signal": "done | done_with_concerns | needs_context | blocked",
         "confidence": 0.0-1.0,
         "summary": "One sentence on what was completed or what the issue is",
         "concerns": ["list if signal = done_with_concerns"],
         "missing": ["what context is needed if signal = needs_context"],
         "blocker": "why blocked if signal = blocked"
       }
       ```
    2. **Reviewer prompt template** — replace `✅ COMPLIANT / ❌ NON-COMPLIANT` verdict block with JSON schema:
       ```json
       {
         "signal": "compliant | non_compliant",
         "confidence": 0.0-1.0,
         "summary": "One sentence verdict",
         "issues": [{"requirement": "...", "issue": "...", "location": "file:line", "fix": "..."}]
       }
       ```
    3. **Core Principles** — add principle: "Static before dynamic — in every subagent prompt, put static content (core module text, project context, repo map) BEFORE dynamic content (task text, decisions so far). Claude caches the longest common prefix across consecutive calls; consistent ordering enables automatic caching."
    4. **Implementer prompt template sections** — reorder so Architecture/Context comes before Task text
  - Acceptance: orchestration.md implementer template contains `"signal":` JSON block; reviewer template contains `"signal": "compliant | non_compliant"` JSON block; Core Principles list includes "Static before dynamic"

- [ ] T007 [P] skills/core/repo-map.md — create new core module + update REGISTRY.md
  - Implements: TR-006
  - Depends: T001
  - Files: `skills/core/repo-map.md` (new), `skills/core/REGISTRY.md`
  - Content:
    - repo-map.md: Module that defines how to generate a compact repo map. Generation commands (bash): `find . -name "*.ts" -o -name "*.py" -o -name "*.go" | grep -v node_modules | grep -v .git | sort`. Then for each file: `grep -n "^export\|^def \|^class \|^func \|^pub fn" <file>` to extract exported symbols. Output format: `path:type:name` one line per symbol. Skills import with `- core/repo-map.md — compact symbol index for subagent context`.
    - REGISTRY.md: Add `core/repo-map.md` section listing `build` as user, "Compact symbol map generation for subagent pre-inline context" as pattern, change impact: 1 skill initially.
  - Acceptance: `skills/core/repo-map.md` exists; REGISTRY.md has repo-map section

- [ ] T008 [P] skills/core/format.md — add task-level checkpoint format variant
  - Implements: TR-007
  - Depends: T001
  - Files: `skills/core/format.md`
  - Content: Add "Task-level checkpoint" format variant in the Checkpoint format section, alongside the existing wave-level checkpoint:
    ```
    ## Task Checkpoint — Task N: [task name]
    Status: COMPLETE
    Commit: [short SHA] — [one-line message]
    Next: Task N+1 — [next task name]
    Context: ~X% used
    ```
    Add note: "Use task-level for per-task checkpoints (build with threshold=1). Use wave-level for multi-task summaries."
  - Acceptance: format.md contains "Task Checkpoint" heading and the 5-line format block

- [ ] T009 [P] skills/build/config.yml — set checkpoint threshold to 1
  - Implements: TR-007
  - Depends: T001
  - Files: `skills/build/config.yml`
  - Content: Change `max_tasks_before_checkpoint: 3` to `max_tasks_before_checkpoint: 1`
  - Acceptance: `grep max_tasks_before_checkpoint skills/build/config.yml` returns `1`

- [ ] T010 [P] workflows/idea-to-pr.yaml — add conditional security branch after synthesize
  - Implements: TR-005
  - Depends: T001
  - Files: `workflows/idea-to-pr.yaml`
  - Content: After `synthesize` node and before `verify`, add two conditional nodes:
    - `triage-security` node: `condition: "{{synthesize.security_signal}} == blocked or {{synthesize.security_signal}} == strong_reject"`, skill: secure, model: sonnet, depends_on: [synthesize]
    - `mitigate-findings` node: condition matches same, skill: mitigate, depends_on: [triage-security]
    - Update `verify` depends_on: [synthesize, mitigate-findings] with trigger_rule: all_done
  - Acceptance: idea-to-pr.yaml has `triage-security` and `mitigate-findings` nodes; verify depends_on includes mitigate-findings

- [ ] T011 [P] hooks/lib/skill_metrics.py — create metrics tracking script
  - Implements: TR-010
  - Depends: T001
  - Files: `hooks/lib/skill_metrics.py` (new)
  - Content: Python script that accepts argv: `[skill_name] [model]`. Appends a JSON line to `~/.dream-studio/state/skill-usage.jsonl` (creates dir if missing). Line format: `{"ts": "ISO-8601", "skill": skill_name, "model": model, "session": "dream-studio"}`. Exits 0 always (metrics failure must not block skill execution).
  - Acceptance: `py hooks/lib/skill_metrics.py test-skill sonnet` exits 0; `~/.dream-studio/state/skill-usage.jsonl` has one JSON line

---

## Phase 3: P2 Dependent (wait for T004)

- [ ] T005 [P] skills/build/SKILL.md — JSON handler + static-first ordering note (P2-a + P2-b)
  - Implements: TR-003, TR-004
  - Depends: T004
  - Files: `skills/build/SKILL.md`
  - Content:
    1. **Step 2 "Handle implementer response"** — replace the DONE/BLOCKED/NEEDS_CONTEXT/BLOCKED prose with JSON parsing: "Read `result.signal`. If `done` → proceed to review. If `done_with_concerns` → read `result.concerns`, address if correctness/scope, then review. If `needs_context` → provide `result.missing` items, re-dispatch. If `blocked` → read `result.blocker`, assess and escalate."
    2. **Implementer dispatch note** — add after the dispatch template: "Ordering rule: assemble the static prefix (repo map + project context + task spec) ONCE per session. Prepend it identically to every dispatch — this enables Claude's automatic prompt caching on the common prefix."
  - Acceptance: build/SKILL.md Step 2 contains `result.signal`; dispatch section contains "Ordering rule"

- [ ] T006 [P] skills/review/SKILL.md — reviewer JSON verdict schema (P2-a)
  - Implements: TR-003
  - Depends: T004
  - Files: `skills/review/SKILL.md`
  - Content: In "Subagent review" section (and Fast scan mode output), replace the `✅ COMPLIANT / ❌ NON-COMPLIANT` output block with the JSON schema from orchestration.md T004. Add note: "This schema matches core/orchestration.md — reviewer prompt template." Keep the Stage 1/Stage 2 narrative prose above it (the JSON is the machine-readable output, the prose is the human-facing process description).
  - Acceptance: review/SKILL.md contains `"signal": "compliant | non_compliant"` JSON block

---

## Phase 4: P3 Dependent on T005 + T007

- [ ] T012 [P] skills/core/orchestration.md — add ## Repo Map field to implementer template
  - Implements: TR-006
  - Depends: T004, T007
  - Files: `skills/core/orchestration.md`
  - Content: In the implementer prompt template, after the `Architecture: [key patterns]` field, add:
    ```
    ## Repo Map
    [Paste compact repo map generated by core/repo-map.md — one line per symbol.
     Generate ONCE at build Step 0 and paste identically into every dispatch.]
    ```
    Also update the template comment: "See: core/repo-map.md for generation commands."
  - Acceptance: orchestration.md implementer template contains `## Repo Map` section with generation reference

- [ ] T013 [P] skills/build/SKILL.md — Step 0 repo-map generation
  - Implements: TR-006
  - Depends: T005, T007
  - Files: `skills/build/SKILL.md`
  - Content: In Step 0 "Load plan and project context", after the CONSTITUTION.md/GOTCHAS.md reads, add:
    "Generate repo map (see core/repo-map.md): run find+grep to extract exported symbols. Store as `$REPO_MAP`. This string is passed identically to every subagent dispatch in the session — do not regenerate per task."
  - Acceptance: build/SKILL.md Step 0 contains "repo map" and "core/repo-map.md" reference

---

## Phase 5: P3 Sequential — build/SKILL.md chain continues

- [ ] T014 skills/build/SKILL.md — Step 2 sub-step 7 task-level checkpoint
  - Implements: TR-007
  - Depends: T008, T013
  - Files: `skills/build/SKILL.md`
  - Content: Replace Step 2 sub-step 7 "Mark complete — Write proof to disk (task status in plan file or state file)" with:
    "Write task-level checkpoint to `.sessions/YYYY-MM-DD/checkpoint-<topic>.md` (append mode). Use format from core/format.md — Task Checkpoint. Include: task number + name, COMPLETE status, commit SHA, next task, context % estimate."
  - Acceptance: build/SKILL.md Step 2 sub-step 7 references "task-level checkpoint" and "core/format.md"

---

## Phase 6: P3 Parallel Wave (all different files, all after their respective deps)

- [ ] T015 [P] skills/build/SKILL.md — worktree isolation in parallel dispatch
  - Implements: TR-008
  - Depends: T014
  - Files: `skills/build/SKILL.md`
  - Content: In the "Spawn parallel subagents" section (imported from core/orchestration.md reference in SKILL.md) and in the build-specific dispatch instructions, add: "For parallel subagent dispatches, add `isolation: 'worktree'` to each Agent call. Claude Code creates an isolated git worktree per agent — last-writer-wins conflicts become structurally impossible. Worktree is auto-cleaned if the agent makes no changes."
  - Acceptance: build/SKILL.md parallel dispatch section contains `isolation: 'worktree'`

- [ ] T016 [P] .claude/settings.json — PostToolUse metrics hook
  - Implements: TR-010
  - Depends: T011
  - Files: `builds/dream-studio/.claude/settings.json` (project-level; create if missing)
  - Content: Add PostToolUse hook for the Skill tool: `{"matcher": "Skill", "hooks": [{"type": "command", "command": "py \"${CLAUDE_PROJECT_DIR}/hooks/lib/skill_metrics.py\" \"${TOOL_INPUT_SKILL}\" \"sonnet\""}]}`. Note: this fires on all dream-studio skill invocations within this project context.
  - Acceptance: `.claude/settings.json` exists with PostToolUse entry for Skill tool

- [ ] T017 [P] skills/core/orchestration.md — pipeline gate pattern
  - Implements: TR-009
  - Depends: T012
  - Files: `skills/core/orchestration.md`
  - Content: Add new section "## Pipeline gate check" after the Background agents section:
    ```
    ### Pipeline gate check (soft)
    At the start of any skill that has a pipeline prerequisite, output:
    
    ```
    Pipeline: [current stage] | Expected prerequisite: [prior stage]
    Prior stage complete? [YES / NO / UNKNOWN]
    ```
    
    If NO or UNKNOWN: "Recommend running [prior skill] first. Continue anyway? (Director can override)"
    If YES: proceed.
    
    Usage: Add to skills' "Before you start" section — "Check pipeline gate: [this stage] requires [prior stage]."
    ```
  - Acceptance: orchestration.md has "Pipeline gate check" section with the 3-line output format

- [ ] T018 [P] skills/debug/SKILL.md — Step 1.5 failing test capture
  - Implements: TR-011
  - Depends: T001
  - Files: `skills/debug/SKILL.md`
  - Content: Add Step 1.5 between Step 1 (Reproduce) and Step 2 (Hypothesize):
    "**1.5 Capture** — If the bug is unit-testable: write a minimal failing test that encodes the exact reproduction steps. This test becomes the fix's acceptance criterion and is passed to `verify` as the red-green check. If the bug is NOT unit-testable (UI rendering, race condition, infrastructure): capture a screenshot or log as the reproduction artifact instead. Add `testable: true/false` to debug output (used by fix-issue workflow to conditionally fire write-failing-test node)."
  - Acceptance: debug/SKILL.md has Step 1.5 between Steps 1 and 2 containing "testable: true/false"

- [ ] T019 [P] skills/verify/SKILL.md — red-green verification section
  - Implements: TR-011
  - Depends: T001
  - Files: `skills/verify/SKILL.md`
  - Content: Add "## Bug Fix Verification" section after the standard Steps section:
    "When verifying a bug fix that came through debug → fix-issue workflow:
    1. **Red** — Run the failing test from debug Step 1.5 BEFORE applying any fix. Confirm it fails.
    2. **Apply** — Confirm the fix is applied (check git diff).
    3. **Green** — Run the same test. Confirm it passes.
    4. **Regression** — Run the full test suite. Confirm no new failures.
    Evidence format: `[test name] pre-fix → FAIL (exit 1) | post-fix → PASS (exit 0)`
    This section only applies when debug Step 1.5 produced a test file. If reproduction was a screenshot/log, use standard golden-path verification instead."
  - Acceptance: verify/SKILL.md has "## Bug Fix Verification" section with Red/Apply/Green steps

- [ ] T021 [P] CLAUDE.md — routing fallback clause
  - Implements: TR-012
  - Depends: T001
  - Files: `builds/dream-studio/CLAUDE.md`
  - Content: After the routing tables, add a "### Routing Fallback" section:
    "If the user's intent does not match any trigger keyword in the tables above, route to `dream-studio:coach` with mode `route-classify`. Coach will classify the intent, map it to the nearest skill, and explain confidence + alternatives. This prevents unmatched intents from falling through to raw Claude behavior."
  - Acceptance: CLAUDE.md has "### Routing Fallback" section referencing `dream-studio:coach` and `route-classify`

- [ ] T022 [P] skills/coach/SKILL.md — route-classify mode
  - Implements: TR-012
  - Depends: T001
  - Files: `skills/coach/SKILL.md`
  - Content: Add `route-classify` to the Modes list:
    "`route-classify` — Classify an ambiguous user intent against all known dream-studio triggers. Returns top 3 skill matches with confidence scores and a recommended action. Use when no routing keyword matched (invoked by CLAUDE.md fallback). Dispatches `route-classifier` analyst."
  - Acceptance: coach/SKILL.md Modes section has `route-classify` entry

---

## Phase 7: P4 — Final wave (parallel, different files, after Phase 6 deps)

- [ ] T020 [P] workflows/fix-issue.yaml — write-failing-test conditional node
  - Implements: TR-005, TR-011
  - Depends: T002, T018
  - Files: `workflows/fix-issue.yaml`
  - Content: Add `write-failing-test` node between `create-issue` and `plan-fix`:
    ```yaml
    - id: write-failing-test
      depends_on: [create-issue]
      condition: "{{diagnose.testable}} == true"
      command: |
        Write a minimal failing test that encodes the reproduction from diagnose.
        File: tests/<area>/<bug-slug>_test.<ext>
        Test must fail before fix and pass after. Commit the test file.
      model: sonnet
      context: fresh
      timeout_seconds: 300
    ```
    Update `plan-fix` depends_on to include `write-failing-test`.
  - Acceptance: fix-issue.yaml has `write-failing-test` node with condition on `diagnose.testable`; plan-fix depends on it

- [ ] T023 [P] skills/coach/analysts/route-classifier.yml — new analyst file
  - Implements: TR-012
  - Depends: T022
  - Files: `skills/coach/analysts/route-classifier.yml` (new)
  - Content: Standard analyst YAML with signal scale, output schema. The analyst receives user input text and returns:
    ```json
    {
      "signal": "strong-accept | accept | neutral | reject | strong-reject",
      "confidence": 0.0-1.0,
      "reasoning": "What the user is trying to do and why this skill fits",
      "key_factors": [
        "Best match: dream-studio:X — because [reason]",
        "Alternative: dream-studio:Y — if the intent is [variant]",
        "Alternative: dream-studio:Z — if the intent is [variant]"
      ]
    }
    ```
    Signal meaning: strong-accept = high-confidence clear match; reject = no good match found, recommend Director clarify.
  - Acceptance: `skills/coach/analysts/route-classifier.yml` exists with signal field and key_factors

- [ ] T025 [P] skills/debug/SKILL.md — auto-learn suggestion at Step 6
  - Implements: TR-013
  - Depends: T018
  - Files: `skills/debug/SKILL.md`
  - Content: In Step 6 (Document), after the "Record what was tried and ruled out" instruction, add:
    "If the fix required more than 3 hypothesis iterations, or revealed a reusable pattern (a class of bug, a hidden invariant, a surprising interaction), invoke `learn:` to capture it. Describe what happened and why the standard approach failed."
  - Acceptance: debug/SKILL.md Step 6 contains "learn:" suggestion with the 3-hypothesis threshold

- [ ] T026 [P] skills/build/SKILL.md — auto-learn at checkpoint
  - Implements: TR-013
  - Depends: T015
  - Files: `skills/build/SKILL.md`
  - Content: In the Checkpoint section (Step 3), after the drift/blocker/context lines, add:
    "If any tasks in this wave resolved as `done_with_concerns` (concerns were addressed), append: 'Concerns resolved — suggest `learn: [topic]` to capture the pattern for future builds.'"
  - Acceptance: build/SKILL.md Checkpoint section contains `learn:` suggestion referencing `done_with_concerns`

---

## Phase 8: Final sequential

- [ ] T024 skills/coach/modes.yml — route-classify entry
  - Implements: TR-012
  - Depends: T023
  - Files: `skills/coach/modes.yml`
  - Content: Add route-classify mode entry with: analysts: [route-classifier], description: "Classify ambiguous intent against all skill triggers", quick_analysts: [route-classifier]
  - Acceptance: coach/modes.yml has `route-classify` key with analysts list

---

## Summary Table

| ID | File | Priority | Depends | [P]? |
|----|------|----------|---------|------|
| T001 | git branch | setup | — | — |
| T002 | workflows/fix-issue.yaml | P1-a | T001 | ✓ |
| T003 | skills/explain/* + CLAUDE.md | P1-b | T001 | ✓ |
| T004 | skills/core/orchestration.md | P2-a+b | T001 | — (bottleneck) |
| T005 | skills/build/SKILL.md | P2-a+b | T004 | ✓ w/ T006 |
| T006 | skills/review/SKILL.md | P2-a | T004 | ✓ w/ T005 |
| T007 | skills/core/repo-map.md + REGISTRY.md | P3-b | T001 | ✓ |
| T008 | skills/core/format.md | P3-c | T001 | ✓ |
| T009 | skills/build/config.yml | P3-c | T001 | ✓ |
| T010 | workflows/idea-to-pr.yaml | P3-a | T001 | ✓ |
| T011 | hooks/lib/skill_metrics.py | P3-f | T001 | ✓ |
| T012 | skills/core/orchestration.md | P3-b | T004, T007 | ✓ w/ T013 |
| T013 | skills/build/SKILL.md | P3-b | T005, T007 | ✓ w/ T012 |
| T014 | skills/build/SKILL.md | P3-c | T008, T013 | — |
| T015 | skills/build/SKILL.md | P3-d | T014 | — |
| T016 | .claude/settings.json | P3-f | T011 | ✓ |
| T017 | skills/core/orchestration.md | P3-e | T012 | ✓ |
| T018 | skills/debug/SKILL.md | P4-a | T001 | ✓ |
| T019 | skills/verify/SKILL.md | P4-a | T001 | ✓ |
| T020 | workflows/fix-issue.yaml | P4-a+TR-005 | T002, T018 | ✓ |
| T021 | CLAUDE.md | P4-b | T001 | ✓ |
| T022 | skills/coach/SKILL.md | P4-b | T001 | ✓ |
| T023 | skills/coach/analysts/route-classifier.yml | P4-b | T022 | ✓ |
| T024 | skills/coach/modes.yml | P4-b | T023 | — |
| T025 | skills/debug/SKILL.md | P4-c | T018 | ✓ |
| T026 | skills/build/SKILL.md | P4-c | T015 | ✓ |
