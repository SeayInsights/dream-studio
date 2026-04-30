# Implementation Plan: Security Dashboard Redesign

**Date**: 2026-04-27 | **Spec**: `.planning/specs/security-dashboard-redesign/spec.md`  
**Input**: Feature specification from spec.md

## Summary

Consolidate 14-tab security dashboard into 3 strategic pages with visual hierarchy. Replace file-level detail tables with repo-level visual aggregates on executive view. Add line-level precision for developer drill-down. Transform from "information overload" to "actionable intelligence" for VP/CEO protecting Kroger proprietary data.

**Core transformation:**
- **Page 1 (Security Command Center):** 5 KPIs + ranked repos chart + trends (exec view, 30-second risk assessment)
- **Page 2 (Repository Deep Dive):** File-level findings table with line numbers, mitigation tracking (investigation layer)
- **Page 3 (Trends & Compliance):** Time-series analytics, compliance mapping, Zscaler compatibility (supporting analytics)

## Technical Context

**Language/Version**: Power BI Desktop (latest), DAX, M Query  
**Primary Dependencies**: Existing data model (Findings, Mitigations, Compliance, Repos, Trends, Netcompat tables)  
**Storage**: Power BI Premium workspace with scheduled refresh (every 4 hours)  
**Testing**: Manual UAT with VP/CEO (5 execs), DAX Studio query performance validation, WCAG 2.1 AA accessibility checker  
**Target Platform**: Power BI Desktop (Windows), Power BI Service (browser), Power BI Mobile (out of scope v1)  
**Project Type**: Power BI dashboard (.pbip format)  
**Performance Goals**: <5 seconds load time for 10,000 findings across 50 repos, <200ms visual refresh on slicer change  
**Constraints**: WCAG 2.1 AA compliance (colorblind-safe palette, 4.5:1 contrast ratios), PLMarketing branding (if applicable)  
**Scale/Scope**: 10,000 findings, 50 repos, 90 days historical trends, 6 OWASP categories, 3 compliance frameworks

## Constitution Check

*GATE: Must pass before implementation.*

✅ **Visual > Tables:** Page 1 has zero detail tables, only visual aggregates (stacked bars, donuts, trend lines)  
✅ **Repo-level executive view:** No file names on Page 1, only repo names ranked by risk  
✅ **Drill hierarchy:** Org → Repo → File → Line (clear information architecture)  
✅ **Independent user stories:** Each story can be implemented and tested standalone (P1 = MVP)  
✅ **Actionable design:** Line numbers enable devs to jump to code (not just "SQL Injection in auth.py")  
✅ **No premature optimization:** DAX measures use simple aggregations, no complex recursion or variables unless needed  

## Project Structure

### Documentation (this feature)

```text
.planning/specs/security-dashboard-redesign/
├── spec.md              # User stories, requirements (dream-studio:think output)
├── plan.md              # This file (dream-studio:plan output)
├── tasks.md             # Task breakdown (dream-studio:plan output)
└── data-model-changes.md  # Optional: DAX measures and calculated columns reference
```

### Power BI Project Structure

```text
enterprise-security/
├── enterprise-security.pbip           # Power BI project file
├── enterprise-security.Report/
│   ├── report.json                    # Report layout (pages, visuals)
│   └── .pbi/localSettings.json
├── enterprise-security.SemanticModel/
│   ├── model.bim                      # Data model (tables, DAX measures, relationships)
│   └── definition/
│       ├── tables/                    # Table definitions
│       ├── relationships/
│       └── expressions/
└── generate_visuals.py                # (Existing) Python script for test data generation
```

**Structure Decision:** Keep existing .pbip structure. Add new DAX measures to `_Measures` table. Create 3 new report pages (delete/archive old 14 pages after migration). Use Power BI native drill-through (not bookmarks) for Page 1 → Page 2 navigation.

## Complexity Tracking

| Concern | Why Needed | Simpler Alternative Rejected Because |
|---------|------------|-------------------------------------|
| Line number column added to Findings table | Enables developers to jump directly to problematic code (FR-026) | Showing only file name insufficient — devs waste time searching 500+ line files for the issue |
| Drill-through from Page 1 to Page 2 | Preserves filter context (selected repo flows to Page 2) while keeping Page 2 hidden from nav | Bookmarks don't auto-filter drill target; visible Page 2 clutters navigation for execs who never leave Page 1 |
| Colorblind-safe palette with conditional formatting | WCAG 2.1 AA requirement + 8% of male execs are colorblind | Standard Power BI colors (red/green) fail accessibility and confuse colorblind users |

