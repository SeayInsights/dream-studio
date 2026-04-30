---
description: "Task breakdown for Security Dashboard Redesign implementation"
---

# Tasks: Security Dashboard Redesign

**Input**: Design documents from `.planning/specs/security-dashboard-redesign/`
**Prerequisites**: plan.md, spec.md

**Tests**: Manual UAT and validation tasks included (T014, T021, T030-T033)

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different visuals, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US5, or SETUP/POLISH)
- Include exact file paths where applicable

---

## Phase 1: Setup & Data Model (Shared Infrastructure)

**Purpose**: Data model preparation and configuration that blocks all user story work

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

---

### T001 [SETUP] Verify data model prerequisites

**Implements**: Foundation check  
**Files**: `enterprise-security.SemanticModel/model.bim`  
**Depends on**: None  
**Acceptance**: 
- [ ] Query `Findings` table schema and verify `LineNumber` column exists (integer, nullable)
- [ ] If missing, document escalation to data team (blocker — cannot proceed to Page 2 tasks)
- [ ] Verify `Findings[Severity]` has values: "Critical", "High", "Medium", "Low"
- [ ] Verify `Findings[MitigationStatus]` has expected values
- [ ] Verify `Repos[RepoName]` is unique (no duplicates)

---

### T002 [P] [SETUP] Create DateTable if missing

**Implements**: Time-series foundation (FR-012 prerequisite)  
**Files**: `enterprise-security.SemanticModel/model.bim` → `DateTable`  
**Depends on**: None  
**Acceptance**:
- [ ] Check if `DateTable` exists in model
- [ ] If missing, create DateTable with columns: Date, Year, Quarter, Month, Day, DayOfWeek
- [ ] Create relationship: `Findings[DateOpened]` → `DateTable[Date]`
- [ ] Verify: Time-series trend chart can use DateTable for X-axis

---

### T003 [SETUP] Create Org Risk Score DAX measure

**Implements**: FR-017  
**Files**: `enterprise-security.SemanticModel/model.bim` → `_Measures` table  
**Depends on**: T001 (severity values validated)  
**Acceptance**:
- [ ] Create measure: `[Org Risk Score]` = weighted sum of findings by severity / total repos
  ```dax
  VAR TotalFindings = 
      (COUNTROWS(FILTER(Findings, Findings[Severity] = "Critical")) * 10) +
      (COUNTROWS(FILTER(Findings, Findings[Severity] = "High")) * 5) +
      (COUNTROWS(FILTER(Findings, Findings[Severity] = "Medium")) * 2) +
      (COUNTROWS(FILTER(Findings, Findings[Severity] = "Low")) * 1)
  VAR TotalRepos = DISTINCTCOUNT(Repos[RepoName])
  RETURN DIVIDE(TotalFindings, TotalRepos, 0)
  ```
- [ ] Test: Returns numeric value (e.g., 67) for org with 50 repos and mixed findings

---

### T004 [P] [SETUP] Create Remediation Velocity DAX measure

**Implements**: FR-018  
**Files**: `enterprise-security.SemanticModel/model.bim` → `_Measures` table  
**Depends on**: T001 (DateClosed column validated)  
**Acceptance**:
- [ ] Add calculated column to `Findings`: `[DaysToRemediate]` = DATEDIFF(DateOpened, DateClosed, DAY)
- [ ] Create measure: `[Remediation Velocity]` = average DaysToRemediate for findings closed in last 90 days
  ```dax
  CALCULATE(
      AVERAGE(Findings[DaysToRemediate]),
      Findings[DateClosed] >= TODAY() - 90,
      NOT(ISBLANK(Findings[DateClosed]))
  )
  ```
- [ ] Test: Returns numeric value (e.g., 14) when findings exist with DateClosed populated

---

### T005 [P] [SETUP] Configure colorblind-safe palette

