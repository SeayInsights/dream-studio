# Feature Specification: Security Dashboard Redesign

**Topic Directory**: `.planning/specs/security-dashboard-redesign/`  
**Created**: 2026-04-27  
**Status**: Draft  
**Input**: Redesign the Kroger security dashboard Power BI layout to reduce duplication, show high-level metrics (repo-level counts not file-level detail), rank findings by priority, consolidate into fewer views with visual hierarchy, and maximize use of visuals over tables.

---

## Executive Summary

**Current State:** 14-page Power BI dashboard with excessive detail (file-level findings) and duplicative category pages (6 separate OWASP pages). VP/CEO must navigate multiple tabs to assess org-wide security posture.

**Problem:** Decision-makers need to answer "Are we secure?" in seconds, not minutes. Current structure buries risk insights under granular detail and forces tab-hopping for context.

**Solution:** Consolidate to **3 strategic pages** with visual hierarchy:
1. **Security Command Center** (hero view) — Org-level KPIs, ranked repos, trends
2. **Repository Deep Dive** (drill-through) — File-level investigation for selected repo
3. **Trends & Compliance** (supporting analytics) — Time-series, compliance mapping, specialty metrics

**Impact:** Reduce time-to-insight from 5-10 minutes (scanning 14 tabs) to <30 seconds (one-screen command center).

---

## User Scenarios & Testing

### User Story 1 - Executive Daily Risk Check (Priority: P1)

**Persona:** VP of Engineering, CEO  
**Journey:** Open dashboard Monday morning to assess weekend security posture before leadership meeting.

**Flow:**
1. Opens Power BI dashboard to Page 1 (Security Command Center)
2. Scans 5 KPI cards: Org Risk Score (67/100), Critical Issues (3), High Issues (12), Repos at Risk (8/45), Remediation Velocity (14 days avg)
3. Glances at risk trend line (declining over 30 days = good)
4. Identifies highest-risk repo in stacked bar chart (repo "payment-api" has 2 critical + 5 high)
5. Decides whether to escalate in leadership meeting

**Why this priority:** Executives spend 80% of their dashboard time here. If Page 1 fails, they won't dig deeper.

**Independent Test:** Can be fully tested by loading dashboard with synthetic data (3 critical findings across 2 repos) and verifying Page 1 shows: (a) risk score decreases, (b) "payment-api" appears at top of ranked chart, (c) KPI cards reflect correct totals.

**Acceptance Scenarios:**

1. **Given** org has 3 critical and 12 high-severity findings across 8 repos, **When** VP opens dashboard, **Then** KPI cards display "3 Critical", "12 High", "8 Repos at Risk"
2. **Given** risk score decreased from 72 to 67 over 7 days, **When** VP views trend line, **Then** chart shows downward slope with tooltip "67 (↓5 from last week)"
3. **Given** "payment-api" repo has the highest risk score (2 critical + 5 high), **When** VP scans ranked repos bar chart, **Then** "payment-api" appears at top with stacked red/orange bars
4. **Given** avg remediation velocity is 14 days, **When** VP checks velocity KPI, **Then** card shows "14 days" with conditional formatting (green if <7, yellow if 7-14, red if >14)

---

### User Story 2 - Security Lead Investigates High-Risk Repo (Priority: P1)

**Persona:** Security Engineer, DevOps Lead  
**Journey:** VP flagged "payment-api" as high-risk. Security lead drills down to investigate specific vulnerabilities and assign mitigations.

**Flow:**
1. On Page 1, clicks "payment-api" bar in ranked repos chart
2. Drills through to Page 2 (Repository Deep Dive)
3. Reviews file-level findings table filtered to "payment-api":
   - `auth.py:142` - SQL Injection (Critical, CWE-89)
   - `config.py:23` - Hardcoded Secret (High, CWE-798)
   - `api.py:87` - Broken Access Control (High, CWE-284)
4. Sorts table by severity (Critical → High → Medium)
5. Checks mitigation status column (2 assigned, 1 unassigned)
6. Creates GitHub issue for unassigned critical finding

**Why this priority:** This is the action layer. Execs identify risk (Story 1), engineers fix it (Story 2). Both are MVP.

**Independent Test:** Can be fully tested by: (a) creating test data for "payment-api" with 3 findings, (b) clicking repo bar on Page 1, (c) verifying Page 2 shows only "payment-api" files, (d) verifying findings table sorts by severity, (e) verifying mitigation status column shows assigned/unassigned.

