# Tasks: Workflow Coverage, Token Efficiency & Feature Activation

**Input**: `.planning/specs/workflow-coverage-and-efficiency/plan.md`
**Prerequisites**: plan.md (required), spec.md (required for designs)

## Format: `[ID] [P?] Description`
- **[P]**: Can run in parallel (different files, no dependencies)

---

## Wave 1: Foundation (Sessions 1-2) — No Dependencies

**Purpose**: Scripts and metadata that everything else builds on. All tasks in this wave write to distinct files and can run in parallel.

---

- [x] T001 [P] Delete dead code `hooks/lib/skill_metrics.py` — duplicate of `packs/meta/hooks/on-skill-metrics.py`

**Acceptance**: File deleted, no import errors anywhere (grep confirms no references)

---

- [x] T002 [P] Add `chain_suggests` frontmatter to all **core pack** SKILL.md files (9 files): `skills/core/modes/{think,plan,build,review,verify,ship,handoff,recap,explain}/SKILL.md`

**Details**: Add to each file's YAML frontmatter block:
```yaml
chain_suggests:
  - condition: "<from spec chain-suggest map>"
    next: "<skill>"
    prompt: "<suggestion text>"
```
Use the complete chain-suggest map from spec.md for exact values per skill.

**Acceptance**: All 9 files have valid `chain_suggests` in frontmatter; YAML parses without errors

---

- [x] T003 [P] Add `chain_suggests` frontmatter to all **quality pack** SKILL.md files (7 files): `skills/quality/modes/{debug,polish,harden,secure,structure-audit,learn,coach}/SKILL.md`

**Acceptance**: All 7 files have valid `chain_suggests` in frontmatter; YAML parses without errors

---

- [x] T004 [P] Add `chain_suggests` frontmatter to all **security pack** SKILL.md files: `skills/security/modes/{scan,dast,binary-scan,mitigate,comply,netcompat,dashboard}/SKILL.md`. Locate actual file paths first (security pack may use different directory structure).

**Acceptance**: All security skill SKILL.md files have valid `chain_suggests`; YAML parses

---

- [x] T005 [P] Add `chain_suggests` frontmatter to remaining packs — domains, career, analyze, setup. Locate actual SKILL.md files first. Skills with no chain (explain, coach, handoff) get `chain_suggests: []` to explicitly mark them as terminal.

**Acceptance**: Every SKILL.md in the project has `chain_suggests` in frontmatter (either populated or empty array)

---

- [x] T006 [P] Create `hooks/lib/repo_context.py` — project snapshot generator

**Details**:
- CLI: `py hooks/lib/repo_context.py [--project-root .] [--output path]`
- Scans project directory, produces JSON: tree, stack detection (language/framework/runtime/db/orm), entry_points, dependency counts, file_count, loc
- Stack detection heuristics: package.json → JS/TS, pyproject.toml → Python, Cargo.toml → Rust, wrangler.toml → Cloudflare, etc.
- Framework detection: look for astro.config, next.config, vite.config, django settings, etc.
- Output to stdout (JSON) or to `--output` path
- Stdlib only (os, json, pathlib, subprocess for `git status`)
- Cache invalidation: include a `git_hash` field (short SHA) so callers can check staleness

**Acceptance**: Run on dream-studio repo itself → produces valid JSON with correct stack info; run on a different project → produces valid JSON with different stack

---

- [x] T007 [P] Create `hooks/lib/findings_summarizer.py` — inter-node data compression

**Details**:
- CLI: `py hooks/lib/findings_summarizer.py <findings-file> [--format json|compact]`
- Parses markdown findings files (the format used by audit/review/scan nodes)
- Extracts: severity tags (Critical/High/Medium/Low), file paths, finding titles, fix suggestions
- Outputs structured JSON (see spec for schema) or compact one-line-per-finding format
- Handles missing files gracefully (outputs empty findings array)
- Handles varied finding formats: `[SEVERITY] file — description`, `**SEVERITY**: description`, table rows

**Acceptance**: Feed it a real `review-harden-findings.md` or `optimize-audit-deps.md` → produces valid JSON with correct severity counts; feed it a nonexistent file → produces `{"total": 0, "findings": []}`

---

- [x] T009 [P] Create `hooks/lib/model_selector.py` — SQLite-driven model selection