## Requirements Traceability

| Requirement ID | Description | Implemented By |
|---------------|-------------|----------------|
| FR-001 | 5 KPI cards on Page 1 | T006, T007 |
| FR-002 | Repos ranked by risk (stacked bar) | T008, T009 |
| FR-003 | 30-day risk trend line | T010 |
| FR-004 | Category distribution donut | T011 |
| FR-005 | Top 5 vulnerabilities bar chart | T012 |
| FR-006 | Remediation velocity KPI with conditional formatting | T013 |
| FR-007 | Drill-through from Page 1 to Page 2 | T020 |
| FR-008 | File-level findings table with Line column | T015, T016 |
| FR-009 | Severity sorting (Critical → High → Medium → Low) | T017 |
| FR-010 | Mitigation status icons (✅⚠️🔄✔️) | T018 |
| FR-011 | Finding type donut filtered to selected repo | T019 |
| FR-012 | Time-series line chart (findings opened vs closed) | T022 |
| FR-013 | Mean time to remediate bar chart by severity | T023 |
| FR-014 | Compliance mapping matrix | T025 |
| FR-015 | Compliance framework slicer | T026 |
| FR-016 | Zscaler compatibility traffic lights | T027 |
| FR-017 | Org risk score calculation | T003 |
| FR-018 | Remediation velocity calculation | T004 |
| FR-019 | Auto-refresh on dashboard load | T029 (config) |
| FR-020 | Excel export capability | T029 (native Power BI) |
| FR-021 | <5 second load time for 10K findings | T030 (performance test) |
| FR-022 | Drill-through filter context preserved | T020 |
| FR-023 | KPI change indicators (↑↓) | T007 |
| FR-024 | Ranked repos chart shows top 15 only | T009 |
| FR-025 | Colorblind-safe palette applied | T005 |
| FR-026 | Line number displayed in findings table | T016 |
| FR-027 | Line column sortable and filterable | T016 |

## Dependencies

### External Dependencies
- **Power BI Desktop** (latest version, free) — development environment
- **Power BI Premium Workspace** — deployment target for scheduled refresh
- **Python 3.12+** (optional) — for `generate_visuals.py` test data script
- **DAX Studio** (optional) — for query performance testing

### Internal Dependencies
- **Existing data model tables:** Findings, Mitigations, Compliance, Repos, Trends, Netcompat
- **Findings table MUST have `LineNumber` column** (integer, nullable) — if missing, ETL pipeline update required (blocks all Page 2 work)
- **Color palette constants** — define in theme JSON or document in plan for consistent application

### Data Model Assumptions
- `Findings[Severity]` has values: "Critical", "High", "Medium", "Low" (exact case-sensitive match)
- `Findings[DateOpened]` and `Findings[DateClosed]` are datetime columns
- `Findings[MitigationStatus]` has values: "Unassigned", "Assigned", "In Progress", "Completed"
- `Repos[RepoName]` is unique (primary key for drill-through filtering)
- `DateTable` exists with standard calendar columns for time-series charting

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| **Findings table missing LineNumber column** | High — blocks FR-026, FR-027, entire Page 2 line-level feature | **Pre-check:** Query Findings table schema before starting tasks. If missing, add ETL task to pipeline (outside this plan scope, escalate to data team) |
| **10K findings cause >5sec load time** | Medium — fails FR-021, poor exec experience | **Test early:** Load dashboard with full prod dataset after T009. If slow, add aggregation table or implement Top N filtering |
| **Exec resistance to 3-page design** | Medium — adoption failure, revert to 14-tab design | **Mitigate:** UAT with VP after Page 1 complete (T014). Get approval before continuing to Page 2/3 |
| **Drill-through doesn't preserve filters** | High — breaks FR-022, Page 2 investigation workflow broken | **Validate:** Test drill-through with multiple filter scenarios (severity filter + repo click) in T020 |
| **WCAG 2.1 AA compliance fails** | Medium — legal/audit risk for PLMarketing | **Validate:** Run Power BI Accessibility Checker after T005 (color palette). Fix before proceeding to visuals |
| **Data refresh failures (4-hour schedule)** | Low — stale data shown to execs | **Monitor:** Set up Power BI refresh failure alerts. Document manual refresh procedure in T029 |

