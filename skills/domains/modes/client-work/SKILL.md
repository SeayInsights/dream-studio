---
ds:
  pack: domains
  mode: client-work
  mode_type: build
  inputs: [client_request, business_requirements, data_sources, sow]
  outputs: [deliverable, documentation, handoff_package, validation_evidence]
  capabilities_required: [Read, Write, Edit, Grep, Bash, Agent]
  model_preference: sonnet
  estimated_duration: 8-30hrs
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

## Intake Triage {#intake-triage}

Use this table to quickly classify incoming requests and route to the right approach.

| Request Pattern | Work Type | Est. Hours | Submode/Approach |
|---|---|---|---|
| "Build a dashboard showing..." | Power BI dashboard build | 8-20 | Full lifecycle: data model → measures → visuals → storytelling framework. Check `domains/powerbi/storytelling-framework.yml` for structure. |
| "This DAX measure is slow/wrong..." | DAX formula optimization | 2-6 | Dispatch `bi-developer` subagent. Read `domains/powerbi/dax-patterns.md` for VAR patterns, context transition, time intelligence. Analyze query plan if >3s. |
| "Build an app for tracking..." | Power Apps canvas app | 12-30 | Canvas app with delegation warnings resolved. Follow naming conventions (scr_, ctn_, lbl_, btn_). Test offline scenarios if mobile. |
| "Automate [process] when [trigger]..." | Power Automate flow | 4-12 | Flow with error handling (Scope + Configure Run After), approval timeout, environment variables for connections. Set concurrency to 1 if shared state. |
| "Connect [source A] to [source B]..." | Data model design | 6-16 | Star schema with fact/dimension tables. Check `domains/powerbi/m-query-patterns.md` for query folding. Dispatch `bi-developer` for TMDL authoring. |
| "Report takes 30s to load..." | Report performance tuning | 4-10 | Check DirectQuery vs Import, measure complexity, visual count. Use Performance Analyzer. Read `domains/powerbi/dax-patterns.md` for SUMMARIZE/TREATAS patterns. Dispatch `bi-developer` if semantic model changes needed. |

**Escalation:** If the request does not match any pattern above, ask one clarifying question: "Is this primarily a data issue, a visualization issue, or a process automation issue?"

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

## Deliverable Response Contract {#deliverable-contract}

Every client deliverable MUST include all five sections below. This contract ensures nothing is missed and the client can maintain/extend the work independently.

### 1. Scope Confirmation
**What was requested vs. what was delivered**

- [ ] Original request documented (from email, meeting notes, or intake form)
- [ ] Delivered scope explicitly stated
- [ ] Any deviations from original request explained with rationale
- [ ] Out-of-scope items listed (what was NOT included and why)
- [ ] Sign-off confirmation: "This deliverable fulfills [specific business requirement]"

### 2. Data Lineage
**Where data comes from, transformations applied**

- [ ] Source systems documented (e.g., SQL Server, SharePoint, Excel, Dataverse)
- [ ] Connection details provided (server names, database names, authentication method)
- [ ] Transformation steps outlined (M-query steps, DAX calculations, Power Automate actions)
- [ ] Refresh schedule documented (frequency, time, dependencies)
- [ ] Data freshness indicators shown (e.g., "Last Refresh" timestamp on report)

### 3. Validation Evidence
**Test results, data checks passed**

- [ ] Sample outputs provided (screenshots, PDFs, or test data exports)
- [ ] Expected vs. actual results documented for key metrics
- [ ] Edge cases tested (empty data, nulls, filters, RLS, date ranges)
- [ ] Performance benchmarks documented (refresh time, query response time)
- [ ] Accessibility compliance verified (see `accessibility-checklist.yml` for Power BI)

### 4. Handoff Checklist
**Files delivered, access granted, documentation**

- [ ] All files delivered (`.pbix`, `.pbit`, `.msapp`, flow exports, documentation)
- [ ] Access granted (workspace permissions, data source credentials, app sharing)
- [ ] User guide provided (how to use the deliverable, with screenshots)
- [ ] Admin guide provided (how to refresh, update, troubleshoot)
- [ ] Contact info provided (who to reach for support, escalation path)

### 5. Maintenance Notes
**How to update, troubleshoot, extend**

- [ ] How to refresh data (manual vs. scheduled, gateway dependencies)
- [ ] How to add new fields/measures (with examples)
- [ ] How to troubleshoot common errors (with solutions or workarounds)
- [ ] Known limitations documented (technical debt, workarounds, future improvements)
- [ ] Extension guidance (how to add new pages, visuals, or flows without breaking existing work)

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