**Implements**: FR-025  
**Files**: `enterprise-security.Report/.pbi/` or theme JSON  
**Depends on**: None  
**Acceptance**:
- [ ] Define color constants:
  - Critical/Red: #D32F2F
  - High/Orange: #F57C00
  - Medium/Yellow: #FBC02D
  - Low/Green: #388E3C
  - Primary/Blue: #1976D2
  - Neutral/Gray: #757575
- [ ] Apply to theme JSON or document for manual application in conditional formatting
- [ ] Run Power BI Accessibility Checker → verify contrast ratio ≥4.5:1 for all colors
- [ ] Test: Red/green not used together (colorblind confusion)

**Checkpoint**: Foundation ready — data model has measures, colors validated, prerequisite columns confirmed

---

## Phase 2: Page 1 - Security Command Center (Priority: P1) 🎯 MVP

**Goal**: Complete User Story 1 (Executive Daily Risk Check)

**Independent Test**: VP opens dashboard, sees Page 1 with 5 KPIs, identifies highest-risk repo in <30 seconds

---

### T006 [US1] Create Page 1 in report

**Implements**: Page 1 structure (FR-001 prerequisite)  
**Files**: `enterprise-security.Report/report.json` → add new section "Security Command Center"  
**Depends on**: T005 (setup complete)  
**Acceptance**:
- [ ] Delete or hide old 14 pages (archive for reference, don't delete source yet)
- [ ] Create new page: "Security Command Center" (displayName = "Security Command Center")
- [ ] Set page as default landing page (activeSectionIndex = 0)
- [ ] Set page height = 720px (standard 1920×1080 canvas)

---

### T007 [P] [US1] Add 5 KPI cards to Page 1

**Implements**: FR-001, FR-023  
**Files**: `enterprise-security.Report/report.json` → add 5 card visuals  
**Depends on**: T003, T004, T006 (measures exist, page created)  
**Acceptance**:
- [ ] Add card visual: Org Risk Score (x=20, y=20, w=300, h=160)
  - Measure: `[Org Risk Score]`
  - Title: "Org Risk Score"
  - Show change indicator: ↑↓ from last week (use `[Change from Last Week]` measure)
- [ ] Add card visual: Total Findings (x=340, y=20, w=220, h=160)
- [ ] Add card visual: Critical Findings (x=580, y=20, w=220, h=160)
- [ ] Add card visual: High Findings (x=820, y=20, w=220, h=160)
- [ ] Add card visual: Repos at Risk (x=1060, y=20, w=200, h=160)
  - Measure: `DISTINCTCOUNT(Repos[RepoName])` where findings > 0
- [ ] Test: All 5 cards display numeric values when dashboard loads

---

### T008 [US1] Create Repos[RiskScore] calculated column

**Implements**: FR-002 prerequisite  
**Files**: `enterprise-security.SemanticModel/model.bim` → `Repos` table  
**Depends on**: T001 (severity validated)  
**Acceptance**:
- [ ] Add calculated column: `Repos[RiskScore]`
  ```dax
  (CALCULATE(COUNTROWS(Findings), Findings[Severity] = "Critical") * 10) +
  (CALCULATE(COUNTROWS(Findings), Findings[Severity] = "High") * 5) +
  (CALCULATE(COUNTROWS(Findings), Findings[Severity] = "Medium") * 2) +
  (CALCULATE(COUNTROWS(Findings), Findings[Severity] = "Low") * 1)
  ```
- [ ] Test: Repos with 2 critical + 5 high findings have RiskScore = 45

---

### T009 [US1] Add ranked repos horizontal stacked bar chart

**Implements**: FR-002, FR-024  
**Files**: `enterprise-security.Report/report.json` → add horizontal stacked bar chart  
**Depends on**: T008 (RiskScore calculated)  
**Acceptance**:
- [ ] Add stacked bar chart visual (x=20, y=520, w=1240, h=300)
- [ ] Axis: `Repos[RepoName]`, sorted by `Repos[RiskScore]` descending
- [ ] Legend: `Findings[Severity]`
- [ ] Values: `COUNTROWS(Findings)` grouped by severity
- [ ] Colors: Red (Critical), Orange (High), Yellow (Medium), Green (Low)
- [ ] Filter: Top 15 repos only (FR-024)
- [ ] Test: Repo with highest RiskScore appears at top of chart
- [ ] Test: Clicking bar triggers drill-through to Page 2 (T020 will configure)

---

### T010 [P] [US1] Add 30-day risk trend line chart

**Implements**: FR-003  
**Files**: `enterprise-security.Report/report.json` → add line chart  
**Depends on**: T002 (DateTable exists), T003 (Org Risk Score measure)  
**Acceptance**:
- [ ] Add line chart visual (x=20, y=200, w=400, h=300)
- [ ] X-axis: `DateTable[Date]` (last 30 days filter)
- [ ] Y-axis: `[Org Risk Score]` calculated daily
- [ ] Line color: #1976D2 (primary blue)
- [ ] Tooltip: Show date + score + change from previous day
- [ ] Test: Trend line slopes downward when org improves (fewer findings)

---

### T011 [P] [US1] Add category distribution donut chart

**Implements**: FR-004  
**Files**: `enterprise-security.Report/report.json` → add donut chart  
**Depends on**: T006 (page created)  
**Acceptance**:
- [ ] Add donut chart visual (x=440, y=200, w=400, h=300)
- [ ] Legend: `Findings[FindingType]` (OWASP categories: Injection, Auth, Secrets, Data Protection, Dependencies, Misconfiguration)
- [ ] Values: `COUNTROWS(Findings)`
- [ ] Colors: 6-color palette (colorblind-safe from T005)
- [ ] Test: Clicking donut slice filters Page 1 visuals to that category

---

### T012 [P] [US1] Add top 5 vulnerabilities bar chart

**Implements**: FR-005  
**Files**: `enterprise-security.Report/report.json` → add horizontal bar chart  
**Depends on**: T006 (page created)  
**Acceptance**:
- [ ] Add horizontal bar chart (x=860, y=200, w=400, h=300)
- [ ] Axis: `Findings[FindingType]` or `Findings[CWE]` (top 5 by count)
- [ ] Values: `COUNTROWS(Findings)`
- [ ] Sort: Descending by count
- [ ] Filter: Top 5 only
- [ ] Test: SQL Injection appears at top if it's the most common vulnerability

---

### T013 [P] [US1] Add remediation velocity KPI with conditional formatting

**Implements**: FR-006  
**Files**: `enterprise-security.Report/report.json` → modify velocity card from T007  
**Depends on**: T004 (velocity measure), T007 (cards exist)  
**Acceptance**:
- [ ] Update "Remediation Velocity" card (created in T007)
- [ ] Apply conditional formatting:
  - Green if <7 days
  - Yellow if 7-14 days
  - Red if >14 days
- [ ] Format: Display as "14 days" (not just "14")
- [ ] Test: Card shows red when avg velocity = 21 days

---

### T014 [US1] UAT: Executive approval gate for Page 1

**Implements**: SC-001 (time-to-insight metric)  
**Files**: None (user testing)  
**Depends on**: T007-T013 (all Page 1 visuals complete)  
**Acceptance**:
- [ ] Schedule 30-min session with VP/CEO
- [ ] Task: "Identify the highest-risk repo and tell me the risk score"
- [ ] Measure: Time to answer (target: <30 seconds)
- [ ] Task: "Tell me if org security is improving or declining over last 30 days"
- [ ] Collect feedback: Any visuals confusing? Too much/too little detail?
- [ ] **GATE**: Get explicit approval to proceed to Page 2
- [ ] If rejected: Capture required changes before continuing

**Checkpoint**: Page 1 (MVP) is complete and approved — Security Command Center delivers exec value

---

## Phase 3: Page 2 - Repository Deep Dive (Priority: P1)

**Goal**: Complete User Story 2 (Security Lead Investigates High-Risk Repo)

**Independent Test**: Click "payment-api" on Page 1 → drill to Page 2 → see file-level table with line numbers sorted by severity

---

### T015 [US2] Create Page 2 in report

**Implements**: Page 2 structure (FR-008 prerequisite)  
**Files**: `enterprise-security.Report/report.json` → add new section "Repository Deep Dive"  
**Depends on**: T014 (Page 1 approved)  
**Acceptance**:
- [ ] Create new page: "Repository Deep Dive" (hidden from navigation — drill-through only)
- [ ] Set page as drill-through target
- [ ] Add page filter placeholder for `Repos[RepoName]` (will be populated by drill-through)

---

### T016 [US2] Add file-level findings table with Line column

**Implements**: FR-008, FR-026, FR-027  
**Files**: `enterprise-security.Report/report.json` → add table visual  
**Depends on**: T001 (LineNumber column validated), T015 (Page 2 created)  
**Acceptance**:
- [ ] Add table visual (x=20, y=220, w=1240, h=400)
- [ ] Columns: File, Line, Severity, CWE, Finding Type, Mitigation Status, Last Updated
- [ ] Line column format:
  - Display as integer (e.g., "142")
  - If NULL or 0, display "-"
  - Tooltip: "File-level issue - no specific line identified" when "-"
- [ ] Enable column sorting and filtering
- [ ] Test: Table shows "auth.py" in File column, "142" in Line column
- [ ] Test: Dependency vulnerability shows "-" in Line column

---

### T017 [US2] Configure custom severity sort order

**Implements**: FR-009  
**Files**: `enterprise-security.SemanticModel/model.bim` → `Findings[Severity]` column  
**Depends on**: T001 (severity values validated)  
**Acceptance**:
- [ ] Set custom sort order on `Findings[Severity]`:
  1. Critical
  2. High
  3. Medium
  4. Low
- [ ] Test: Clicking "Severity" column header in table (T016) sorts Critical → High → Medium → Low (not alphabetically)

---

### T018 [P] [US2] Add mitigation status icons via conditional formatting

**Implements**: FR-010  
**Files**: `enterprise-security.Report/report.json` → conditional formatting on table  
**Depends on**: T016 (table created)  
**Acceptance**:
- [ ] Apply conditional formatting to "Mitigation Status" column:
  - "Unassigned" → ⚠️ (yellow warning icon)
  - "Assigned" → ✅ (green check)
  - "In Progress" → 🔄 (blue circular arrow)
  - "Completed" → ✔️ (green checkmark filled)
- [ ] Test: Row with MitigationStatus = "Unassigned" shows ⚠️ icon

---

### T019 [P] [US2] Add finding type donut filtered to selected repo

**Implements**: FR-011  
**Files**: `enterprise-security.Report/report.json` → add donut chart  
**Depends on**: T015 (Page 2 created)  
**Acceptance**:
- [ ] Add donut chart visual (x=20, y=640, w=400, h=200)
- [ ] Legend: `Findings[FindingType]`
- [ ] Values: `COUNTROWS(Findings)`
- [ ] Page filter: Auto-filtered by selected repo from drill-through
- [ ] Test: When drilled to "payment-api", donut shows only payment-api findings distribution

---

### T020 [US2] Configure drill-through from Page 1 to Page 2

**Implements**: FR-007, FR-022  
**Files**: `enterprise-security.Report/report.json` → drill-through configuration  
**Depends on**: T009 (ranked repos chart), T015 (Page 2 created)  
**Acceptance**:
- [ ] Enable drill-through on ranked repos chart (T009)
- [ ] Drill-through target: Page 2 (Repository Deep Dive)
- [ ] Drill-through fields: `Repos[RepoName]`
- [ ] Test: Right-click "payment-api" bar on Page 1 → "Drill through" → Page 2 loads
- [ ] Test: Page 2 table shows only payment-api files (filter context preserved)
- [ ] Test: If Page 1 has severity filter (e.g., Critical only), Page 2 also shows only Critical (FR-022)

---

### T021 [US2] UAT: Security lead investigation workflow

**Implements**: SC-003 (drill-down in <3 clicks)  
**Files**: None (user testing)  
**Depends on**: T016-T020 (Page 2 complete)  
**Acceptance**:
- [ ] Task: "Find the unassigned critical finding in payment-api and tell me the file and line number"
- [ ] Measure: Number of clicks from Page 1 to answer (target: ≤3 clicks)
- [ ] Task: "Sort findings by severity and identify the top 3 issues"
- [ ] Test: Clicking severity column header correctly sorts Critical → High → Medium → Low
- [ ] Collect feedback: Is line number column useful? Any missing info?

**Checkpoint**: Page 2 (investigation layer) is complete — Security leads can drill to file-level detail

---

## Phase 4: Page 3 - Trends & Compliance (Part 1: User Story 3)

**Goal**: Complete User Story 3 (Compliance Team Prepares Audit Report)

**Independent Test**: Navigate to Page 3 → select "OWASP ASVS" in slicer → export compliance matrix to Excel

---

### T022 [P] [US4] Add time-series line chart (findings opened vs closed)

**Implements**: FR-012  
**Files**: `enterprise-security.Report/report.json` → add line chart to Page 3  
**Depends on**: T002 (DateTable exists)  
**Acceptance**:
- [ ] Create Page 3: "Trends & Compliance" (visible in navigation)
- [ ] Add line chart visual (x=20, y=20, w=1240, h=250)
- [ ] X-axis: `DateTable[Date]` with date range slicer (30/60/90 days)
- [ ] Y-axis: Two lines:
  1. Findings Opened (count of Findings where DateOpened in range)
  2. Findings Closed (count of Findings where DateClosed in range)
- [ ] Legend: "Opened" (solid line), "Closed" (dashed line)
- [ ] Test: Chart shows 30 opened, 25 closed over 90 days → 5-finding net increase visible

---

### T023 [P] [US4] Add mean time to remediate bar chart by severity

**Implements**: FR-013  
**Files**: `enterprise-security.Report/report.json` → add bar chart to Page 3  
**Depends on**: T004 (DaysToRemediate column)  
**Acceptance**:
- [ ] Add grouped bar chart (x=20, y=290, w=600, h=200)
- [ ] X-axis: `Findings[Severity]` (Critical, High, Medium, Low)
- [ ] Y-axis: `AVERAGE(Findings[DaysToRemediate])`
- [ ] Apply conditional formatting:
  - Red if >14 days
  - Yellow if 7-14 days
  - Green if <7 days
- [ ] Test: Critical bar shows 21 days in red when avg critical remediation = 21 days

---

### T024 [P] [US4] Add remediation funnel chart

**Implements**: Supporting visual for remediation velocity analysis  
**Files**: `enterprise-security.Report/report.json` → add funnel chart to Page 3  
**Depends on**: T001 (MitigationStatus validated)  
**Acceptance**:
- [ ] Add funnel chart (x=640, y=290, w=600, h=200)
- [ ] Stages (top to bottom):
  1. Detected (total findings)
  2. Assigned (MitigationStatus != "Unassigned")
  3. In Progress (MitigationStatus = "In Progress")
  4. Completed (MitigationStatus = "Completed")
- [ ] Test: Funnel narrows at "Assigned" if 40% of findings unassigned (shows bottleneck)

---

### T025 [US3] Add compliance mapping matrix table

**Implements**: FR-014  
**Files**: `enterprise-security.Report/report.json` → add table to Page 3  
**Depends on**: Compliance table exists with framework mappings  
**Acceptance**:
- [ ] Add table visual (x=20, y=520, w=1240, h=300)
- [ ] Columns: Framework, Control ID, Description, Findings Count, Coverage %
- [ ] Findings Count: `COUNTROWS(Findings)` where Compliance[ControlID] matches
- [ ] Coverage %: `DIVIDE(Completed findings, Total findings, 0) * 100`
  - Apply data bar conditional formatting (green = >80%, yellow = 50-80%, red = <50%)
- [ ] Test: Row for "OWASP ASVS V2.1" shows count = 5 findings, coverage = 60%

---

### T026 [US3] Add compliance framework slicer

**Implements**: FR-015  
**Files**: `enterprise-security.Report/report.json` → add slicer to Page 3  
**Depends on**: T025 (table created)  
**Acceptance**:
- [ ] Add slicer visual (x=20, y=480, w=400, h=60)
- [ ] Field: `Compliance[Framework]` (values: "OWASP ASVS", "NIST CSF", "SOC 2")
- [ ] Style: Dropdown (not list)
- [ ] Test: Selecting "OWASP ASVS" filters compliance matrix to show only OWASP controls

---

## Phase 5: Page 3 - Trends & Compliance (Part 2: User Story 5)

**Goal**: Complete User Story 5 (Network Team Validates Zscaler Compatibility)

**Independent Test**: Navigate to Page 3 → see Zscaler traffic lights → click ❌ Incompatible → drill to 2 repos with cert pinning

---

### T027 [US5] Add Zscaler compatibility traffic light visual

**Implements**: FR-016  
**Files**: `enterprise-security.Report/report.json` → add card visuals or icon set to Page 3  
**Depends on**: Netcompat table exists with CompatStatus column  
**Acceptance**:
- [ ] Add 3 card visuals (x=20, y=840, w=400 each, h=80)
  1. ✅ Compatible (count of Netcompat where Status = "Compatible")
  2. ⚠️ Warnings (count where Status = "Warning")
  3. ❌ Incompatible (count where Status = "Incompatible")
- [ ] Colors: Green (#388E3C), Yellow (#FBC02D), Red (#D32F2F)
- [ ] Enable drill-through to repo detail table when clicking incompatible card
- [ ] Test: Cards show 38 green, 5 yellow, 2 red when Netcompat data has those counts

---

### T028 [US5] Add Zscaler repo detail table (drill-through target)

**Implements**: Drill-down for FR-016  
**Files**: `enterprise-security.Report/report.json` → add table to Page 3 or new drill-through page  
**Depends on**: T027 (traffic lights created)  
**Acceptance**:
- [ ] Add table visual (x=440, y=840, w=800, h=160) or create drill-through page
- [ ] Columns: Repo, Issue Type (Cert Pinning, Custom SSL, Non-Standard Port), Affected Files, Recommendation
- [ ] Filter: Only repos with CompatStatus = "Incompatible" (when drilling from ❌ card)
- [ ] Test: Clicking ❌ Incompatible (2 repos) shows table with 2 rows: repos with cert pinning

**Checkpoint**: Page 3 is complete — Compliance team can export audit reports, DevOps monitors trends, Network team checks Zscaler

---

## Phase 6: Polish, Performance & Deployment

**Goal**: Validate dashboard meets performance, accessibility, and business success criteria

---

### T029 [POLISH] Configure dashboard settings and refresh schedule

**Implements**: FR-019, FR-020  
**Files**: Power BI Service workspace settings  
**Depends on**: T028 (all visuals complete)  
**Acceptance**:
- [ ] Publish dashboard to Power BI Premium workspace
- [ ] Configure scheduled refresh: Every 4 hours (6 refreshes/day)
- [ ] Set up refresh failure email alerts to admin
- [ ] Document manual refresh procedure (Power BI Desktop → Refresh → Publish)
- [ ] Verify Excel export works: Right-click any table → "Export data" → Excel file downloads

---

### T030 [POLISH] Performance validation

**Implements**: FR-021, SC-002  
**Files**: None (performance testing)  
**Depends on**: T029 (dashboard published)  
**Acceptance**:
- [ ] Load dashboard with full production dataset (10K findings, 50 repos)
- [ ] Measure: Time from click "Security Command Center" to all visuals loaded
- [ ] Target: <5 seconds
- [ ] If >5 seconds:
  - Run DAX Studio query analyzer to identify slow measures
  - Add Top N filter to ranked repos chart (already has Top 15)
  - Consider aggregation table for Trends data
- [ ] Test slicer performance: Click framework slicer → measure visual refresh time (target: <200ms)

---

### T031 [POLISH] Accessibility validation

**Implements**: FR-025, SC-008  
**Files**: None (accessibility testing)  
**Depends on**: T005 (color palette configured)  
**Acceptance**:
- [ ] Run Power BI Desktop → View → Accessibility Checker
- [ ] Verify: 0 errors, 0 warnings
- [ ] Manual checks:
  - [ ] All visuals have alt text describing what they show
  - [ ] Tab order follows logical reading flow (top-left to bottom-right)
  - [ ] Keyboard navigation works (Tab to move, Enter to select)
  - [ ] Contrast ratio ≥4.5:1 for all text on background
- [ ] Test with colorblind simulator: Red/green not used together

---

### T032 [POLISH] User acceptance testing (UAT) with 5 executives

**Implements**: SC-001, SC-006  
**Files**: None (user testing)  
**Depends on**: T030, T031 (performance and accessibility validated)  
**Acceptance**:
- [ ] Schedule 30-min UAT sessions with 5 execs (VP, CEO, Security Lead, Compliance Officer, DevOps Manager)
- [ ] Task 1 (VP): "Identify highest-risk repo" → Measure: Time to answer (target: <30 sec)
- [ ] Task 2 (Security Lead): "Drill to payment-api and find unassigned critical issues" → Measure: <3 clicks
- [ ] Task 3 (Compliance): "Export OWASP compliance report to Excel" → Measure: <2 min
- [ ] Survey question: "Do you prefer the new 3-page design or old 14-page design?" (target: 80% prefer new)
- [ ] Collect feedback: Any confusing visuals? Missing data? Performance issues?
- [ ] Document: High-priority changes (fix before launch), medium-priority (fix in v1.1), low-priority (backlog)

---

### T033 [POLISH] Training and documentation

**Implements**: Deployment support  
**Files**: None (training materials)  
**Depends on**: T032 (UAT complete)  
**Acceptance**:
- [ ] Create 1-page quick reference guide:
  - Page 1: What each KPI means, how to identify high-risk repos
  - Page 2: How to drill-through, how to sort by severity
  - Page 3: How to export compliance reports, how to check Zscaler status
- [ ] Schedule 30-min walkthrough with all users (live demo + Q&A)
- [ ] Record walkthrough video for async viewing
- [ ] Add "Help" text box on each page with key instructions

**Checkpoint**: Dashboard is production-ready — performance validated, accessibility compliant, users trained

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1: T001-T005)**: No dependencies — can start immediately. **BLOCKS all other phases**
- **Page 1 (Phase 2: T006-T014)**: Depends on Setup complete. **MVP — approval gate before proceeding**
- **Page 2 (Phase 3: T015-T021)**: Depends on Page 1 approved (T014)
- **Page 3 Part 1 (Phase 4: T022-T026)**: Depends on Setup complete (can run parallel to Page 2 if desired)
- **Page 3 Part 2 (Phase 5: T027-T028)**: Depends on Page 3 Part 1 structure created
- **Polish (Phase 6: T029-T033)**: Depends on all pages complete (T028)

### Critical Path

```
T001 (verify schema) → T003 (org risk score) → T006 (create Page 1) → T007 (KPI cards) → T009 (ranked repos) → T014 (UAT approval) → T015 (create Page 2) → T016 (findings table) → T020 (drill-through) → T029 (publish) → T030 (performance test) → T032 (UAT) → LAUNCH
```

### Parallel Opportunities

- **Setup phase**: T002, T004, T005 can run parallel (different measures/configs)
- **Page 1 visuals**: T010, T011, T012, T013 can run parallel (different chart types)
- **Page 2 visuals**: T018, T019 can run parallel after T016 (table) is done
- **Page 3 visuals**: T022, T023, T024 can all run parallel
- **Polish**: T030 (performance) and T031 (accessibility) can run parallel

### Blockers

**BLOCKER 1**: T001 reveals `Findings[LineNumber]` column missing  
- **Impact**: Cannot proceed to T016 (Page 2 findings table)  
- **Resolution**: Escalate to data team for ETL pipeline update. Estimate: 3-5 days. Can continue Page 1 and Page 3 work in parallel.

**BLOCKER 2**: T014 (Page 1 UAT) rejected by VP  
- **Impact**: Cannot proceed to Page 2/3 until changes made  
- **Resolution**: Document required changes, implement, re-test with VP, get approval

**BLOCKER 3**: T030 performance test fails (<5 seconds)  
- **Impact**: Cannot launch to production  
- **Resolution**: Optimize DAX measures, add aggregation tables, reduce visual complexity

---

## Implementation Strategy

### MVP First (Recommended)

1. Complete **Phase 1** (Setup: T001-T005) → **2-3 hours**
2. Complete **Phase 2** (Page 1: T006-T014) → **6-8 hours**
3. **STOP and VALIDATE**: T014 UAT with VP
4. If approved → Deploy Page 1 only to production (partial launch)
5. Continue Phase 3-6 (Page 2, Page 3, Polish) in next sprint

**Benefits:**
- VP gets value immediately (Page 1 command center)
- Early feedback loop reduces rework risk
- Phased rollout reduces change resistance

### Full Build (Alternative)

1. Complete all phases sequentially: Setup → Page 1 → Page 2 → Page 3 → Polish
2. Launch all 3 pages together
3. Duration: 20-25 hours over 2-3 weeks

**Benefits:**
- Single training session (not multiple rollouts)
- Complete feature set on day 1

---

## Execution Checklist

Before starting:
- [ ] Verify `Findings[LineNumber]` column exists (T001) — if missing, escalate to data team
- [ ] Backup current .pbip file (in case rollback needed)
- [ ] Review colorblind-safe palette (T005) with design team if PLMarketing has brand guidelines

During build:
- [ ] Commit after each phase (T005, T014, T021, T028, T033)
- [ ] Test drill-through after T020 (most complex interaction)
- [ ] Run accessibility checker after each page complete

After build:
- [ ] Archive old 14-page dashboard (don't delete — reference for rollback)
- [ ] Monitor Power BI refresh logs for first week (catch data issues early)
- [ ] Schedule 1-week follow-up with execs (collect post-launch feedback)

---

## dream-studio Integration

**Execution via**: `dream-studio:build` skill

**Task Tracking**: Use TaskCreate for each task, TaskUpdate to mark in_progress/completed

**Commit Strategy**: 
- Commit after each phase (5 commits total)
- Commit message format: "feat(page1): add KPI cards and ranked repos chart" (follows conventional commits)

**Traceability**: Active — see `.planning/traceability.yaml` for requirement → task → commit mapping

---

## Notes

- Power BI tasks = visual configuration, DAX formulas, report.json edits (not traditional code)
- "Tests" = manual validation by opening dashboard and verifying behavior
- [P] markers indicate visuals that can be built in parallel (different chart types, no dependencies)
- UAT gates (T014, T032) are critical — exec buy-in prevents rework
- Line number feature (T016) depends on ETL pipeline — verify T001 immediately to avoid late blocker
