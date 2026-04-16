---
name: client-work
description: Power Platform client lifecycle — intake, SOW, build (Power BI, Power Apps, Power Automate), review, handoff — with DAX/M-query patterns, delegation rules, and flow error handling. Trigger on `intake:`, `sow:`, `proposal:`, `build report:`, `review powerbi:`, `optimize dax:`, `build flow:`, `build app:`, `client handoff:`, `document:`.
---

# Client Work — Full Lifecycle

## Trigger
`intake:`, `sow:`, `proposal:`, `build report:`, `review powerbi:`, `optimize dax:`, `build flow:`, `review flow:`, `build app:`, `review app:`, `client handoff:`, `document:`

## Lifecycle
1. **Intake** — Read the project tracker (Notion, Jira, etc.), understand the business question, surface assumptions
2. **SOW** — Scope, deliverables, timeline, assumptions, out-of-scope. Director reviews before sending.
3. **Build** — Power BI / Power Apps / Power Automate per SOW. Atomic commits. Test as you go.
4. **Review** — Director walkthrough before client sees it
5. **Handoff** — Documentation package: what was built, how to use it, how to maintain it, known limitations

## Power BI

### Data modeling
- Star schema: fact tables + dimension tables, no wide flat tables
- Naming: dim_[entity], fact_[process], bridge_[relationship]
- Date table: always create a dedicated date dimension
- Avoid bi-directional relationships unless absolutely necessary

### DAX
- Always use VAR for multi-step measures — never nested CALCULATE without reason
- Pattern: `VAR result = CALCULATE(...) RETURN result`
- Time intelligence: use DATEADD, SAMEPERIODLASTYEAR with the dedicated date table
- Row-level security: implement per client requirement, test with "View As"

### M Query
- Fold to source when possible — check query folding indicator
- Document manual steps that break folding
- Parameter tables for dynamic data sources
- Error handling: `try...otherwise` for unreliable sources

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