**Acceptance Scenarios:**

1. **Given** user clicks "payment-api" on Page 1, **When** drill-through fires, **Then** Page 2 loads with repo filter = "payment-api" and shows only files from that repo
2. **Given** "payment-api" has findings in 3 files, **When** user views findings table, **Then** table shows 3 rows with columns: File, Line, Severity, CWE, Finding Type, Mitigation Status
3. **Given** user clicks severity column header, **When** sort applies, **Then** rows reorder: Critical → High → Medium → Low
4. **Given** 2 findings have assigned mitigations, **When** user views mitigation status column, **Then** icons show ✅ (assigned) or ⚠️ (unassigned)

---

### User Story 3 - Compliance Team Prepares Audit Report (Priority: P2)

**Persona:** Compliance Officer, Security Auditor  
**Journey:** Annual SOC 2 audit requires mapping findings to control frameworks (OWASP ASVS, NIST CSF).

**Flow:**
1. Navigates to Page 3 (Trends & Compliance)
2. Views compliance mapping matrix:
   - OWASP ASVS controls coverage (e.g., V2.1 Auth, V3.4 Access Control)
   - NIST CSF controls mapped to findings (e.g., PR.AC-4, DE.CM-8)
3. Filters by compliance framework (dropdown slicer)
4. Exports compliance table to Excel for audit submission
5. Shares Zscaler compatibility status with network team

**Why this priority:** P2 because compliance is periodic (quarterly/annual), not daily. Still critical for audit success but not part of daily ops.

**Independent Test:** Can be fully tested by: (a) loading test data with findings mapped to OWASP V2.1 and NIST PR.AC-4, (b) navigating to Page 3, (c) selecting "OWASP ASVS" in slicer, (d) verifying matrix shows only OWASP controls, (e) exporting table and validating Excel output.

**Acceptance Scenarios:**

1. **Given** compliance data exists for OWASP ASVS and NIST CSF, **When** user selects "OWASP ASVS" in framework slicer, **Then** compliance matrix filters to show only OWASP controls (V2.x, V3.x series)
2. **Given** 12 findings map to NIST PR.AC-4 (Access Control), **When** user views NIST mapping, **Then** PR.AC-4 row shows count = 12 with drill-through to finding details
3. **Given** user clicks "Export" on compliance table, **When** export completes, **Then** Excel file downloads with columns: Control ID, Framework, Description, Findings Count, Coverage %

---

### User Story 4 - DevOps Monitors Remediation Progress Over Time (Priority: P2)

**Persona:** Engineering Manager, DevOps Lead  
**Journey:** Monthly sprint planning. Need to assess if remediation velocity is improving and whether high-severity backlog is shrinking.

**Flow:**
1. Navigates to Page 3 (Trends & Compliance)
2. Views time-series charts:
   - Findings opened vs. closed (line chart, 90-day trend)
   - Mean time to remediate by severity (bar chart)
   - Backlog growth rate (area chart)
3. Identifies bottleneck: Critical findings take 21 days avg to remediate (target: <7 days)
4. Drills into remediation funnel to see where delays occur (detection → assignment → fix → verify)
5. Adjusts sprint capacity to prioritize critical backlog

**Why this priority:** P2 because trend analysis is strategic (monthly planning) vs. tactical (daily monitoring in Story 1). Still valuable for continuous improvement.

**Independent Test:** Can be fully tested by: (a) generating time-series test data (30 findings opened, 25 closed over 90 days), (b) navigating to Page 3, (c) verifying line chart shows 30 opened / 25 closed, (d) verifying mean time to remediate = 21 days for critical findings, (e) clicking funnel chart and validating drill-through to remediation stages.

**Acceptance Scenarios:**

1. **Given** 30 findings opened and 25 closed in last 90 days, **When** user views findings trend chart, **Then** chart shows two lines (opened = 30, closed = 25) with 5-finding net increase
2. **Given** critical findings take avg 21 days to remediate, **When** user views remediation velocity chart, **Then** critical bar = 21 days with red conditional formatting (threshold: >7 days = red)
3. **Given** remediation funnel shows 40% delay in "assignment" stage, **When** user clicks funnel segment, **Then** drill-through opens table of unassigned findings with repo/severity breakdown

---

### User Story 5 - Network Team Validates Zscaler Compatibility (Priority: P3)

