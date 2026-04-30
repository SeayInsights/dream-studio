# Tasks: Repo Knowledge Enhancement

**Input**: `.planning/specs/repo-knowledge-enhancement/plan.md`  
**Prerequisites**: plan.md approved by Director

**Root**: `C:\Users\Dannis Seay\.claude\plugins\cache\dream-studio\dream-studio\0.2.0\skills\`

---

## Phase 1: Critical Bug Fix (Sequential — must complete before Phase 2)

**Purpose**: Fix the TMDL indentation bug that is actively causing parse errors in generated TMDL files.

**⚠️ CRITICAL**: This bug is live. Do this task first, alone. Do not parallelize.

- [ ] T001 [BUG] Rewrite `client-work/powerbi/pbip-format.md`
  - **What**: Fix tabs/spaces rule (currently backwards — says spaces, must say tabs). Add full PBIP folder structure (roles/, cultures/en-US.tmdl, diagramLayout.json, expressions.tmdl). Add TMDL editing rules from pbip-demo copilot-instructions: description placement, lineageTag prohibition, M-query step naming. Add PBIP dynamic detection rule (never hardcode `.SemanticModel` — detect `*.SemanticModel`). Add rename checklist (8 scopes). Add Python-first file ops rule.
  - **Acceptance**: File says "indent with tabs, never spaces (spaces cause parse errors)" — and the old "2 spaces" line is gone.
  - **Implements**: FR-001, FR-002
  - **Source**: d7rocket/PowerBI-Skill, RuiRomano/pbip-demo, JonathanJihwanKim/pbip-lineage-explorer

**Checkpoint**: T001 complete → Phase 2 and Phase 3 can begin (all in parallel, all different files)

---

## Phase 2: Power BI Reference Expansion (Parallel — T002 and T003 touch different files)

**Purpose**: Add deep Power BI reference knowledge from the repo analysis.

- [ ] T002 [P] [US1] Create new file `client-work/powerbi/tmdl-authoring.md`
  - **What**: New reference file covering: `_measures` table pattern (measures-only table, no data rows), single-direction relationship rationale, calculation group TMDL structure, field parameter gotcha (references ALL contained measures, not just active), three-level rename chain (source_name → pq_name → pbi_name), session workflow (inspect before editing, small changes, validate in Desktop immediately). Update `client-work/SKILL.md` imports section to reference this new file.
  - **Acceptance**: File exists at the correct path and `client-work/SKILL.md` imports it.
  - **Implements**: FR-003
  - **Source**: d7rocket/PowerBI-Skill, JonathanJihwanKim/pbip-documenter, JonathanJihwanKim/pbip-lineage-explorer, Ajandaghian/superstore-pbip
  - **Depends on**: T001 complete (T001 modifies client-work/powerbi/ folder; T002 adds a new file there — safe to parallel after T001 is done)

- [ ] T003 [P] [US1] Expand `skills/domains/bi/dax-patterns.md`
  - **What**: Add annotated DAX patterns section with WHY explanations: (1) VAR-before-CALCULATE — why VAR captures scalar before outer CALCULATE, preventing circular evaluation; (2) ALL vs ALLSELECTED — ALL(Table) for true global benchmarks vs ALLSELECTED for respect-slicer benchmarks, with decision guide; (3) AVERAGEX for composite expressions — why AVERAGEX over composite is correct while AVERAGE of separate columns yields wrong results under filters; (4) mean absolute deviation — AVERAGEX + ABS pattern. Add concrete TMDL measure syntax section: QoQ with REMOVEFILTERS+DATEADD, MEDIANX+KEEPFILTERS+SUMMARIZE+ALLSELECTED, CONCATENATEX+VALUES for dynamic labels. Add toolchain section (pbir CLI, Tabular Editor, DAX Studio, pbi-tools, Fabric CLI). Add DAX measure output template (Name / Business definition / DAX / Format string / Display folder / Description / Validation idea).
  - **Acceptance**: File contains all four annotated patterns with WHY explanations, two concrete TMDL measure examples with code, and the toolchain list.
  - **Implements**: FR-004
  - **Source**: TeslimAdeyanju/world-university-ranking, Ajandaghian/superstore-pbip, gustavonline/agentic-powerbi

---

## Phase 3: Skill Architecture Improvements (Parallel — T004, T005, T006, T007 all touch different files)

**Purpose**: Apply wix/skills architectural patterns across the most-used skills.

- [ ] T004 [P] [US2] Update `client-work/SKILL.md`
  - **What**: Add mandatory pre-build checklist with STOP gate: `[ ]` Identify PBIP_DIR dynamically (grep for `*.SemanticModel`), `[ ]` Read tmdl-authoring.md rules, `[ ]` State blast radius (which tables/measures affected), `[ ]` STOP: if any unchecked, do not proceed. Add anti-patterns table (❌ WRONG / ✅ CORRECT) covering: hardcoding `.SemanticModel` path, adding `lineageTag` to new objects, indenting TMDL with spaces, using Windows grep on TMDL files, skipping Desktop validation. Expand trigger phrase list in frontmatter description.
  - **Acceptance**: SKILL.md has a numbered checklist section with 4 items and a STOP gate, and a two-column anti-patterns table with at least 5 rows.
  - **Implements**: FR-005
  - **Source**: wix/skills, d7rocket/PowerBI-Skill

- [ ] T005 [P] [US2] Update `build/SKILL.md`
  - **What**: Add STOP gate after Step 0 (Load plan): "If project has 5+ files and CONSTITUTION.md or GOTCHAS.md are missing — STOP. Run `dream-studio:harden` first." Convert existing "Anti-patterns" prose list at the bottom into a ❌ WRONG / ✅ CORRECT two-column table.
  - **Acceptance**: Anti-patterns section is a markdown table with ❌/✅ columns, and the STOP gate text appears after Step 0.
  - **Implements**: FR-006
  - **Source**: wix/skills

- [ ] T006 [P] [US2] Update `debug/SKILL.md`
  - **What**: Convert existing "Rules" + "Anti-patterns" sections into a single ❌ WRONG / ✅ CORRECT two-column table. Add one row: "Using shell grep on Windows for TMDL/UTF-8 file search → Use Python with UTF-8 encoding instead."
  - **Acceptance**: Anti-patterns section is a markdown table with ❌/✅ columns. No prose anti-patterns remain below the table.
  - **Implements**: FR-006
  - **Source**: wix/skills, d7rocket/PowerBI-Skill

- [ ] T007 [P] [US3] Create new file `dashboard-dev/canvas-patterns.md`
  - **What**: New reference file covering 7 visual builder patterns extracted from repo analysis: (1) Zero-size inflation — empty elements collapse to 0×0; fix with RAF-batched MutationObserver + synthetic padding, distinguish empty vs intentionally zero; (2) Canvas overlay pattern (CanvasSpots) — selection/hover chrome on positioned overlay above iframe, not injected into page DOM; (3) 4-tier responsive style cascade — baseStyles → tabletStyles → mobileStyles → rawStyles, write to correct tier by active breakpoint, cascade downward on read; (4) Drag placeholder as raw DOM — inject drop placeholder as raw `<div>`, not reactive/framework-managed, to prevent full re-render during drag; (5) Grouped undo — fuse simultaneous mutations into one undo step, don't treat each style property change as separate; (6) Declarative property panel — components expose `properties[]` array, panel renders from it automatically; (7) AI → canvas pipeline — prompt → block JSON → deserialize into component tree → render. Update `dashboard-dev/SKILL.md` to import this file.
  - **Acceptance**: File exists, contains all 7 patterns each with source attribution, and dashboard-dev/SKILL.md imports it.
  - **Implements**: FR-007
  - **Source**: Webstudio (inflator.ts), GrapesJS (CanvasSpots), Frappe Builder (block.ts, canvasStore.ts, AIPageGeneratorModal), VvvebJs (properties[])

---

## Dependencies & Execution Order

### Phase Dependencies
- **Phase 1 (T001)**: Start immediately — no dependencies
- **Phase 2 (T002, T003)**: Requires T001 complete. T002 and T003 are parallel (different files)
- **Phase 3 (T004–T007)**: Can start after T001 complete. T004–T007 are all parallel (different files)

**Note**: Phase 2 and Phase 3 can actually run concurrently once T001 is done. No shared files between any Phase 2 or Phase 3 task.

### File Ownership (no conflicts)
| Task | Files Owned |
|---|---|
| T001 | `client-work/powerbi/pbip-format.md` |
| T002 | `client-work/powerbi/tmdl-authoring.md` (new), `client-work/SKILL.md` (imports section only) |
| T003 | `skills/domains/bi/dax-patterns.md` |
| T004 | `client-work/SKILL.md` (body sections — not imports) |
| T005 | `build/SKILL.md` |
| T006 | `debug/SKILL.md` |
| T007 | `dashboard-dev/canvas-patterns.md` (new), `dashboard-dev/SKILL.md` (imports section only) |

**⚠️ CONFLICT WARNING**: T002 and T004 both touch `client-work/SKILL.md`. T002 adds to the imports section; T004 adds to the body. They must be executed sequentially (T002 → T004) or carefully merged.

---

## Summary Table

| ID | Task | Phase | Parallel? | Acceptance |
|---|---|---|---|---|
| T001 | Fix pbip-format.md (bug + TMDL rules) | 1 | No | "tabs, never spaces" in file |
| T002 | New tmdl-authoring.md | 2 | Yes | File exists + imported by SKILL.md |
| T003 | Expand dax-patterns.md | 2 | Yes | 4 annotated patterns + code examples |
| T004 | Update client-work/SKILL.md | 3 | Yes (after T002) | Checklist + STOP gate + anti-patterns table |
| T005 | Update build/SKILL.md | 3 | Yes | Anti-patterns table + STOP gate |
| T006 | Update debug/SKILL.md | 3 | Yes | Anti-patterns table |
| T007 | New canvas-patterns.md | 3 | Yes | 7 patterns + imported by dashboard-dev/SKILL.md |
