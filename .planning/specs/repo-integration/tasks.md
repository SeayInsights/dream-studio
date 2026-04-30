# Tasks: Repo Integration — 4 External Repos → dream-studio

**Input**: `.planning/specs/repo-integration/plan.md`  
**Rule**: Every task is additive only. Read existing file before any update. Never remove existing content.  
**Commit strategy**: One commit per task. Message format: `chore(repo-integration): <description>`

---

## Phase A: New Reference Files

**Purpose**: Create standalone reference documents. Zero conflict risk — all pure additions.  
**All tasks in this phase are [P] — different files, no shared state.**

---

### A1 — skills/design/references/ (8 new files from impeccable)

Fetch source content from `https://raw.githubusercontent.com/pbakaus/impeccable/main/source/skills/impeccable/reference/<filename>`, adapt to dream-studio markdown style (strip platform-specific framing, keep principles and examples).

- [ ] T001 [P] Create `skills/design/references/typography.md` — type systems, font pairing, modular scales, OpenType features, what to avoid (source: impeccable/reference/typography.md, adapt content)
  **Acceptance**: File exists, contains sections on type scale, font pairing, OpenType, avoid-list.

- [ ] T002 [P] Create `skills/design/references/color-and-contrast.md` — OKLCH color space, tinted neutrals, dark mode token strategy, accessibility ratios (source: impeccable/reference/color-and-contrast.md)
  **Acceptance**: File exists, contains OKLCH guidance, dark mode section, WCAG contrast ratios.

- [ ] T003 [P] Create `skills/design/references/spatial-design.md` — spacing systems, 4/8px grids, visual hierarchy, density modes (source: impeccable/reference/spatial-design.md)
  **Acceptance**: File exists, contains spacing scale, grid system, density guidance.

- [ ] T004 [P] Create `skills/design/references/motion-design.md` — easing curves, stagger patterns, timing guidelines, reduced-motion handling, what not to do (source: impeccable/reference/motion-design.md)
  **Acceptance**: File exists, contains easing curve reference, reduced-motion section, avoid-list.

- [ ] T005 [P] Create `skills/design/references/interaction-design.md` — form patterns, focus states, loading states, error states, empty states (source: impeccable/reference/interaction-design.md)
  **Acceptance**: File exists, contains form UX, focus state guidance, loading/error/empty state patterns.

- [ ] T006 [P] Create `skills/design/references/responsive-design.md` — mobile-first approach, fluid design, container queries, breakpoint strategy (source: impeccable/reference/responsive-design.md)
  **Acceptance**: File exists, contains mobile-first principle, container query examples, breakpoint guidance.

- [ ] T007 [P] Create `skills/design/references/ux-writing.md` — button label rules, error message format, empty state copy, microcopy principles (source: impeccable/reference/ux-writing.md)
  **Acceptance**: File exists, contains button label guidance, error message format, empty state examples.

- [ ] T008 [P] Create `skills/design/references/anti-patterns.md` — comprehensive list of design anti-patterns to avoid. Expand on impeccable's list to include dream-studio's existing anti-slop rules. (Combine impeccable anti-patterns + existing anti-slop rules from skills/design/SKILL.md into one unified reference)
  **Acceptance**: File exists, contains 20+ anti-patterns with brief explanations, organized by category (typography, color, layout, motion, copy).

---

### A2 — skills/domains/design/ (4 new YML files)

Follow the YAML format convention of existing files in this directory (e.g., `typography-standards.yml`, `color-standards.yml`).

- [ ] T009 [P] Create `skills/domains/design/motion-design.yml` — easing curve standards, stagger specifications, timing budgets, reduced-motion requirements. Model structure on `layout-standards.yml`.
  **Acceptance**: File exists, valid YAML, contains easing, timing, and reduced-motion standards.

- [ ] T010 [P] Create `skills/domains/design/interaction-design.yml` — focus state standards, form interaction patterns, loading state specifications, touch target sizes. Model structure on `layout-standards.yml`.
  **Acceptance**: File exists, valid YAML, contains focus, form, loading, and touch target specs.