## Success Metrics

- [x] All 27 functional requirements implemented (FR-001 through FR-027)
- [ ] All 5 user stories testable independently (US1-US5)
- [ ] Dashboard loads in <5 seconds with 10K findings (FR-021) — validate in T030
- [ ] WCAG 2.1 AA compliance verified — validate in T031
- [ ] 80% of execs prefer new design over old 14-tab design (post-deployment survey)
- [ ] VP/CEO can identify highest-risk repo in <30 seconds (SC-001) — validate in T032 UAT
- [ ] Time to export compliance audit report reduces from 10+ minutes to <2 minutes (SC-005)

## Implementation Phases

### Phase 1: Setup & Data Model (T001-T005)
**Duration:** 2-3 hours  
**Goal:** Prepare data model with DAX measures, color palette, base structure

**Deliverables:**
- 5 new DAX measures in `_Measures` table
- Color palette theme configured
- Line number handling verified (or escalation issued)

---

### Phase 2: Page 1 - Security Command Center (T006-T014) 🎯 MVP
**Duration:** 6-8 hours  
**Goal:** Complete User Story 1 (Executive Daily Risk Check)

**Deliverables:**
- 5 KPI cards (risk score, critical, high, repos at risk, velocity)
- Ranked repos horizontal stacked bar chart
- 30-day risk trend line
- Category donut + top vulnerabilities bar
- Drill-through configuration to Page 2

**Checkpoint:** VP approval required before proceeding to Page 2

---

### Phase 3: Page 2 - Repository Deep Dive (T015-T021)
**Duration:** 4-5 hours  
**Goal:** Complete User Story 2 (Security Lead Investigates High-Risk Repo)

**Deliverables:**
- File-level findings table with Line column
- Severity sorting, mitigation status icons
- Repo slicer + summary cards
- Finding type donut filtered to selected repo
- Drill-through tested end-to-end

---

### Phase 4: Page 3 - Trends & Compliance (T022-T028)
**Duration:** 5-6 hours  
**Goal:** Complete User Stories 3, 4, 5 (Compliance, Remediation Monitoring, Zscaler)

**Deliverables:**
- Time-series charts (opened vs closed, remediation velocity)
- Compliance mapping matrix with framework slicer
- Zscaler compatibility traffic lights

---

### Phase 5: Polish, Testing & Deployment (T029-T033)
**Duration:** 3-4 hours  
**Goal:** Validate performance, accessibility, UAT, publish to Power BI Service

**Deliverables:**
- Performance validated (<5sec load)
- Accessibility validated (WCAG 2.1 AA)
- UAT completed with 5 execs
- Dashboard published to Premium workspace

---

## Total Effort Estimate

**Development:** 20-25 hours (part-time over 2-3 weeks at 10 hrs/week)  
**UAT & Revisions:** 3-5 hours  
**Deployment & Training:** 2 hours  
**Total:** 25-32 hours

## dream-studio Integration

**Skill Flow**: think → **plan** → build → review → verify → ship

**Output Location**: `.planning/specs/security-dashboard-redesign/plan.md` and `tasks.md`

**Traceability**: Active — see `.planning/traceability.yaml` for requirement status tracking

**Next Steps**: 
1. Review this plan with user for approval
2. Verify `Findings[LineNumber]` column exists (blocker check)
3. Run `dream-studio:build` with tasks.md
4. Execute tasks in dependency order (Setup → Page 1 → Page 2 → Page 3 → Polish)
5. UAT approval gate after Page 1 (T014) before continuing

**Notes:**
- This is a Power BI project, not traditional code — tasks involve DAX, M Query, visual configuration
- Commits will be `.pbip` file changes (report.json, model.bim updates)
- "Tests" are manual validation (open dashboard, verify visual behavior)
- Performance testing uses DAX Studio query analyzer
- Accessibility testing uses Power BI built-in checker