**Persona:** Network Engineer, IT Ops  
**Journey:** PLMarketing uses Zscaler proxy. Need to verify which apps have compatibility issues (cert pinning, non-standard ports) before deploying new policies.

**Flow:**
1. Navigates to Page 3 (Trends & Compliance)
2. Scrolls to Zscaler Compatibility section
3. Views repo compatibility matrix:
   - ✅ Compatible (38 repos)
   - ⚠️ Warnings (5 repos - custom SSL)
   - ❌ Incompatible (2 repos - cert pinning detected)
4. Drills into "cert pinning" repos to see affected files
5. Creates tickets for dev teams to remediate cert pinning

**Why this priority:** P3 because Zscaler compatibility is niche (network ops only) and not tied to security risk scoring. Important for operational compliance but not exec-level concern.

**Independent Test:** Can be fully tested by: (a) loading netcompat test data (2 repos with cert pinning, 5 with SSL warnings), (b) navigating to Page 3, (c) verifying compatibility matrix shows 38 green / 5 yellow / 2 red, (d) clicking red segment and validating drill-through to cert-pinned repos.

**Acceptance Scenarios:**

1. **Given** 2 repos have cert pinning detected, **When** user views Zscaler section, **Then** compatibility matrix shows ❌ count = 2 with red visual
2. **Given** user clicks ❌ incompatible segment, **When** drill-through fires, **Then** table displays 2 repos with columns: Repo, Issue Type (Cert Pinning), Affected Files, Recommendation
3. **Given** 5 repos have SSL warnings, **When** user hovers over ⚠️ segment, **Then** tooltip shows "5 repos with custom SSL configuration - review required"

---

### Edge Cases

- **What happens when org risk score is null (no findings data)?**  
  → KPI card shows "N/A - No data available" with gray background. Trend chart hidden. Drill-through disabled.

- **What happens when a repo has 0 findings but still appears in data?**  
  → Repo excluded from "Repos at Risk" count but appears in full repo inventory on Page 3 with ✅ status.

- **What happens when user drills through on Page 1 but no file-level data exists?**  
  → Page 2 shows "No detailed findings for [repo name]. Check data refresh status." with refresh timestamp.

- **What happens when compliance framework has no mapped findings?**  
  → Compliance matrix row shows control ID + 0 findings, but control is not hidden (still shows coverage gap).

- **What happens when remediation velocity is infinite (0 findings closed)?**  
  → KPI card shows "— days (No findings closed yet)" with neutral gray color instead of red/yellow/green.

- **What happens when time-series data has gaps (e.g., no findings for a week)?**  
  → Trend line interpolates missing dates with dotted line + tooltip "No data for [date range]".

- **What happens when user applies slicer filters that result in empty dataset?**  
  → Visuals show "No data matches current filters. Clear filters to view all data." with reset button.

- **What happens when drill-through fires but page filter fails to apply?**  
  → Error handler shows "Drill-through failed. Refresh dashboard and try again. Contact admin if issue persists."

- **What happens when a finding has no line number (NULL or 0)?**  
  → Table displays "-" in Line column (indicates file-level finding, e.g., missing dependency). Tooltip explains "File-level issue - no specific line identified."

---

## Requirements

### Functional Requirements