- [ ] T011 [P] Create `skills/domains/design/ux-writing.yml` — microcopy standards, button label rules (do/don't pairs), error message format, empty state copy formula. Model structure on existing domain YMLs.
  **Acceptance**: File exists, valid YAML, contains button labels, error format, empty state guidance.

- [ ] T012 [P] Create `skills/domains/design/anti-patterns.yml` — consolidated design anti-patterns for cross-skill use. List with: pattern name, what it looks like, why it's harmful, what to do instead.
  **Acceptance**: File exists, valid YAML, 20+ entries, each with name/example/fix fields.

---

### A3 — skills/domains/design/ (2 file enrichments)

- [ ] T013 [P] Update `skills/domains/design/typography-standards.yml` — read existing file first, then append new sections: OKLCH-aware type color guidance, OpenType feature recommendations (ligatures, tabular nums for data), font pairing principles (display + body), scale ratios (1.25 minor third, 1.333 perfect fourth). Do not modify existing entries.
  **Acceptance**: File has new appended sections; all original content intact; valid YAML.

- [ ] T014 [P] Update `skills/domains/design/color-standards.yml` — read existing file first, then append: OKLCH color space guidance, tinted neutral palette pattern, dark mode token strategy (semantic tokens not raw values), P3 wide-gamut considerations. Do not modify existing entries.
  **Acceptance**: File has new appended sections; all original content intact; valid YAML.

---

## Phase B: New Templates / Checklists / Analysts

**Purpose**: Create supporting files that Phase C SKILL.md updates will reference.  
**All tasks are [P] — different files and directories, no shared state.**  
**Depends on**: Phase A complete (T001-T014)

---

- [ ] T015 [P] Create `skills/think/templates/design-template.md` — architecture decision doc template for complex features. Sections: System Overview, Component Breakdown, Key Decisions (decision + rationale + alternatives considered), Integration Points, Data Flow, Known Constraints. Include frontmatter and usage note.
  **Acceptance**: File exists, has all 6 sections with placeholder text, includes usage instructions at top.

- [ ] T016 [P] Create `skills/build/templates/agent-prompts/tdd-loop.md` — TDD agent prompt template. Follows the format/style of existing `implementer.md` and `reviewer.md` in same directory. Content: write failing test → confirm red → implement minimum → confirm green → refactor → confirm still green. Include JSON output schema matching other agent prompts.
  **Acceptance**: File exists, follows same format as implementer.md/reviewer.md, covers red→green→refactor cycle, has JSON output schema.

- [ ] T017 [P] Create `skills/ship/templates/archive-stamp-template.md` — spec archive record. Fields: status (shipped/cancelled), shipped_date (ISO-8601), merge_sha, pr_url, summary (1-2 sentences), spec_path. Markdown format with frontmatter.
  **Acceptance**: File exists, contains all 6 fields with placeholder values, includes usage note.

- [ ] T018 [P] Create `skills/polish/checklists/design-anti-patterns.yml` — YAML checklist following the format of existing checklists in this directory (e.g., `web-design.yml`). Pull the 24 impeccable anti-patterns plus dream-studio's existing anti-slop rules. Format: each entry has `id`, `description`, `check`, `fix`.
  **Acceptance**: File exists, follows same YAML structure as web-design.yml, 20+ entries, each with id/description/check/fix.

- [ ] T019 [P] Create `skills/coach/analysts/zoom-out.yml` — coach analyst YAML following the format of existing analysts (e.g., `workflow-fit.yml`). Analyst purpose: detect scope creep and validate we're solving the right problem. Questions to ask: Is the original goal still the goal? Has scope grown past the spec? Are we building the right thing for the right person? Output: signal (strong-accept to strong-reject) with key_factors.
  **Acceptance**: File exists, follows same YAML structure as workflow-fit.yml, contains purpose, questions, output schema, signal scale.

- [ ] T020 [P] Create `skills/harden/templates/` directory and `skills/harden/templates/context-template.md` — CONTEXT.md domain vocabulary template. Sections: Project Domain Terms (table: term | definition | example), Abbreviations, What Words Mean Here (disambiguation), What This Is Not (scope boundaries). Include a filled example row in each table.
  **Acceptance**: Directory created, file exists, has 4 sections, each section has at least one example row.

- [ ] T021 [P] Update `skills/think/templates/spec-template.md` — read existing file first, then append (do not replace): a new "Acceptance Criteria" section between Success Criteria and Edge Cases. Format: AC-001, AC-002 style, "Given / When / Then" format. Add example. Also append a "PRD Context" optional section (problem statement, target user, business goal).
  **Acceptance**: Existing spec-template.md content intact; two new sections appended (Acceptance Criteria, PRD Context); new sections have examples.

- [ ] T022 [P] Update `skills/plan/templates/tasks-template.md` — read existing file first. In the Format section, expand the task format to add optional `[owner:name]` and `[est:Xh]` tags after the existing `[P?]` and `[Story]` markers. Update the format legend. Add one example task showing all optional fields. Do not change the existing sample tasks or structure.
  **Acceptance**: Existing tasks-template.md content intact; Format section updated with owner+estimate tags; format legend updated; one example showing new fields.

---

## Phase C: SKILL.md Updates

**Purpose**: Add new sections to 12 SKILL.md files. Additive only — append or insert, never replace.  
**Depends on**: Phase A (T001-T014) + Phase B (T015-T022) complete.  
**Protocol for every task**: (1) Read full SKILL.md, (2) identify insertion point, (3) append/insert only, (4) verify original content unchanged, (5) commit.

All Phase C tasks write to different files and can run in parallel within sub-waves. Split into 3 waves of 4 for agent safety.

---

### C1 — Wave 1 (think, plan, build, debug)

- [ ] T023 [P] Update `skills/think/SKILL.md` — two additions:
  1. In Step 1 (Clarify), add a structured questioning block: before writing spec, ask 3-5 targeted questions to surface hidden constraints (source: mattpocock grill-me pattern). Format: "Clarify Questions" sub-block with examples.
  2. In the Output section, add: "For complex features, also output `design-template.md` to `.planning/specs/<topic>/design.md`" with link to new template.
  **Acceptance**: Both additions present; original 5-step flow and all existing content intact.

- [ ] T024 [P] Update `skills/plan/SKILL.md` — one addition:
  After Step 9 (Write traceability registry), add Step 10: "Auto-issues (optional) — If Director approves, run `gh issue create` for each task in tasks.md. Use task description as title, acceptance criteria as body. Link issues back in tasks.md with `[#issue]` tag." (source: mattpocock to-issues)
  **Acceptance**: Step 10 present; Steps 1-9 and all existing content intact.

- [ ] T025 [P] Update `skills/build/SKILL.md` — two additions:
  1. In Execution Modes section, add `[build:tdd]` as a third mode after Subagent mode: "Trigger with `build:tdd` flag. For each task, dispatch tdd-loop.md agent prompt instead of implementer.md. Write failing test first, confirm red, implement, confirm green, refactor." Reference `templates/agent-prompts/tdd-loop.md`.
  2. In Step 2 (Execute each task), add spec-tracking note: "When a task implements a functional requirement, note `FR-XXX: implemented` in the commit message body if traceability is active."
  **Acceptance**: [build:tdd] mode present in Execution Modes; spec-tracking note present in Step 2; all existing content intact.

- [ ] T026 [P] Update `skills/debug/SKILL.md` — two additions:
  1. Add Step 0.5 between the "Before you start" block and Step 1: "**Triage** — Before reproducing, classify the issue: severity (P0 blocker / P1 high / P2 medium / P3 low), type (logic error / UI rendering / performance / data / integration), scope (single file / cross-module / infrastructure). Log as `Triage: P1 | logic | cross-module`." (source: mattpocock triage)
  2. After the Rules section, add a "React/Next.js projects" conditional block: "If the project uses React or Next.js, before Step 1 (Reproduce): run `next-browser errors` to pull live React errors; use `next-browser snapshot` to inspect component tree; use `next-browser network` to trace failed requests. These replace log-reading when the app is running."
  **Acceptance**: Step 0.5 triage present; React conditional block present; original steps 1-6 and all content intact.

---

### C2 — Wave 2 (verify, ship, harden, design)

- [ ] T027 [P] Update `skills/verify/SKILL.md` — extend the "Verification by domain" section's Web/SaaS entry. After the existing "open browser, test forms, responsive, a11y" line, add:
  - `npx impeccable detect` — runs design quality scan against the project, reports anti-pattern violations. Run before claiming UI is clean.
  - For React/Next.js: `next-browser snapshot` (component render check), `next-browser accessibility` (ARIA violations), `next-browser profile` (Core Web Vitals), and interaction testing with `next-browser click/fill` for key user paths.
  **Acceptance**: Both additions present in Web/SaaS section; all existing verification steps and content intact.

- [ ] T028 [P] Update `skills/ship/SKILL.md` — two additions:
  1. In the Gate checklist section (or after it), add: "**CWV check (frontend projects)**: Run `next-browser profile` to verify Core Web Vitals before deploy. LCP < 2.5s, FID < 100ms, CLS < 0.1. Any fail blocks ship."
  2. After the Rules section, add an Archive step: "**Post-ship archive**: After successful deploy, move `.planning/specs/<topic>/` to `.planning/archive/<topic>/`. Create `archive-stamp.md` using `templates/archive-stamp-template.md` — fill in status: shipped, date, merge SHA, PR URL, one-line summary."
  **Acceptance**: CWV check present; archive step present; all existing rules and gate content intact.

- [ ] T029 [P] Update `skills/harden/SKILL.md` — one addition:
  In the "Project memory system (always first)" section, add CONTEXT.md as a 4th required file after GOTCHAS.md:
  - Check: does `CONTEXT.md` exist in project root?
  - If missing: create from `skills/harden/templates/context-template.md`
  - Stub content: "# Context\n\n## Domain Terms\n[Fill in: project-specific vocabulary, abbreviations, what words mean here]\n\nSee `skills/harden/templates/context-template.md` for full template."
  - Explanation: "CONTEXT.md is the shared domain vocabulary. It prevents AI verbosity and drift by defining what project-specific terms mean in this codebase."
  **Acceptance**: CONTEXT.md check present as 4th item; stub content provided; original 3-file checks intact.

- [ ] T030 [P] Update `skills/design/SKILL.md` — three additions:
  1. After the "Anti-slop rules" section, add a "Design Reference Modules" section: "For deep guidance on any design dimension, consult the reference modules in `references/`:" — list all 7 files with one-line descriptions.
  2. After the Junior Designer Workflow section, add `/critique` mode: "**`/critique` mode** — Run the output against all 7 reference modules. Score each dimension. List violations with reference citations. Produce prioritized fix list."
  3. After `/critique`, add `/animate` mode: "**`/animate` mode** — Apply motion design guidance from `references/motion-design.md`. Add entrance animations (fade+translate), hover feedback, loading states. Follow easing and timing standards. Check reduced-motion."
  **Acceptance**: All 3 additions present; 7 reference files listed; original SKILL.md content intact.

---

### C3 — Wave 3 (polish, coach, workflow, mcp-build)

- [ ] T031 [P] Update `skills/polish/SKILL.md` — one addition:
  In Step 2 (Fix), in the Color dimension block, after the existing "Replace failing contrast, apply 60/30/10 rule, check anti-slop list" line, add: "Load `checklists/design-anti-patterns.yml` and run each check. Flag any violations and add to priority fix list."
  **Acceptance**: Anti-patterns checklist reference present in Color fix block; all existing Step 1/2/3 content intact.

- [ ] T032 [P] Update `skills/coach/SKILL.md` — two additions:
  1. Add `zoom-out` to the Modes list: "- `zoom-out` — Scope health check: are we still solving the right problem? Detects scope creep, goal drift, and solution-problem mismatch. Run when a build feels larger than the original spec."
  2. In Step 4 (Dispatch Analyst Subagents), add: "For `zoom-out` mode: dispatch the `analysts/zoom-out.yml` analyst."
  **Acceptance**: zoom-out in modes list; zoom-out dispatch present in Step 4; all existing modes and steps intact.

- [ ] T033 [P] Update `skills/workflow/SKILL.md` — one addition:
  Read current SKILL.md. Add a "Communication Modes" section: "**Caveman mode** — When verbosity is a problem, toggle compressed communication: one-word status updates, no explanations, no summaries, no preamble. Activate by user saying `caveman mode on`. Deactivate with `caveman mode off`. In caveman mode: respond with action done, nothing else." (source: mattpocock caveman skill)
  **Acceptance**: Caveman mode section present; file has no content removed.

- [ ] T034 [P] Update `skills/mcp-build/SKILL.md` — one addition:
  Read current SKILL.md. Add a "CLI-to-Skill Bridge Pattern" section: "When building an MCP that wraps a CLI tool, follow the daemon model used by next-browser (vercel-labs/next-browser): (1) launch daemon once at session start (not per-call), (2) communicate via JSON-RPC over a socket (Unix domain socket or Windows named pipe), (3) design CLI commands to be stateless and machine-readable — one command in, structured output out, (4) expose as skill commands with typed inputs/outputs. This eliminates per-command startup overhead and enables agent loops to fire rapid commands."
  **Acceptance**: CLI-to-skill bridge section present; daemon model described; next-browser cited as reference; no content removed.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase A** (T001-T014): No dependencies — start immediately. All [P].
- **Phase B** (T015-T022): No dependencies on A (B creates different files). All [P]. Can run in parallel with A.
- **Phase C** (T023-T034): Depends on Phase A + B complete (SKILL.md updates reference the new files).

### Within Phase C

All 12 tasks write to different SKILL.md files — no file conflicts.  
Split into 3 waves of 4 for agent safety (not file-dependency reasons):
- Wave C1: T023-T026
- Wave C2: T027-T030  
- Wave C3: T031-T034

### Parallel Summary

```
Wave 1 (immediate): T001-T014 in parallel [Phase A]
                    + T015-T022 in parallel [Phase B]  ← same time as A
                                  ↓
Wave 2: T023-T026 in parallel [Phase C Wave 1]
                                  ↓
Wave 3: T027-T030 in parallel [Phase C Wave 2]
                                  ↓
Wave 4: T031-T034 in parallel [Phase C Wave 3]
```

Total: 34 tasks, 4 execution waves.

---

## Notes

- [P] = different files, no dependency — safe to run as parallel subagents
- Every SKILL.md task: Read → append/insert → verify original intact → commit
- For impeccable content: fetch from raw GitHub URL, adapt phrasing to dream-studio idiom
- For mattpocock patterns: synthesize from README/skill description, don't copy verbatim
- For OpenSpec patterns: synthesize the principle (archive, design.md), not the Node.js CLI
- For next-browser: reference the CLI commands by name, note "requires next-browser installed"
- harden/templates/ directory does not exist — T020 must create it before writing the file