**Details**:
- CLI: `py hooks/lib/model_selector.py --skill=<name> [--default=sonnet]`
- Queries `sum_skill_summary` table in studio_db for the skill's historical success rate by model tier
- Decision logic:
  - If success_rate >= 95% with haiku → recommend haiku
  - If success_rate < 80% with current tier → recommend upgrade (haiku→sonnet, sonnet→opus)
  - If no history → return `--default` value
  - Architecture/complex analysis keywords → always recommend opus
- Outputs single word to stdout: `haiku`, `sonnet`, or `opus`
- Fails gracefully: if SQLite unavailable or table empty, returns `--default`
- Import from studio_db (existing module)

**Acceptance**: With populated SQLite → returns model recommendation; with empty/missing DB → returns default; output is always one of three valid model names

---

**Checkpoint**: Wave 1 complete. All foundation pieces exist. Verify: 5 new Python scripts run without errors, 22+ SKILL.md files have chain_suggests frontmatter, skill_metrics.py is deleted.

---

## Wave 2: Core Compilation Layer (Sessions 3-4) — Needs Wave 1

**Purpose**: The prompt compilation pipeline and skill-completion hook. These scripts transform how agents receive context.

---

- [x] T008 Create `hooks/lib/context_compiler.py` — minimal prompt compiler (depends on T006: repo_context.py)