- **FR-001**: Page 1 MUST display 5 KPI cards in single horizontal row: Org Risk Score, Critical Findings, High Findings, Repos at Risk, Remediation Velocity
- **FR-002**: Page 1 MUST show repos ranked by risk score in descending order (highest risk at top) as horizontal stacked bar chart with severity segments (Critical = red, High = orange, Medium = yellow, Low = green)
- **FR-003**: Page 1 MUST display 30-day risk score trend line with tooltip showing daily score + change from previous day
- **FR-004**: Page 1 MUST show category distribution as donut chart with segments for each OWASP category (Injection, Auth, Secrets, Data Protection, Dependencies, Misconfiguration) sized by finding count
- **FR-005**: Page 1 MUST display top 5 vulnerabilities by count as horizontal bar chart ranked by frequency
- **FR-006**: Page 1 MUST show remediation velocity as single KPI with conditional formatting: green (<7 days), yellow (7-14 days), red (>14 days)
- **FR-007**: Users MUST be able to drill through from ranked repos chart on Page 1 to Page 2 with automatic repo filter applied
- **FR-008**: Page 2 MUST display file-level findings table with columns: File, Line, Severity, CWE, Finding Type, Mitigation Status, Last Updated
- **FR-009**: Page 2 MUST allow sorting by severity with order: Critical → High → Medium → Low
- **FR-010**: Page 2 MUST show mitigation status as icon (✅ assigned, ⚠️ unassigned, 🔄 in progress, ✔️ completed)
- **FR-011**: Page 2 MUST display finding type distribution donut chart filtered to selected repo
- **FR-012**: Page 3 MUST display time-series line chart for findings opened vs. closed over selectable date range (30/60/90 days)
- **FR-013**: Page 3 MUST show mean time to remediate as grouped bar chart by severity (Critical, High, Medium, Low)
- **FR-014**: Page 3 MUST display compliance mapping matrix with columns: Framework, Control ID, Description, Findings Count, Coverage %
- **FR-015**: Page 3 MUST allow filtering compliance matrix by framework via slicer (OWASP ASVS, NIST CSF, SOC 2)
- **FR-016**: Page 3 MUST show Zscaler compatibility status as traffic light visual (✅ Compatible, ⚠️ Warnings, ❌ Incompatible) with counts
- **FR-017**: System MUST calculate org risk score using weighted formula: `(Critical × 10) + (High × 5) + (Medium × 2) + (Low × 1) / Total Repos`
- **FR-018**: System MUST calculate remediation velocity as: `AVG(Date Closed - Date Opened)` for findings closed in last 90 days
- **FR-019**: System MUST refresh data automatically on dashboard load (Power BI refresh or live connection to dataset)
- **FR-020**: Users MUST be able to export any table visual to Excel via Power BI native export
- **FR-021**: Dashboard MUST load in <5 seconds for dataset with 10,000 findings across 50 repos
- **FR-022**: Dashboard MUST support drill-through with filter context preserved (e.g., if Page 1 filtered to "Critical only", Page 2 inherits that filter)
- **FR-023**: KPI cards MUST display change indicators (↑↓) comparing current value to previous period (e.g., "67 ↓5 from last week")
- **FR-024**: Ranked repos chart MUST show top 15 repos only (to avoid overcrowding). Link to "View All Repos" table on Page 3
- **FR-025**: All charts MUST use colorblind-safe palette: Red (#D32F2F), Orange (#F57C00), Yellow (#FBC02D), Green (#388E3C), Blue (#1976D2), Gray (#757575)
- **FR-026**: Page 2 findings table MUST display line number for each finding to enable developers to jump directly to problematic code
- **FR-027**: Line number column MUST be sortable and filterable (e.g., show only findings in lines 1-100)

### Key Entities

- **Org Risk Score**: Calculated metric representing overall org security posture (0-100 scale, lower = better). Aggregates weighted severity across all repos. Used as hero KPI on Page 1.

- **Finding**: Individual security vulnerability detected in a file. Attributes: severity (Critical/High/Medium/Low), CWE ID, finding type (OWASP category), repo, file path, line number, date detected, mitigation status. Primary grain for drill-down analysis. Line number enables developers to jump directly to problematic code.

- **Repo**: Code repository (e.g., "payment-api", "user-service"). Aggregation level for risk ranking. Attributes: name, risk score (calculated), total findings, critical count, high count, Zscaler compat status.

- **Mitigation**: Remediation action for a finding. Attributes: status (unassigned/assigned/in progress/completed), assignee, date assigned, date completed, remediation type (code fix/config change/suppression).

- **Compliance Control**: Framework control (e.g., OWASP ASVS V2.1, NIST CSF PR.AC-4) mapped to findings. Attributes: framework name, control ID, description, findings count, coverage % (findings addressed / total).

- **Trend Data Point**: Time-series snapshot of findings. Attributes: date, findings opened count, findings closed count, org risk score, repo-level breakdown. Granularity: daily. Retention: 90 days minimum.

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: VP/CEO can determine org security posture within 30 seconds of opening Page 1 (measured via user testing with 5 execs - target: 100% success rate)
- **SC-002**: Time to identify highest-risk repo reduces from 5-10 minutes (scanning 14 tabs) to <10 seconds (scanning Page 1 ranked chart) - measured via A/B test with current vs. new dashboard
- **SC-003**: Security engineers can drill from repo identification to file-level investigation in <3 clicks (Page 1 → drill-through → sort by severity) - measured via click tracking
- **SC-004**: Dashboard loads in <5 seconds for 10,000 findings across 50 repos on standard PLMarketing hardware (measured via DAX Studio query performance)
- **SC-005**: Compliance team can export audit report with 100% data accuracy (no missing/incorrect control mappings) - validated via manual audit sample (50 findings)
- **SC-006**: 80% of execs prefer new 3-page design over old 14-page design (measured via post-deployment survey with 5-point Likert scale)
- **SC-007**: Reduce dashboard maintenance time by 50% (fewer pages = fewer visuals to update when data schema changes) - measured via dev team time tracking
- **SC-008**: Zero accessibility violations (WCAG 2.1 AA compliance for color contrast, keyboard navigation) - validated via Power BI Accessibility Checker

---

## Approach & Design Details

### Chosen Approach: Executive KPI Dashboard (3 Pages)

**Why this approach:**
- **Executive-first:** Page 1 optimized for C-level scanning (5-second risk assessment)
- **Drill hierarchy:** Org → Repo → File matches mental model of risk investigation
- **Separation of concerns:** Daily ops (Page 1), investigation (Page 2), compliance/trends (Page 3)
- **Visual storytelling:** Ranked repos, trend lines, and category donuts answer "what's broken" without reading tables
- **Remediation-centric:** Velocity metric on Page 1 shows progress, not just problems

**Alternative approaches considered:**
1. **Risk-First Dashboard (4 pages):** More granular category breakdown but adds a 4th page (defeats consolidation goal)
2. **Single-Page Dashboard:** Everything on one scrollable page. Too dense for quick scanning; execs scroll past critical info.

### Page 1: Security Command Center (Layout Spec)

**Screen Resolution Target:** 1920×1080 (optimized for dual-monitor setups)

**Layout Grid (720px tall canvas):**

```
┌─────────────────────────────────────────────────────────────────┐
│  [KPI Cards Row - 60px tall each]                               │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐                  │
│  │ Risk │ │Crit  │ │High  │ │Repos │ │Velocity                 │
│  │ 67   │ │  3   │ │  12  │ │ 8/45 │ │14 days │                │
│  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘                  │
├─────────────────────────────────────────────────────────────────┤
│  [Trend Line - 200px tall] │ [Category Donut - 200px tall]      │
│  Risk Score Over Time      │  Findings by OWASP Category        │
│  (30-day trend)            │  (Injection, Auth, Secrets...)     │
├────────────────────────────┴────────────────────────────────────┤
│  [Ranked Repos Chart - 300px tall, full width]                  │
│  Repos Ranked by Risk (horizontal stacked bars)                 │
│  payment-api    ███ 2C + 5H + 3M + 1L                           │
│  user-service   ██  1C + 3H + 2M + 0L                           │
│  billing-api    █   0C + 2H + 4M + 2L                           │
│  ...                                                             │
├─────────────────────────────────────────────────────────────────┤
│  [Top Vulnerabilities - 160px tall]                             │
│  SQL Injection (12) ████████                                    │
│  Hardcoded Secrets (8) █████                                    │
│  Broken Auth (5) ███                                            │
└─────────────────────────────────────────────────────────────────┘
```

**Visual Hierarchy Rules:**
- KPI cards use 32px font for numbers, 12px for labels
- Trend line uses primary brand color (#1976D2) with 2px stroke
- Ranked repos use stacked bars with severity colors (Critical=red, High=orange, Medium=yellow, Low=green)
- Category donut uses 6-slice palette (colorblind-safe)
- Top vulnerabilities use horizontal bars ranked by count

**Interactivity:**
- Clicking any repo bar drills through to Page 2 with repo filter
- Clicking category donut slice filters Page 1 to that category
- Hovering KPI cards shows tooltip with previous period comparison

---

### Page 2: Repository Deep Dive (Layout Spec)

```
┌─────────────────────────────────────────────────────────────────┐
│  [Repo Selector Slicer - 60px tall]                             │
│  Selected Repo: payment-api ▼                                   │
├─────────────────────────────────────────────────────────────────┤
│  [Summary Cards - 60px tall each]                               │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐                           │
│  │Total │ │Crit  │ │High  │ │Assigned                          │
│  │ 11   │ │  2   │ │  5   │ │ 7/11   │                         │
│  └──────┘ └──────┘ └──────┘ └──────┘                           │
├─────────────────────────────────────────────────────────────────┤
│  [File-Level Findings Table - 400px tall, full width]          │
│  File         │ Line │ Severity │ CWE    │ Type          │ Status      │
│  ─────────────┼──────┼──────────┼────────┼───────────────┼────────────│
│  auth.py      │ 142  │ Critical │ CWE-89 │ SQL Injection │ ⚠️ Unassign│
│  config.py    │  23  │ High     │ CWE-798│ Hardcoded Sec │ ✅ Assigned│
│  api.py       │  87  │ High     │ CWE-284│ Broken Access │ ✅ Assigned│
│  ...          │      │          │        │               │            │
├─────────────────────────────────────────────────────────────────┤
│  [Finding Type Donut - 200px] │ [Mitigation Funnel - 200px]    │
│  Filtered to selected repo    │ Detection → Assignment → Fix   │
└─────────────────────────────────────────────────────────────────┘
```

**Interactivity:**
- Clicking row in findings table opens detail pane with CWE description, affected code snippet, remediation recommendation
- Line number column displays as clickable link format (e.g., "auth.py:142") — future enhancement: deep link to GitHub/repo viewer
- Sorting by severity uses custom sort order (Critical → High → Medium → Low)
- Mitigation status column clickable to filter table (e.g., click ⚠️ to see only unassigned)

---

### Page 3: Trends & Compliance (Layout Spec)

```
┌─────────────────────────────────────────────────────────────────┐
│  [Time-Series Chart - 250px tall, full width]                   │
│  Findings Opened vs. Closed (90-day trend)                      │
│  ──── Opened (30)  ──── Closed (25)                             │
├─────────────────────────────────────────────────────────────────┤
│  [Remediation Velocity - 200px] │ [Backlog Growth - 200px]      │
│  Mean Time to Remediate         │ Net Findings Over Time        │
│  Critical: 21d ███ (red)        │ (area chart)                  │
│  High: 14d ██ (yellow)          │                               │
├─────────────────────────────────────────────────────────────────┤
│  [Compliance Matrix - 300px tall, full width]                   │
│  Framework Slicer: [OWASP ASVS ▼] [NIST CSF] [SOC 2]           │
│  Control ID │ Description       │ Findings │ Coverage %         │
│  V2.1.1     │ Password strength │    5     │ 60% ████░░         │
│  V3.4.2     │ Access control    │   12     │ 40% ██░░░░         │
├─────────────────────────────────────────────────────────────────┤
│  [Zscaler Compatibility - 200px tall]                           │
│  ✅ Compatible (38) │ ⚠️ Warnings (5) │ ❌ Incompatible (2)    │
└─────────────────────────────────────────────────────────────────┘
```

**Interactivity:**
- Date range slicer for time-series (30/60/90 days)
- Compliance framework slicer filters matrix
- Clicking Zscaler status drills to repo list with compatibility details

---

### Data Model Changes Required

**Current Tables:** Findings, Mitigations, Compliance, Repos, Trends, Netcompat

**New Calculated Columns Needed:**

1. **Repos[RiskScore]** = 
   ```dax
   (CALCULATE(COUNTROWS(Findings), Findings[Severity] = "Critical") * 10) +
   (CALCULATE(COUNTROWS(Findings), Findings[Severity] = "High") * 5) +
   (CALCULATE(COUNTROWS(Findings), Findings[Severity] = "Medium") * 2) +
   (CALCULATE(COUNTROWS(Findings), Findings[Severity] = "Low") * 1)
   ```

2. **Findings[DaysToRemediate]** = 
   ```dax
   IF(
       ISBLANK(Findings[DateClosed]),
       BLANK(),
       DATEDIFF(Findings[DateOpened], Findings[DateClosed], DAY)
   )
   ```

3. **Compliance[CoveragePercent]** = 
   ```dax
   DIVIDE(
       CALCULATE(COUNTROWS(Findings), Findings[MitigationStatus] = "Completed"),
       COUNTROWS(Findings),
       0
   ) * 100
   ```

**New Measures Needed:**

1. **[Org Risk Score]** = 
   ```dax
   VAR TotalFindings = 
       (COUNTROWS(FILTER(Findings, Findings[Severity] = "Critical")) * 10) +
       (COUNTROWS(FILTER(Findings, Findings[Severity] = "High")) * 5) +
       (COUNTROWS(FILTER(Findings, Findings[Severity] = "Medium")) * 2) +
       (COUNTROWS(FILTER(Findings, Findings[Severity] = "Low")) * 1)
   VAR TotalRepos = DISTINCTCOUNT(Repos[RepoName])
   RETURN DIVIDE(TotalFindings, TotalRepos, 0)
   ```

2. **[Remediation Velocity]** = 
   ```dax
   CALCULATE(
       AVERAGE(Findings[DaysToRemediate]),
       Findings[DateClosed] >= TODAY() - 90,
       NOT(ISBLANK(Findings[DateClosed]))
   )
   ```

3. **[Repos at Risk]** = 
   ```dax
   CALCULATE(
       DISTINCTCOUNT(Repos[RepoName]),
       FILTER(Repos, Repos[RiskScore] > 0)
   ) & " / " & DISTINCTCOUNT(Repos[RepoName])
   ```

4. **[Change from Last Week]** (for KPI cards) = 
   ```dax
   VAR CurrentValue = [Org Risk Score]
   VAR LastWeekValue = 
       CALCULATE(
           [Org Risk Score],
           DATEADD(DateTable[Date], -7, DAY)
       )
   RETURN CurrentValue - LastWeekValue
   ```

---

## Assumptions

- **Target users:** VP/CEO (executives), Security Engineers, DevOps Leads, Compliance Officers, Network Engineers. Primary persona = VP/CEO (80% usage on Page 1).
- **Data refresh frequency:** Dashboard connects to live dataset refreshed every 4 hours via Power BI scheduled refresh or DirectQuery. Assume dataset < 50MB (10K findings × 50 repos).
- **Scope boundaries:** Mobile support out of scope for v1 (desktop Power BI only). Paginated reports out of scope (use Excel export instead).
- **Existing infrastructure:** Power BI Premium workspace available for deployment. Users have Power BI Pro licenses. No Row-Level Security required (all users see org-wide data).
- **Compliance frameworks:** OWASP ASVS and NIST CSF are minimum required. SOC 2 mapping is P2 (add if time permits).
- **Zscaler compatibility:** Data sourced from `dream-studio:netcompat` scans. Assume `Netcompat` table has columns: Repo, CompatStatus (Compatible/Warning/Incompatible), IssueType (Cert Pinning, Custom SSL, Non-Standard Port).
- **Historical data retention:** Trends table has 90 days of history minimum. If <90 days, chart shows "Insufficient data for 90-day trend" message.
- **Drill-through behavior:** Assumes Power BI drill-through pages enabled. Drill-through clears all other filters except repo filter. User can manually add filters on Page 2.
- **Export capability:** Users can export any table to Excel via Power BI native export. No custom export buttons needed.
- **Accessibility:** Dashboard must meet WCAG 2.1 AA standards (colorblind-safe palette, keyboard navigation, alt text for visuals). No screen reader optimization required for v1.
- **Line number capture:** Assumes security scanning tools (SAST/DAST) output includes line numbers for each finding. If `Findings` table currently lacks `LineNumber` column, ETL pipeline must be updated to capture this from scan output (e.g., Semgrep JSON, CodeQL SARIF). Line number = 0 or NULL indicates finding applies to entire file (e.g., missing dependency).
- **Conditional formatting thresholds:** 
  - Remediation Velocity: Green (<7d), Yellow (7-14d), Red (>14d)
  - Org Risk Score: Green (<50), Yellow (50-75), Red (>75)
  - Coverage %: Green (>80%), Yellow (50-80%), Red (<50%)

---

## Visual Design Standards

### Color Palette (Colorblind-Safe)

- **Critical/Red:** `#D32F2F` (accessible with white text, contrast ratio 4.5:1)
- **High/Orange:** `#F57C00` (accessible with white text)
- **Medium/Yellow:** `#FBC02D` (accessible with black text)
- **Low/Green:** `#388E3C` (accessible with white text)
- **Primary/Blue:** `#1976D2` (brand color for trend lines, buttons)
- **Neutral/Gray:** `#757575` (for labels, gridlines)
- **Background:** `#FFFFFF` (white canvas)
- **Accent/Dark:** `#212121` (for headings, borders)

### Typography

- **Headings (Page Titles):** Segoe UI Bold, 24px, #212121
- **KPI Numbers:** Segoe UI Bold, 32px, #212121
- **KPI Labels:** Segoe UI Regular, 12px, #757575
- **Chart Labels:** Segoe UI Regular, 10px, #757575
- **Table Headers:** Segoe UI Semibold, 11px, #212121
- **Table Body:** Segoe UI Regular, 10px, #212121

### Spacing & Sizing

- **KPI Card Padding:** 16px all sides
- **Chart Margins:** 20px top/bottom, 16px left/right
- **Table Row Height:** 32px (allows 12-15 rows visible without scrolling)
- **Visual Borders:** 1px solid #E0E0E0
- **Drillthrough Icon:** 16×16px (right-aligned in chart titles)

### Iconography

- **Mitigation Status Icons:**
  - ✅ Assigned (green check)
  - ⚠️ Unassigned (yellow warning)
  - 🔄 In Progress (blue circular arrow)
  - ✔️ Completed (green checkmark filled)
- **Trend Indicators:**
  - ↑ Increase (red if bad metric, green if good)
  - ↓ Decrease (green if bad metric, red if good)
  - → No change (gray)

---

## Implementation Notes

### Phase 1: Page 1 Build (Week 1)
1. Create 5 KPI card measures
2. Build ranked repos horizontal stacked bar chart (test with 15 repos)
3. Add 30-day trend line (test with sparse data)
4. Add category donut + top vulnerabilities bar
5. Configure drill-through to Page 2 (test filter passthrough)

### Phase 2: Page 2 Build (Week 1)
1. Build file-level findings table with custom severity sort
2. Add line number column (display as "File:Line" or separate column, handle NULL/0 as "-")
3. Add mitigation status icons (conditional formatting)
4. Add repo slicer + summary cards
5. Test drill-through from Page 1 → Page 2 with 3 repos

### Phase 3: Page 3 Build (Week 2)
1. Build time-series chart (findings opened vs. closed)
2. Add remediation velocity bar chart with conditional formatting
3. Build compliance matrix with framework slicer
4. Add Zscaler compatibility traffic lights

### Phase 4: Polish & Testing (Week 2)
1. Apply colorblind-safe palette globally
2. Add tooltips to all visuals
3. Test dashboard performance with 10K findings
4. Run accessibility checker (WCAG 2.1 AA)
5. User acceptance testing with VP/CEO

### Phase 5: Deployment (Week 3)
1. Publish to Power BI Premium workspace
2. Configure scheduled refresh (every 4 hours)
3. Train users (30-min walkthrough)
4. Monitor usage analytics (track Page 1 vs. Page 2 vs. Page 3 views)

---

## Open Questions for Director Approval

1. **Compliance Tab Requirement:** Is Page 3 (Compliance Mapping) required for daily ops, or can it be a separate paginated report for audit export only? Would save development time to defer compliance mapping to Phase 2.

2. **Zscaler Visibility:** Should Zscaler compatibility appear on Page 1 (exec view) or is Page 3 sufficient? Network team is secondary audience.

3. **Historical Trend Depth:** 90-day trend is default. Do execs need 6-month or 1-year historical trends for strategic planning? Impacts data retention requirements.

4. **Drill-Through vs. Bookmarks:** Should Page 2 be a true drill-through page (hidden from nav) or a visible bookmark? Drill-through is cleaner but less discoverable.

5. **Mobile Support Priority:** Out of scope for v1, but is mobile Power BI app access a near-term requirement (Q2 2026)? Would influence layout decisions now.

6. **Export Requirements:** Excel export sufficient, or do compliance auditors need automated PDF reports with screenshots? PDF generation requires paginated reports (additional dev work).

---

## dream-studio Integration

**Skill Flow**: think → plan → build → review → verify → ship

**Output Location**: `.planning/specs/security-dashboard-redesign/spec.md`

**Next Steps**: 
1. **Director Approval Required:** Review this spec and answer open questions above.
2. Once approved, run `dream-studio:plan` to break into implementation tasks (4 phases × ~8 tasks = 32 task backlog).
3. Output will be `.planning/specs/security-dashboard-redesign/plan.md` and `tasks.md`.
4. Assign to Power BI developer (Dannis) for build execution via `dream-studio:build`.

**Estimated Effort:**
- Spec (complete): 3 hours
- Plan: 1 hour
- Build: 2-3 weeks (part-time, 10 hours/week)
- Review + Verify: 3-5 hours
- Total: 25-35 hours

**Risk Factors:**
- **Data model changes:** If `Findings` table missing required columns (DateClosed, MitigationStatus), ETL pipeline update needed (add 1 week).
- **Performance:** 10K findings across 50 repos should perform well, but if dataset grows to 100K+ findings, consider aggregation tables (add 3-5 days).
- **User adoption:** Execs accustomed to 14-tab structure. Change management required (training + feedback loop).
