---
name: client-work
description: Power Platform client lifecycle — intake, SOW, build (Power BI, Power Apps, Power Automate), review, handoff — with DAX/M-query patterns, delegation rules, and flow error handling. Trigger on `intake:`, `sow:`, `proposal:`, `build report:`, `review powerbi:`, `optimize dax:`, `build flow:`, `build app:`, `client handoff:`, `document:`, `add measure:`, `create measure:`, `build measure:`, `add column:`, `create report:`, `DAX error:`, `M-query error:`, `refresh fails:`, `TMDL:`, `pbip:`, `semantic model:`, `RLS:`, `star schema:`, `data model:`.
pack: domains
chain_suggests: []
---

# Client Work — Full Lifecycle

## Before you start
Read these files first — every time:
1. `gotchas.yml` — what NOT to do (mandatory)
2. `domains/powerbi/pbip-format.md` — for any .pbip / TMDL work
3. `domains/powerbi/storytelling-framework.yml` — for report design
4. `domains/powerbi/accessibility-checklist.yml` — before any report delivery

## Imports
- domains/powerbi/dax-patterns.md — data modeling, DAX patterns, DAX error reference
- domains/powerbi/m-query-patterns.md — query folding, M-query patterns, error reference, semantic model validation
- domains/powerbi/tmdl-authoring.md — TMDL patterns, _measures table, relationship direction, rename chain, session workflow

## Trigger
`intake:`, `sow:`, `proposal:`, `build report:`, `review powerbi:`, `optimize dax:`, `build flow:`, `review flow:`, `build app:`, `review app:`, `client handoff:`, `document:`

## Dispatch: bi-developer subagent
For any Power BI work involving `.pbip` files, TMDL format, semantic model validation, complex DAX debugging, M-query troubleshooting, or Dataverse schema — dispatch a `bi-developer` subagent. Do not handle inline.

Dispatch triggers: editing `.pbip`/`.tmdl` files, DAX error diagnosis, semantic model failures, M-query refresh errors, Dataverse schema changes, RLS implementation.

## Power BI Pre-Build Checklist

Before writing or editing any TMDL, DAX, or M-query — complete every item:

- [ ] **Detect PBIP_DIR** — locate the `*.SemanticModel` folder dynamically (e.g., `glob("*.SemanticModel")`). Never hardcode `.SemanticModel`.
- [ ] **Read TMDL rules** — confirm `domains/powerbi/pbip-format.md` and `domains/powerbi/tmdl-authoring.md` are loaded for this session.
- [ ] **State blast radius** — list which tables, measures, and relationships will be affected by this change.
- [ ] **Identify SSOT** — confirm which `.tmdl` file is the authoritative source for the object being modified.

**⛔ STOP: if any item above is unchecked, do not proceed with any TMDL or DAX edits.**

**Escalation pattern:**
1. Attempt to solve the problem using reference files
2. If that fails, retry once with a different approach
3. If still blocked, ask one targeted question: "I need [specific missing info] to proceed — can you provide it?"

## Lifecycle
1. **Intake** — Read the project tracker (Notion, Jira, etc.), understand the business question, surface assumptions
2. **SOW** — Scope, deliverables, timeline, assumptions, out-of-scope. Director reviews before sending.
3. **Build** — Power BI / Power Apps / Power Automate per SOW. Atomic commits. Test as you go.
4. **Review** — Director walkthrough before client sees it
5. **Handoff** — Documentation package: what was built, how to use it, how to maintain it, known limitations

## Power BI

### Data modeling + DAX
**See:** `domains/powerbi/dax-patterns.md` — star schema, naming conventions, VAR patterns, time intelligence, RLS, DAX error reference

### M Query + query folding
**See:** `domains/powerbi/m-query-patterns.md` — folding rules, parameter tables, error handling, M-query error reference, semantic model validation

### .pbip format
**See:** `domains/powerbi/pbip-format.md` — full file structure, TMDL syntax, JSON schemas, and editing rules

## Power BI Verify

After any build or change, verify in this order:
1. **Open in Power BI Desktop** — no red error indicators in the field list or data pane
2. **Refresh data** — completes without errors; check refresh history
3. **Measure spot-check** — create a matrix/table visual with key measures; compare to expected values
4. **RLS** — use "Modeling → View As Role" for each role; confirm data filters correctly
5. **All pages** — click through every report page; no blank visuals, no "Can't display visual" errors
6. **Publish to dev workspace** — confirm report loads in browser at app.powerbi.com

## Power Apps

### Canvas apps
- Responsive layout, consistent naming: scr_, ctn_, lbl_, btn_, gal_, ico_
- Delegation warnings: resolve or document with workaround
- Collections for offline scenarios, Patch for direct writes
- Touch targets: 44x44px minimum

### Model-driven apps
- Business rules over JavaScript when possible
- Forms: hide complexity, show relevant fields per context
- Views: default view shows actionable items, not everything
- Desktop + mobile: test both form factors before delivery

## Power Automate

### Flow patterns
- Error handling: try/catch (Scope + Configure Run After) on every external connector call
- Approval flows: always set timeout + escalation path
- Naming: descriptive action names, not defaults
- Environment variables for connection references and config values
- Concurrency control: set to 1 for flows that modify shared state

## Handoff documentation
Every deliverable ships with:
1. What was built (purpose, scope)
2. How to use it (user guide with screenshots)
3. How to maintain it (refresh schedules, data source connections, who to contact)
4. Known limitations and workarounds
5. Next steps / future enhancements (if discussed)

## Anti-patterns

| ❌ Wrong | ✅ Correct |
|---|---|
| Hardcoding `.SemanticModel` in scripts | Detect `*.SemanticModel` dynamically — folder name matches the project name |
| Adding `lineageTag` to new TMDL objects | Omit `lineageTag` when creating — Power BI generates these on first open |
| Indenting TMDL with spaces | Tabs only — spaces cause parse errors in Power BI Desktop |
| Using Windows `grep`/`findstr` to search TMDL files | Use Python with `open(path, encoding='utf-8')` — accented characters break shell tools |
| Editing `report.json` directly | Never edit `report.json` — Power BI owns and regenerates this file |
| Skipping Desktop validation after TMDL edits | Always open in Power BI Desktop after every TMDL change — parse errors surface immediately |
| Placing descriptions as `description:` properties in TMDL body | Use `/// Description text` annotation above the object |
| Adding measures after columns in a table block | Measures go above columns in TMDL table blocks |
| Renaming a column in TMDL without checking the rename chain | Trace all 3 levels: source_name → pq_name → pbi_name before renaming |