**Details**:
- CLI: `py hooks/lib/context_compiler.py --skill=<mode> --pack=<pack> [--repo-context=<path>] [--project-root=.]`
- Reads the SKILL.md for the specified mode
- Parses sections by markdown header (##)
- Keeps: "Steps", "Output", "Rules" sections
- Drops: "Example Usage", "Template" boilerplate, "Trigger", "Used by" sections
- Reads gotchas.yml for the mode — includes only `avoid` items with severity >= high
- From orchestration.md — extracts model selection table + response handling rules only
- If `--repo-context` provided, inlines the JSON instead of project exploration instructions
- Outputs compiled markdown to stdout
- **Key constraint**: Output must be deterministic for same inputs (enables prompt caching)

**Acceptance**: Run with `--skill=build --pack=core` → output is <1200 words (vs ~4400 current); output is valid markdown; running twice with same inputs produces byte-identical output

---

- [ ] T010 Create `hooks/lib/prompt_assembler.py` — cache-optimized prompt builder (depends on T008: context_compiler.py)

**Details**:
- CLI: `py hooks/lib/prompt_assembler.py --template=<name> --static-context=<path> [--task-text=<text>] [--task-file=<path>] [--decisions=<text>]`
- Templates: `implementer`, `reviewer`, `auditor`, `explorer`
- Reads static context (output of context_compiler) as the STATIC PREFIX
- Appends dynamic content (task text, decisions) as DYNAMIC SUFFIX
- Separator between prefix and suffix: `═══════════════════════════════════════════`
- Each template adds role-specific framing:
  - `implementer`: "You are implementing task N. Write code, commit when done."
  - `reviewer`: "You are reviewing code against this spec. Report compliance."
  - `auditor`: "You are auditing this project. Report findings by severity."
  - `explorer`: "Answer this question about the codebase. Be concise."
- Outputs full assembled prompt to stdout

**Acceptance**: Two calls with same `--static-context` but different `--task-text` produce identical bytes before the separator and different bytes after; all 4 templates produce valid output

---

- [x] T011 [P] Create template definitions for prompt_assembler at `hooks/lib/prompt_templates/` — 4 markdown template files: `implementer.md`, `reviewer.md`, `auditor.md`, `explorer.md`

**Acceptance**: Each template file exists with role framing, output format spec, and placeholder markers for static/dynamic content

---

- [ ] T012 [P] Write unit tests for the prompt compilation pipeline: `tests/unit/test_context_compiler.py` and `tests/unit/test_prompt_assembler.py`

**Details**:
- Test context_compiler: deterministic output, section filtering, gotchas filtering, repo-context integration
- Test prompt_assembler: static prefix identity, template selection, separator placement
- Test findings_summarizer: various input formats, missing files, severity counting
- Follow existing test patterns in tests/unit/

**Acceptance**: `py -m pytest tests/unit/test_context_compiler.py tests/unit/test_prompt_assembler.py` passes

---

- [x] T013 [P] Write unit test for repo_context.py: `tests/unit/test_repo_context.py`

**Acceptance**: Tests cover: stack detection heuristics, output schema validation, missing project root, git hash inclusion

---

- [ ] T014 Create `packs/meta/hooks/on-skill-complete.py` — chain-suggest advisory hook (depends on T002-T005: chain_suggests metadata)

**Details**:
- Trigger: PostToolUse on Skill tool (add to hooks.json)
- Reads the skill name from tool_input
- Locates the skill's SKILL.md file
- Parses `chain_suggests` from YAML frontmatter
- Evaluates condition:
  - `always` → always suggest
  - `ui_build` → check if recent Edit/Write touched .tsx/.vue/.svelte/.astro/.css files (read activity.json from on-tool-activity)
  - `findings_found` → check if findings file exists in cwd (review-*-findings.md, audit-*.md)
  - `critical_findings` → check if findings file contains "Critical" or "High" severity tags
  - `root_cause_found` → check if debug output contains "root cause" text
- If condition met, print: `→ [<next_skill>] <prompt text>`
- Log suggestion to `~/.dream-studio/state/chain-suggestions.jsonl`: timestamp, skill, suggested_next, condition, accepted (null — filled later if user follows suggestion)
- **Never auto-invoke** — advisory only

**Acceptance**: After running `dream-studio:core think`, hook prints "→ [plan] Spec approved — plan the tasks?"; after running a non-UI build, hook does NOT suggest polish; hook writes to chain-suggestions.jsonl

---

- [x] T015 [P] Create `hooks/lib/session_cache.py` — session file server

**Details**:
- CLI: `py hooks/lib/session_cache.py --session-dir <path> --query <filename>`
- Reads the specified file from the session directory
- Outputs contents to stdout
- If file doesn't exist, outputs empty string (no error)
- If `--query` is `*` or `all`, outputs all files concatenated with `---` separators and filename headers
- Lightweight: no caching beyond what the OS provides (this script runs once per template resolution, not in a loop)

**Acceptance**: Query existing session file → returns contents; query missing file → returns empty; query all → returns concatenated output

---

**Checkpoint**: Wave 2 complete. The full prompt compilation pipeline works end-to-end. Verify: `repo_context.py | context_compiler.py | prompt_assembler.py` produces a valid agent prompt <1200 words.

---

## Wave 3: Workflow Engine Integration (Session 5) — Needs Wave 2

**Purpose**: Wire the Python scripts into the workflow engine and build mode so they're used automatically.

---

- [ ] T016 Add `{{session:<filename>}}` template syntax to `hooks/lib/workflow_engine.py` (depends on T015: session_cache.py)

**Details**:
- In the template resolution logic (where `{{node.output}}` is resolved), add a new pattern: `{{session:<filename>}}`
- Resolution: call `session_cache.py --session-dir <workflow-session-dir> --query <filename>`
- Inline the returned content into the node's command/input text
- If session_cache returns empty, leave the template as-is (downstream node handles missing data)

**Acceptance**: A workflow YAML with `{{session:optimize-baseline.md}}` resolves to the file's contents; workflow runs without error

---

- [ ] T017 [P] Add `output_compress` node property to `hooks/lib/workflow_engine.py` (depends on T007: findings_summarizer.py)

**Details**:
- When a node completes and has `output_compress: findings` in its YAML definition:
  1. Write the raw output to the session file as usual
  2. Also call `findings_summarizer.py <output-file> --format json`
  3. Store the compressed JSON as the node's resolved output for `{{node.output}}` templates
- If findings_summarizer fails, fall back to raw output (no error, just skip compression)
- Only `findings` compression type for now (extensible later)

**Acceptance**: A workflow node with `output_compress: findings` produces compressed JSON in `{{node.output}}` resolution; without the property, behavior is unchanged

---

- [ ] T018 Update `hooks/lib/workflow_state.py` — call repo_context on workflow start (depends on T006: repo_context.py)

**Details**:
- In the `start` command handler, after creating the workflow state entry:
  1. Call `repo_context.py --project-root <cwd> --output <session-dir>/repo-context.json`
  2. Store the output path in the workflow state dict under `repo_context_path`
- If repo_context fails, continue without it (non-blocking)
- The repo_context.json is then available to nodes via `{{session:repo-context.json}}`

**Acceptance**: Starting a workflow creates repo-context.json in the session directory; workflow state includes `repo_context_path`

---

- [ ] T019 [P] Write integration test for workflow engine template resolution: `tests/integration/test_workflow_session_template.py`

**Acceptance**: Test creates a mock session dir with files, runs template resolution with `{{session:*}}`, verifies correct content inline

---

- [ ] T020 Extend `hooks/lib/workflow_cost.py` with pre-run cost gate (depends on T009: model_selector.py)

**Details**:
- Add function `pre_run_cost_gate(workflow_data, context_pct=None)`:
  1. Call `estimate_workflow_cost()` (existing) for YAML-based estimates
  2. For each node with a `skill` property, call `model_selector.py --skill=<name>` to get recommended model
  3. If `context_pct` provided (from context-threshold bridge), calculate estimated fill percentage
  4. Format the cost table (see spec for exact format)
  5. Return the formatted string for the workflow runner to print
- Add CLI entry point: `py hooks/lib/workflow_cost.py --gate <yaml-path> [--context-pct <N>]`
- Do NOT auto-block — just inform. The workflow runner decides whether to ask for confirmation.

**Acceptance**: `py hooks/lib/workflow_cost.py --gate workflows/optimize.yaml` prints a formatted cost table with per-node estimates, total, and model recommendations

---

- [ ] T021 Update `skills/core/modes/build/SKILL.md` — document prompt_assembler usage for subagent dispatch

**Details**:
- In the "Execute each task" section, add instructions for using prompt_assembler when available:
  1. Before spawning implementer agent: run `context_compiler.py` → `prompt_assembler.py --template=implementer`
  2. Use the assembled prompt as the agent's prompt instead of inline SKILL.md reading
  3. If scripts unavailable (error, missing), fall back to current behavior
- Do NOT change the existing behavior — this is additive (use if available)

**Acceptance**: Build SKILL.md documents the prompt_assembler pattern; existing builds still work if scripts are missing

---

- [ ] T022 [P] Update `skills/core/orchestration.md` — add "Compiled Prompt Pattern" section

**Details**:
- Add a new section after "Implementer Prompt Template" documenting the compiled prompt approach
- Include: when to use (workflow nodes, build waves), how to invoke, fallback behavior
- Update the model selection table to reference model_selector.py as an alternative to hardcoded tiers

**Acceptance**: orchestration.md has new section that matches the spec's Python Context Efficiency Layer design

---

- [ ] T023 [P] Add `on-skill-complete` hook entry to `hooks/hooks.json` (depends on T014: the hook script)

**Details**:
- Add a PostToolUse entry for the Skill tool matcher that runs `packs/meta/hooks/on-skill-complete.py`
- Place it AFTER the existing `on-skill-metrics` entry (metrics should log first, then suggest)
- Matcher: `tool_name: Skill`

**Acceptance**: hooks.json includes the new entry; hook fires after a Skill tool completes

---

**Checkpoint**: Wave 3 complete. Workflow engine uses session caching and output compression automatically. Pre-run cost gate is available. Build mode can use compiled prompts.

---

## Wave 4: New Workflows + Existing Optimizations (Sessions 6-7) — Needs Wave 3

**Purpose**: Create the 3 new workflows using the efficiency layer, and optimize 3 existing workflows.

---

- [ ] T025 Create `workflows/audit-to-fix.yaml` — generic audit → plan → build chain

**Details**:
- Parameterized by audit type (harden, secure, structure-audit, scan) — node 1 invokes the specified audit skill
- Nodes: audit → synthesize (with `output_compress: findings`) → plan → [Director gate] → build → verify → report
- Use `{{session:*}}` for inter-node data passing
- Include `estimated_tokens` on each node
- Model tiers: audit=sonnet, synthesize=haiku, plan=sonnet, build=sonnet, verify=haiku, report=haiku

**Acceptance**: `workflow: audit-to-fix audit=harden` runs end-to-end on a test project; Director gate pauses correctly; synthesize node uses compressed findings

---

- [ ] T026 [P] Create `workflows/ui-feature.yaml` — UI-aware build pipeline with polish

**Details**:
- Nodes: think → plan → build → polish → review → verify → ship
- Polish node: `skill: polish`, `model: sonnet`, runs ONLY when build output touches UI files
- Condition on polish: `{{build.ui_files_changed}} == true`
- Build node must output `ui_files_changed: true|false` in its verdict
- Use `{{session:*}}` for repo-context
- Director gates after think and plan (same as idea-to-pr)

**Acceptance**: Workflow runs on a UI project and invokes polish; runs on an API project and skips polish

---

- [ ] T027 [P] Create `workflows/client-deliverable.yaml` — PLMarketing delivery pipeline

**Details**:
- Nodes: intake (capture requirements) → plan → build (powerbi/flow/app) → validate (data checks) → screenshot → summary-doc → [Director gate] → deliver (commit + PR)
- Intake node: command that extracts requirements from user input into structured format
- Validate node: runs data validation checks appropriate to the deliverable type
- Screenshot node: captures key visuals (uses Playwright if available, instructions otherwise)
- Summary-doc node: generates a delivery summary document
- Model tiers: intake=haiku, plan=sonnet, build=sonnet, validate=haiku, screenshot=haiku, summary=haiku, deliver=haiku

**Acceptance**: Workflow runs end-to-end for a Power BI deliverable; produces summary doc; Director gate pauses before delivery

---

- [ ] T028 Optimize `workflows/project-audit.yaml` — parallel regroup

**Details**:
- Change harden, secure, review from sequential (with gates between) to parallel (with single gate before report)
- Remove `after-harden` and `after-secure` gates
- Add single `review-findings` gate before report node
- Keep `trigger_rule: all_done` on report node
- Update report node command to handle any combination of findings (some may be missing if parallel node failed)

**Acceptance**: project-audit runs all 3 audits in parallel; report synthesizes correctly; total time reduced vs. sequential

---

- [ ] T029 [P] Optimize `workflows/optimize.yaml` — short-circuit conditions

**Details**:
- Add `condition` to audit-infra: skip if profile node reports no Docker/Cloudflare/CI config
- Add `condition` to audit-queries: skip if profile node reports no data layer
- Update profile node command to output structured flags: `has_infra: true|false`, `has_data_layer: true|false`
- Add `output_compress: findings` to all audit nodes

**Acceptance**: Running optimize on a project without Docker/Cloudflare skips audit-infra; running on a project without ORM skips audit-queries; audit nodes output compressed findings

---

- [ ] T030 [P] Optimize `workflows/idea-to-pr.yaml` — model tier downgrades

**Details**:
- Change plan node: `model: opus` → `model: sonnet`
- Keep think node at opus (architecture judgment needs it)
- Add `output_compress: findings` to all review nodes (review-code, review-security, review-tests, review-perf, review-docs)

**Acceptance**: idea-to-pr runs successfully with plan on sonnet; review nodes produce compressed findings for synthesize node

---

- [ ] T031 Verification run — end-to-end test of the full system

**Details**:
- Run `workflow: audit-to-fix audit=harden` on dream-studio itself
- Verify: repo_context.py generates snapshot, cost gate shows estimates, findings are compressed, chain-suggest fires after completion
- Run `workflow list` and verify all new workflows appear with token estimates
- Check `~/.dream-studio/state/chain-suggestions.jsonl` has entries from the run

**Acceptance**: Full workflow completes; token estimates appear pre-run; compressed findings used between nodes; chain-suggest logged

---

**Checkpoint**: Wave 4 complete. Full system operational. All 13 success criteria from spec should be met.

---

## Dependencies & Execution Order

### File Ownership (no conflicts within waves)

**Wave 1** (all parallel):
- T001: `hooks/lib/skill_metrics.py` (DELETE)
- T002: `skills/core/modes/*/SKILL.md` (9 files)
- T003: `skills/quality/modes/*/SKILL.md` (7 files)
- T004: `skills/security/modes/*/SKILL.md`
- T005: `skills/domains/`, `skills/career/`, `skills/analyze/`, `skills/setup/` SKILL.md files
- T006: `hooks/lib/repo_context.py` (NEW)
- T007: `hooks/lib/findings_summarizer.py` (NEW)
- T009: `hooks/lib/model_selector.py` (NEW)

**Wave 2** (sequential where noted):
- T008: `hooks/lib/context_compiler.py` (NEW) — after T006
- T010: `hooks/lib/prompt_assembler.py` (NEW) — after T008
- T011: `hooks/lib/prompt_templates/*.md` (NEW) — parallel with T010
- T012: `tests/unit/test_context_compiler.py`, `test_prompt_assembler.py` (NEW)
- T013: `tests/unit/test_repo_context.py` (NEW)
- T014: `packs/meta/hooks/on-skill-complete.py` (NEW) — after T002-T005
- T015: `hooks/lib/session_cache.py` (NEW) — parallel

**Wave 3** (sequential where noted):
- T016: `hooks/lib/workflow_engine.py` (MODIFY) — after T015
- T017: `hooks/lib/workflow_engine.py` (MODIFY) — after T007, SAME FILE as T016 → sequential
- T018: `hooks/lib/workflow_state.py` (MODIFY) — after T006
- T019: `tests/integration/test_workflow_session_template.py` (NEW)
- T020: `hooks/lib/workflow_cost.py` (MODIFY) — after T009
- T021: `skills/core/modes/build/SKILL.md` (MODIFY) — after T010
- T022: `skills/core/orchestration.md` (MODIFY) — parallel with T021
- T023: `hooks/hooks.json` (MODIFY) — after T014

**Wave 4** (mostly parallel):
- T025: `workflows/audit-to-fix.yaml` (NEW)
- T026: `workflows/ui-feature.yaml` (NEW)
- T027: `workflows/client-deliverable.yaml` (NEW)
- T028: `workflows/project-audit.yaml` (MODIFY)
- T029: `workflows/optimize.yaml` (MODIFY)
- T030: `workflows/idea-to-pr.yaml` (MODIFY)
- T031: verification (no files, just execution)

### Critical Path

T006 (repo_context) → T008 (context_compiler) → T010 (prompt_assembler) → T021 (build mode update) → T031 (verification)

This is the longest dependency chain: 5 tasks across 4 waves. Everything else can be parallelized around it.

---

## Summary Table

| # | Task | Wave | Effort | Files |
|---|------|------|--------|-------|
| T001 | Delete dead skill_metrics.py | 1 | trivial | hooks/lib/skill_metrics.py |
| T002 | Chain-suggest: core pack (9 files) | 1 | low | skills/core/modes/*/SKILL.md |
| T003 | Chain-suggest: quality pack (7 files) | 1 | low | skills/quality/modes/*/SKILL.md |
| T004 | Chain-suggest: security pack | 1 | low | skills/security/modes/*/SKILL.md |
| T005 | Chain-suggest: remaining packs | 1 | low | skills/{domains,career,analyze,setup}/*/SKILL.md |
| T006 | repo_context.py | 1 | medium | hooks/lib/repo_context.py |
| T007 | findings_summarizer.py | 1 | medium | hooks/lib/findings_summarizer.py |
| T009 | model_selector.py | 1 | low | hooks/lib/model_selector.py |
| T008 | context_compiler.py | 2 | high | hooks/lib/context_compiler.py |
| T010 | prompt_assembler.py | 2 | medium | hooks/lib/prompt_assembler.py |
| T011 | Prompt templates (4 files) | 2 | low | hooks/lib/prompt_templates/*.md |
| T012 | Unit tests: compiler + assembler | 2 | medium | tests/unit/test_*.py |
| T013 | Unit test: repo_context | 2 | low | tests/unit/test_repo_context.py |
| T014 | on-skill-complete hook | 2 | medium | packs/meta/hooks/on-skill-complete.py |
| T015 | session_cache.py | 2 | low | hooks/lib/session_cache.py |
| T016 | workflow_engine: {{session:*}} | 3 | medium | hooks/lib/workflow_engine.py |
| T017 | workflow_engine: output_compress | 3 | medium | hooks/lib/workflow_engine.py |
| T018 | workflow_state: repo_context on start | 3 | low | hooks/lib/workflow_state.py |
| T019 | Integration test: session templates | 3 | low | tests/integration/test_workflow_session_template.py |
| T020 | Pre-run cost gate | 3 | medium | hooks/lib/workflow_cost.py |
| T021 | Build mode: prompt_assembler docs | 3 | low | skills/core/modes/build/SKILL.md |
| T022 | orchestration.md: compiled prompt docs | 3 | low | skills/core/orchestration.md |
| T023 | hooks.json: add on-skill-complete | 3 | trivial | hooks/hooks.json |
| T025 | audit-to-fix.yaml workflow | 4 | medium | workflows/audit-to-fix.yaml |
| T026 | ui-feature.yaml workflow | 4 | medium | workflows/ui-feature.yaml |
| T027 | client-deliverable.yaml workflow | 4 | medium | workflows/client-deliverable.yaml |
| T028 | Optimize project-audit.yaml | 4 | low | workflows/project-audit.yaml |
| T029 | Optimize optimize.yaml | 4 | low | workflows/optimize.yaml |
| T030 | Optimize idea-to-pr.yaml | 4 | low | workflows/idea-to-pr.yaml |
| T031 | Verification run | 4 | medium | (none — execution only) |
