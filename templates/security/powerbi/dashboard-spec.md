# Enterprise Security Dashboard — Power BI Specification

**Template:** `enterprise-security.pbit`
**Data source:** CSV files from `~/.dream-studio/security/datasets/{client}/`
**Pages:** 16 total (pages 1-14 cover SAST/compliance/netcompat; pages 15-16 cover DAST and binary analysis)

---

## Data Model

### Tables (CSV imports)

| Table | Source file | Row grain |
|---|---|---|
| Findings | findings.csv | One row per finding |
| Mitigations | mitigations.csv | One row per finding mitigation |
| Compliance | compliance.csv | One row per framework control |
| Repos | repos.csv | One row per repository |
| Trends | trends.csv | One row per scan date |
| Netcompat | netcompat.csv | One row per repository |
| Metadata | metadata.json | Single record (flatten to table) |

### Relationships

| From (table.column) | To (table.column) | Cardinality | Cross-filter |
|---|---|---|---|
| Findings.id | Mitigations.finding_id | 1:1 | Both |
| Findings.repo | Repos.name | M:1 | Single (Repos → Findings) |
| Repos.name | Netcompat.repo | 1:1 | Both |
| Trends.date | (Date table).Date | M:1 | Single |

**Note:** Findings.compliance_controls is a semicolon-delimited string. Use a calculated column to split it for M:N relationship with Compliance, or use `CONTAINSSTRING()` in measures.

### Date Table (calculated)

```dax
DateTable =
ADDCOLUMNS(
    CALENDARAUTO(),
    "Year", YEAR([Date]),
    "Month", FORMAT([Date], "MMM YYYY"),
    "MonthNum", MONTH([Date]),
    "Week", WEEKNUM([Date]),
    "DayOfWeek", FORMAT([Date], "ddd")
)
```

### Parameters

| Parameter | Default | Purpose |
|---|---|---|
| ClientName | (from metadata.json client_name) | Display in titles |
| Enterprise | (from metadata.json enterprise) | Display in titles |
| DatasetPath | ~/.dream-studio/security/datasets/{client}/ | CSV folder connection |
| GreenThreshold | 85 | Org score RAG boundary |
| YellowThreshold | 60 | Org score RAG boundary |

---

## Shared DAX Measures

These measures are referenced across multiple pages. Define them once in a `_Measures` table (empty table used as a measure container).

### Finding Counts

```dax
Total Findings =
COUNTROWS(Findings)
```

```dax
Critical Findings =
CALCULATE(
    COUNTROWS(Findings),
    Findings[severity] = "critical"
)
```

```dax
High Findings =
CALCULATE(
    COUNTROWS(Findings),
    Findings[severity] = "high"
)
```

```dax
Medium Findings =
CALCULATE(
    COUNTROWS(Findings),
    Findings[severity] = "medium"
)
```

```dax
Low Findings =
CALCULATE(
    COUNTROWS(Findings),
    Findings[severity] = "low"
)
```

```dax
Open Findings =
CALCULATE(
    COUNTROWS(Findings),
    Findings[status] = "open"
)
```

```dax
Resolved Findings =
CALCULATE(
    COUNTROWS(Findings),
    Findings[status] = "resolved"
)
```

### Severity Weights

```dax
Weighted Penalty =
SUMX(
    Findings,
    SWITCH(
        Findings[severity],
        "critical", 10,
        "high", 4,
        "medium", 1,
        "low", 0.25,
        0.25
    )
)
```

### Org Score

```dax
Org Score =
VAR _total = COUNTROWS(Findings)
VAR _penalty = [Weighted Penalty]
VAR _ceiling = _total * 10
VAR _pct = IF(_ceiling > 0, DIVIDE(_penalty, _ceiling) * 100, 0)
RETURN
    MAX(0, ROUND(100 - _pct, 1))
```

### RAG Status

```dax
RAG Status =
VAR _score = [Org Score]
RETURN
    SWITCH(
        TRUE(),
        _score >= [GreenThreshold], "Green",
        _score >= [YellowThreshold], "Yellow",
        "Red"
    )
```

```dax
GreenThreshold = 85
```

```dax
YellowThreshold = 60
```

### RAG Color

```dax
RAG Color =
SWITCH(
    [RAG Status],
    "Green", "#2E7D32",
    "Yellow", "#F9A825",
    "Red", "#C62828",
    "#757575"
)
```

### Repository Counts

```dax
Total Repos =
COUNTROWS(Repos)
```

```dax
Repos At Risk =
CALCULATE(
    COUNTROWS(Repos),
    Repos[risk_score] > 0
)
```

---

## Page 1: Org Security Score

**Purpose:** Single-glance executive summary. Is the org secure? What direction is the trend?

**Background:** Dark (#1A1A2E)
**Accent:** Teal (#00BFA5) for positive, Red (#C62828) for negative

### Layout (1280 x 720)

```
+--------------------------------------------------------------+
|  ENTERPRISE SECURITY SCORE          [Client] / [Enterprise]  |
+--------------------------------------------------------------+
|                                                               |
|   +-------------------+    +-----------------------------+   |
|   |                   |    |                             |   |
|   |    ORG SCORE      |    |    SCORE TREND (12-week)    |   |
|   |      62.4         |    |    ~~~~~~~~~~~~~/           |   |
|   |    /100           |    |                             |   |
|   |   [RAG BADGE]     |    +-----------------------------+   |
|   |                   |                                      |
|   +-------------------+    +-----------------------------+   |
|                            |  SEVERITY BREAKDOWN (donut) |   |
|   +-------------------+    |     Critical: 3             |   |
|   | KROGER-READY      |    |     High: 18               |   |
|   | [BADGE]           |    |     Medium: 67              |   |
|   +-------------------+    |     Low: 59                 |   |
|                            +-----------------------------+   |
|   +-------------------+                                      |
|   | KEY STATS         |    +-----------------------------+   |
|   | Repos: 12         |    | TOP 5 RISKIEST REPOS       |   |
|   | Findings: 147     |    | repo-a   ████████░░  78    |   |
|   | Scanners: 4       |    | repo-b   ██████░░░░  62    |   |
|   | Frameworks: 3     |    | repo-c   █████░░░░░  51    |   |
|   +-------------------+    +-----------------------------+   |
+--------------------------------------------------------------+
```

### Visuals

#### V1.1 — Org Score Card
- **Type:** Card
- **Position:** Top-left quadrant
- **Value:** `[Org Score]`
- **Format:** 1 decimal, font size 72pt bold
- **Subtitle:** "/100"
- **Conditional formatting:** Background color = `[RAG Color]`

#### V1.2 — RAG Status Badge
- **Type:** Card (text)
- **Position:** Below score card
- **Value:** `[RAG Status Label]`

```dax
RAG Status Label =
VAR _status = [RAG Status]
RETURN
    SWITCH(
        _status,
        "Green", "SECURE",
        "Yellow", "AT RISK",
        "Red", "CRITICAL",
        "UNKNOWN"
    )
```

- **Conditional formatting:** Font color = `[RAG Color]`, bold, uppercase

#### V1.3 — Score Trend Sparkline
- **Type:** Line chart
- **Position:** Top-right quadrant
- **Axis:** Trends[date]
- **Values:** `[Trend Org Score]`
- **Format:** No gridlines, no axis labels (sparkline style), line color teal (#00BFA5), area fill with 20% opacity
- **Data labels:** Show only first and last points
- **Reference line:** Horizontal at `[GreenThreshold]` (dashed green) and `[YellowThreshold]` (dashed yellow)

```dax
Trend Org Score =
MAX(Trends[org_score])
```

```dax
Score Trend Direction =
VAR _current = [Org Score]
VAR _previous =
    CALCULATE(
        MAX(Trends[org_score]),
        TOPN(
            1,
            FILTER(
                ALL(Trends),
                Trends[date] < MAX(Trends[date])
            ),
            Trends[date], DESC
        )
    )
RETURN
    SWITCH(
        TRUE(),
        ISBLANK(_previous), "—",
        _current > _previous, "+" & FORMAT(_current - _previous, "0.0"),
        _current < _previous, FORMAT(_current - _previous, "0.0"),
        "±0"
    )
```

#### V1.4 — Kroger-Ready Badge
- **Type:** Card
- **Position:** Left column, below RAG badge
- **Value:** `[Kroger Ready Badge]`

```dax
Kroger Ready Badge =
VAR _isolation_failures =
    CALCULATE(
        COUNTROWS(Findings),
        CONTAINSSTRING(Findings[rule_id], "KRG")
            && Findings[status] = "open"
            && (Findings[severity] = "critical" || Findings[severity] = "high")
    )
VAR _data_exposure =
    CALCULATE(
        COUNTROWS(Findings),
        Findings[owasp] = "A01:2021-Broken Access Control"
            && Findings[status] = "open"
    )
RETURN
    IF(
        _isolation_failures = 0 && _data_exposure = 0,
        "KROGER-READY",
        "NOT KROGER-READY (" & (_isolation_failures + _data_exposure) & " blocking)"
    )
```

```dax
Kroger Ready Color =
IF(
    CONTAINSSTRING([Kroger Ready Badge], "NOT"),
    "#C62828",
    "#2E7D32"
)
```

- **Conditional formatting:** Font color = `[Kroger Ready Color]`

#### V1.5 — Key Stats Cards
- **Type:** Multi-row card
- **Position:** Left column, bottom
- **Fields:**
  - `[Total Repos]` — label "Repositories"
  - `[Total Findings]` — label "Findings"
  - `[Scanner Count]` — label "Scanners"
  - `[Framework Count]` — label "Frameworks"

```dax
Scanner Count =
DISTINCTCOUNT(Findings[scanner])
```

```dax
Framework Count =
DISTINCTCOUNT(Compliance[framework])
```

#### V1.6 — Severity Breakdown Donut
- **Type:** Donut chart
- **Position:** Right column, middle
- **Legend:** severity
- **Values:** Count of findings by severity
- **Detail measure:**

```dax
Severity Distribution =
COUNTROWS(Findings)
```

- **Color mapping:**
  - critical → #C62828 (red)
  - high → #E65100 (dark orange)
  - medium → #F9A825 (amber)
  - low → #66BB6A (green)
- **Inner label:** `[Total Findings]` with "Total" subtitle
- **Sort:** By severity rank (critical first)

#### V1.7 — Top 5 Riskiest Repos
- **Type:** Bar chart (horizontal)
- **Position:** Right column, bottom
- **Axis:** Repos[name]
- **Values:** `[Repo Risk Score]`
- **Top N filter:** Top 5 by Repos[risk_score]
- **Conditional formatting:** Data bars colored by RAG thresholds

```dax
Repo Risk Score =
MAX(Repos[risk_score])
```

### Page-Level Filters
- None (shows all data)

### Drill-Through
- Click any repo bar → drills to Page 13 (Application Inventory Heatmap, task 19)

---

## Page 2: Threat Landscape Summary

**Purpose:** What types of vulnerabilities exist? Where are they concentrated? What's the trend?

**Background:** Dark (#1A1A2E)

### Layout (1280 x 720)

```
+--------------------------------------------------------------+
|  THREAT LANDSCAPE                   [Total Findings] total   |
+--------------------------------------------------------------+
|                                                               |
|  +---------------------------+  +---------------------------+ |
|  | OWASP TOP 10 (bar chart)  |  | CWE TREEMAP              | |
|  | A01 ████████████  42      |  | +------+--------+------+ | |
|  | A02 ████████  28          |  | |CWE-89|CWE-79  |CWE-  | | |
|  | A03 ██████  21            |  | |      |        | 259  | | |
|  | A07 ████  14              |  | +------+--------+------+ | |
|  | A09 ███  11               |  | |CWE-532|CWE-327|CWE-78| | |
|  | ...                       |  | +------+--------+------+ | |
|  +---------------------------+  +---------------------------+ |
|                                                               |
|  +---------------------------+  +---------------------------+ |
|  | NEW vs RESOLVED (area)    |  | BY SCANNER SOURCE (donut) | |
|  | ~~~~~~~~~~~               |  |   Semgrep: 68%            | |
|  | ===== resolved            |  |   Bandit: 18%             | |
|  |                           |  |   TruffleHog: 9%          | |
|  |                           |  |   pip-audit: 5%           | |
|  +---------------------------+  +---------------------------+ |
|                                                               |
|  [Slicer: Severity] [Slicer: Repo] [Slicer: Scanner]        |
+--------------------------------------------------------------+
```

### Visuals

#### V2.1 — OWASP Top 10 Bar Chart
- **Type:** Clustered bar chart (horizontal)
- **Position:** Top-left quadrant
- **Axis:** `[OWASP Category]`
- **Values:** `[OWASP Finding Count]`
- **Sort:** Descending by count
- **Conditional formatting:** Bar color by severity majority per category

```dax
OWASP Category =
Findings[owasp]
```

```dax
OWASP Finding Count =
COUNTROWS(Findings)
```

```dax
OWASP Dominant Severity =
VAR _crit = CALCULATE(COUNTROWS(Findings), Findings[severity] = "critical")
VAR _high = CALCULATE(COUNTROWS(Findings), Findings[severity] = "high")
VAR _med = CALCULATE(COUNTROWS(Findings), Findings[severity] = "medium")
RETURN
    SWITCH(
        TRUE(),
        _crit > 0, "critical",
        _high > _med, "high",
        "medium"
    )
```

- **Data labels:** Show count at end of each bar
- **Reference line:** None

#### V2.2 — CWE Treemap
- **Type:** Treemap
- **Position:** Top-right quadrant
- **Group:** Findings[cwe]
- **Values:** `[CWE Finding Count]`
- **Tooltips:** CWE ID, count, most common OWASP mapping, highest severity

```dax
CWE Finding Count =
COUNTROWS(Findings)
```

```dax
CWE Highest Severity =
VAR _crit = CALCULATE(COUNTROWS(Findings), Findings[severity] = "critical")
VAR _high = CALCULATE(COUNTROWS(Findings), Findings[severity] = "high")
RETURN
    SWITCH(
        TRUE(),
        _crit > 0, "critical",
        _high > 0, "high",
        "medium"
    )
```

- **Color:** Gradient by severity (red = critical, orange = high, amber = medium)
- **Labels:** CWE ID + count

#### V2.3 — New vs Resolved Area Chart
- **Type:** Area chart (stacked)
- **Position:** Bottom-left quadrant
- **Axis:** Trends[date]
- **Values:**
  - `[Trend Total Findings]` — line (dark)
  - `[Trend Resolved Count]` — area fill (green, 40% opacity)

```dax
Trend Total Findings =
MAX(Trends[total_findings])
```

```dax
Trend Resolved Count =
MAX(Trends[resolved_count])
```

```dax
Net New Findings =
VAR _current = MAX(Trends[total_findings])
VAR _resolved = MAX(Trends[resolved_count])
RETURN
    _current - _resolved
```

- **Data labels:** Show latest point only
- **Reference line:** None

#### V2.4 — By Scanner Source Donut
- **Type:** Donut chart
- **Position:** Bottom-right quadrant
- **Legend:** Findings[scanner]
- **Values:** `[Scanner Finding Count]`

```dax
Scanner Finding Count =
COUNTROWS(Findings)
```

- **Color mapping:**
  - semgrep → #1565C0 (blue)
  - bandit → #6A1B9A (purple)
  - trufflehog → #E65100 (orange)
  - pip-audit → #00838F (teal)
  - npm-audit → #2E7D32 (green)
  - cyclonedx → #4E342E (brown)
- **Inner label:** `[Total Findings]`

#### V2.5 — Severity Slicer
- **Type:** Slicer (horizontal buttons)
- **Position:** Bottom bar
- **Field:** Findings[severity]
- **Selection:** Multi-select
- **Style:** Pill buttons, colored by severity mapping

#### V2.6 — Repo Slicer
- **Type:** Slicer (dropdown)
- **Position:** Bottom bar
- **Field:** Repos[name]
- **Selection:** Multi-select

#### V2.7 — Scanner Slicer
- **Type:** Slicer (horizontal buttons)
- **Position:** Bottom bar
- **Field:** Findings[scanner]
- **Selection:** Multi-select

### Page-Level Filters
- Findings[status] = "open" (default, can be cleared)

### Drill-Through
- Click any OWASP bar → drills to the matching threat drilldown page (pages 4-9)
- Click any CWE tile → drills to the matching threat drilldown page

---

## Page 3: Remediation Velocity

**Purpose:** How fast are we fixing things? What's aging? When will we hit zero criticals?

**Background:** Dark (#1A1A2E)

### Layout (1280 x 720)

```
+--------------------------------------------------------------+
|  REMEDIATION VELOCITY               [Resolved] resolved      |
+--------------------------------------------------------------+
|                                                               |
|  +---------+---------+---------+---------+                   |
|  |  MTTR   |  MTTR   |  MTTR   |  MTTR   |                  |
|  | Critical| High    | Medium  | Low     |                   |
|  |  14d    |  7d     |  21d    |  45d    |                   |
|  +---------+---------+---------+---------+                   |
|                                                               |
|  +---------------------------+  +---------------------------+ |
|  | REMEDIATION RATE (line)   |  | AGING HISTOGRAM           | |
|  |        ___/               |  | 0-7d   ████████  32       | |
|  |    ___/                   |  | 8-30d  ██████████████  58  | |
|  |   /                       |  | 31-90d ████████████  47   | |
|  |  target: 80%              |  | 90d+   ██████  10         | |
|  +---------------------------+  +---------------------------+ |
|                                                               |
|  +---------------------------+  +---------------------------+ |
|  | TOP 10 OLDEST (table)     |  | PROJECTED ZERO-CRITICAL   | |
|  | repo | file | age | sev   |  |                           | |
|  | ...  | ...  | 120d| crit  |  |   Est: June 15, 2026     | |
|  | ...  | ...  | 98d | high  |  |   At current velocity     | |
|  +---------------------------+  +---------------------------+ |
+--------------------------------------------------------------+
```

### Visuals

#### V3.1 — MTTR by Severity Cards
- **Type:** Multi-row card (4 cards in a row)
- **Position:** Top row, full width
- **Values:** `[MTTR Critical]`, `[MTTR High]`, `[MTTR Medium]`, `[MTTR Low]`

```dax
MTTR Critical =
VAR _resolved =
    FILTER(
        Findings,
        Findings[status] = "resolved" && Findings[severity] = "critical"
    )
VAR _avg = AVERAGEX(_resolved, Findings[age_days])
RETURN
    IF(ISBLANK(_avg), "—", FORMAT(_avg, "0") & "d")
```

```dax
MTTR High =
VAR _resolved =
    FILTER(
        Findings,
        Findings[status] = "resolved" && Findings[severity] = "high"
    )
VAR _avg = AVERAGEX(_resolved, Findings[age_days])
RETURN
    IF(ISBLANK(_avg), "—", FORMAT(_avg, "0") & "d")
```

```dax
MTTR Medium =
VAR _resolved =
    FILTER(
        Findings,
        Findings[status] = "resolved" && Findings[severity] = "medium"
    )
VAR _avg = AVERAGEX(_resolved, Findings[age_days])
RETURN
    IF(ISBLANK(_avg), "—", FORMAT(_avg, "0") & "d")
```

```dax
MTTR Low =
VAR _resolved =
    FILTER(
        Findings,
        Findings[status] = "resolved" && Findings[severity] = "low"
    )
VAR _avg = AVERAGEX(_resolved, Findings[age_days])
RETURN
    IF(ISBLANK(_avg), "—", FORMAT(_avg, "0") & "d")
```

```dax
MTTR Overall =
VAR _resolved = FILTER(Findings, Findings[status] = "resolved")
VAR _avg = AVERAGEX(_resolved, Findings[age_days])
RETURN
    IF(ISBLANK(_avg), 0, _avg)
```

- **Conditional formatting:** Card border color by severity color mapping
- **Subtitle:** "mean time to resolve"

#### V3.2 — Remediation Rate Trend Line
- **Type:** Line chart
- **Position:** Middle-left
- **Axis:** Trends[date]
- **Values:** `[Remediation Rate Trend]`

```dax
Remediation Rate =
VAR _total = [Total Findings] + [Resolved Findings]
VAR _resolved = [Resolved Findings]
RETURN
    IF(_total > 0, DIVIDE(_resolved, _total) * 100, 0)
```

```dax
Remediation Rate Trend =
VAR _total = MAX(Trends[total_findings]) + MAX(Trends[resolved_count])
VAR _resolved = MAX(Trends[resolved_count])
RETURN
    IF(_total > 0, DIVIDE(_resolved, _total) * 100, 0)
```

- **Format:** Percentage (0 decimal), line color teal
- **Reference line:** Horizontal at 80% (dashed, labeled "Target")
- **Y-axis:** 0-100%

#### V3.3 — Aging Histogram
- **Type:** Clustered bar chart (horizontal)
- **Position:** Middle-right
- **Axis:** `[Age Bucket]`
- **Values:** `[Age Bucket Count]`

```dax
Age Bucket =
SWITCH(
    TRUE(),
    Findings[age_days] <= 7, "0-7 days",
    Findings[age_days] <= 30, "8-30 days",
    Findings[age_days] <= 90, "31-90 days",
    "90+ days"
)
```

To use this as a column for charting, create a calculated column on Findings:

```dax
// Calculated column on Findings table
Age Bucket =
SWITCH(
    TRUE(),
    Findings[age_days] <= 7, "0-7 days",
    Findings[age_days] <= 30, "8-30 days",
    Findings[age_days] <= 90, "31-90 days",
    "90+ days"
)
```

```dax
// Sort order helper (calculated column)
Age Bucket Sort =
SWITCH(
    TRUE(),
    Findings[age_days] <= 7, 1,
    Findings[age_days] <= 30, 2,
    Findings[age_days] <= 90, 3,
    4
)
```

```dax
Age Bucket Count =
COUNTROWS(Findings)
```

- **Filter:** Findings[status] = "open"
- **Sort:** By Age Bucket Sort ascending
- **Color:** Gradient — lighter for newer, darker/redder for older
  - 0-7 days → #66BB6A (green)
  - 8-30 days → #F9A825 (amber)
  - 31-90 days → #E65100 (orange)
  - 90+ days → #C62828 (red)

#### V3.4 — Top 10 Oldest Findings Table
- **Type:** Table
- **Position:** Bottom-left
- **Columns:**
  - Findings[repo]
  - Findings[file] (truncated to last path segment)
  - Findings[rule_id]
  - Findings[severity]
  - Findings[age_days]
  - Findings[status]
- **Sort:** Descending by age_days
- **Top N filter:** Top 10 by Findings[age_days]
- **Filter:** Findings[status] = "open"
- **Conditional formatting:**
  - Severity column: background color by severity color mapping
  - Age column: data bars (red gradient)

```dax
File Short Name =
VAR _path = Findings[file]
VAR _lastSlash = FIND("/", _path, 1, LEN(_path))
RETURN
    IF(
        _lastSlash < LEN(_path),
        RIGHT(_path, LEN(_path) - _lastSlash),
        _path
    )
```

#### V3.5 — Projected Zero-Critical Date
- **Type:** Card
- **Position:** Bottom-right
- **Value:** `[Projected Zero Critical]`

```dax
Critical Resolution Rate Per Day =
VAR _resolved_criticals =
    CALCULATE(
        COUNTROWS(Findings),
        Findings[severity] = "critical",
        Findings[status] = "resolved"
    )
VAR _mttr =
    AVERAGEX(
        FILTER(
            Findings,
            Findings[severity] = "critical" && Findings[status] = "resolved"
        ),
        Findings[age_days]
    )
RETURN
    IF(
        ISBLANK(_mttr) || _mttr = 0,
        BLANK(),
        DIVIDE(1, _mttr)
    )
```

```dax
Projected Zero Critical =
VAR _open_criticals = [Critical Findings]
VAR _rate = [Critical Resolution Rate Per Day]
VAR _days_needed =
    IF(
        ISBLANK(_rate) || _rate <= 0,
        BLANK(),
        ROUNDUP(DIVIDE(_open_criticals, _rate), 0)
    )
RETURN
    IF(
        _open_criticals = 0,
        "CLEAR — no open criticals",
        IF(
            ISBLANK(_days_needed),
            "Unable to project (no resolution history)",
            "Est. " & FORMAT(TODAY() + _days_needed, "MMMM DD, YYYY") & " (" & _days_needed & " days at current velocity)"
        )
    )
```

```dax
Projected Zero Critical Color =
IF(
    [Critical Findings] = 0,
    "#2E7D32",
    "#C62828"
)
```

- **Conditional formatting:** Font color = `[Projected Zero Critical Color]`
- **Subtitle:** "at current resolution velocity"

#### V3.6 — Remediation Summary KPIs
- **Type:** Card row (inline with page title)
- **Position:** Header area, right-aligned
- **Values:**

```dax
Resolved This Period =
CALCULATE(
    COUNTROWS(Findings),
    Findings[status] = "resolved"
)
```

```dax
Remediation Percentage =
VAR _total = COUNTROWS(Findings)
VAR _resolved =
    CALCULATE(COUNTROWS(Findings), Findings[status] = "resolved")
RETURN
    IF(_total > 0, DIVIDE(_resolved, _total), 0)
```

- **Format:** `[Resolved This Period]` as integer, `[Remediation Percentage]` as percentage

### Page-Level Filters
- None (shows all findings including resolved for MTTR calculations)

### Drill-Through
- Click any row in Top 10 Oldest → drills to the matching threat drilldown page (pages 4-9) filtered by that finding's OWASP category

---

## Color Palette (all pages)

| Token | Hex | Usage |
|---|---|---|
| bg-primary | #1A1A2E | Page background |
| bg-card | #16213E | Visual card background |
| text-primary | #E8E8E8 | Primary text |
| text-secondary | #A0A0A0 | Subtitles, labels |
| accent-teal | #00BFA5 | Positive trend, score |
| severity-critical | #C62828 | Critical findings |
| severity-high | #E65100 | High findings |
| severity-medium | #F9A825 | Medium findings |
| severity-low | #66BB6A | Low findings |
| rag-green | #2E7D32 | Score >= 85 |
| rag-yellow | #F9A825 | Score 60-84 |
| rag-red | #C62828 | Score < 60 |
| scanner-semgrep | #1565C0 | Semgrep source |
| scanner-bandit | #6A1B9A | Bandit source |
| scanner-trufflehog | #E65100 | TruffleHog source |
| scanner-pip-audit | #00838F | pip-audit source |
| scanner-npm-audit | #2E7D32 | npm-audit source |

## Font Hierarchy

| Level | Font | Size | Weight |
|---|---|---|---|
| Page title | Segoe UI | 24pt | Semibold |
| Section header | Segoe UI | 16pt | Semibold |
| Card value (large) | Segoe UI | 72pt | Bold |
| Card value (medium) | Segoe UI | 36pt | Bold |
| Card subtitle | Segoe UI | 12pt | Regular |
| Table header | Segoe UI | 11pt | Semibold |
| Table body | Segoe UI | 10pt | Regular |
| Axis labels | Segoe UI | 9pt | Regular |

---

## M-Query: Data Source Configuration

Each CSV table uses this pattern (parameterized by DatasetPath):

```m
let
    Source = Csv.Document(
        File.Contents(DatasetPath & "\findings.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    TypedColumns = Table.TransformColumnTypes(PromotedHeaders, {
        {"id", type text},
        {"repo", type text},
        {"file", type text},
        {"line", Int64.Type},
        {"rule_id", type text},
        {"severity", type text},
        {"cvss", type number},
        {"business_impact", type text},
        {"risk_score", type number},
        {"owasp", type text},
        {"cwe", type text},
        {"status", type text},
        {"age_days", Int64.Type},
        {"scanner", type text},
        {"message", type text},
        {"compliance_controls", type text}
    })
in
    TypedColumns
```

For metadata.json:

```m
let
    Source = Json.Document(File.Contents(DatasetPath & "\metadata.json")),
    AsTable = Record.ToTable(Source),
    Pivoted = Table.Pivot(AsTable, List.Distinct(AsTable[Name]), "Name", "Value")
in
    Pivoted
```

---

# Pages 4-9: Threat Drilldown Pages

All six threat drilldown pages share a common layout template. Each page filters to a specific OWASP Top 10 category (or group of related rule IDs) and provides detailed finding-level views. Every page is reachable via drill-through from Page 2 (Threat Landscape) and Page 13 (Application Inventory Heatmap).

## Shared Drilldown Layout Template

All pages 4-9 follow this structure:

```
+--------------------------------------------------------------+
|  [PAGE TITLE]          [Count] findings | [Repos] repos      |
+--------------------------------------------------------------+
|                                                               |
|  +---------+---------+---------+---------+                   |
|  | CRITICAL| HIGH    | MEDIUM  | LOW     |  severity cards   |
|  |   2     |   8     |   14    |   3     |                   |
|  +---------+---------+---------+---------+                   |
|                                                               |
|  +---------------------------+  +---------------------------+ |
|  | BY REPO (bar chart)       |  | BY CWE (donut)           | |
|  | repo-a  ████████  12      |  |  CWE-89: 40%             | |
|  | repo-b  ██████  9         |  |  CWE-78: 30%             | |
|  | repo-c  ████  6           |  |  CWE-79: 20%             | |
|  +---------------------------+  +---------------------------+ |
|                                                               |
|  +----------------------------------------------------------+ |
|  | FINDING DETAIL TABLE                                      | |
|  | repo | file | line | rule_id | sev | age | status | msg  | |
|  | ...  | ...  | ...  | ...     | ... | ... | ...    | ...  | |
|  +----------------------------------------------------------+ |
|                                                               |
|  [Slicer: Repo] [Slicer: Severity] [Slicer: Status]         |
+--------------------------------------------------------------+
```

### Shared Drilldown Visuals

#### VD.1 — Severity KPI Cards (row of 4)
- **Type:** Card row
- **Values:** Filtered `[Critical Findings]`, `[High Findings]`, `[Medium Findings]`, `[Low Findings]`
- **Conditional formatting:** Card border color = severity color

#### VD.2 — By Repo Bar Chart
- **Type:** Clustered bar chart (horizontal)
- **Axis:** Findings[repo]
- **Values:** Count of filtered findings
- **Sort:** Descending by count
- **Conditional formatting:** Bar color gradient by count (darker = more findings)

#### VD.3 — By CWE Donut
- **Type:** Donut chart
- **Legend:** Findings[cwe]
- **Values:** Count of filtered findings
- **Inner label:** Total count for this page's category

#### VD.4 — Finding Detail Table
- **Type:** Table (paginated, 15 rows per page)
- **Columns:**

| Column | Source | Width | Format |
|---|---|---|---|
| Repo | Findings[repo] | 120px | Text |
| File | `[File Short Name]` | 160px | Text, truncated |
| Line | Findings[line] | 50px | Integer |
| Rule | Findings[rule_id] | 100px | Text |
| Severity | Findings[severity] | 80px | Conditional bg color |
| CVSS | Findings[cvss] | 60px | 1 decimal |
| Age | Findings[age_days] | 60px | Integer + "d" |
| Status | Findings[status] | 80px | Conditional icon |
| Message | Findings[message] | 280px | Text, wrapped |

- **Conditional formatting:**
  - Severity column: background = severity color mapping
  - Status column: icon (open = red circle, resolved = green check, suppressed = grey dash)
  - Age column: data bars (red gradient)
- **Sort:** Default by severity rank desc, then age_days desc
- **Row click:** Opens tooltip with full file path, compliance controls, and mitigation title

#### VD.5 — Slicers (bottom bar)
- Repo slicer (dropdown, multi-select)
- Severity slicer (buttons, multi-select)
- Status slicer (buttons: Open / Resolved / Suppressed)

### Shared Drilldown DAX

```dax
Page Finding Count =
COUNTROWS(Findings)
```

```dax
Page Repo Count =
DISTINCTCOUNT(Findings[repo])
```

```dax
Status Icon =
SWITCH(
    Findings[status],
    "open", UNICHAR(128308),
    "resolved", UNICHAR(9989),
    "suppressed", UNICHAR(10134),
    ""
)
```

### Drill-Through Configuration

Each page accepts these drill-through fields:
- `Findings[owasp]` — primary filter from Page 2 OWASP bar chart
- `Findings[cwe]` — secondary filter from Page 2 CWE treemap
- `Findings[repo]` — filter from Page 13 heatmap tile click

---

## Page 4: Injection Attacks

**Purpose:** All injection vulnerabilities — SQL injection, command injection, XSS, template injection, LDAP injection.

**Page-level filter:** `Findings[owasp] = "A03:2021 - Injection"`
**Rule ID prefix:** `KRG-inj-*`

### Page-Specific Visuals

#### V4.1 — Injection Type Breakdown
- **Type:** Stacked bar chart (horizontal)
- **Position:** Replaces VD.3 position (top-right)
- **Axis:** `[Injection Type]`
- **Values:** Count of findings
- **Legend:** Findings[severity]

```dax
Injection Type =
SWITCH(
    TRUE(),
    CONTAINSSTRING(Findings[rule_id], "inj-001") || CONTAINSSTRING(Findings[cwe], "CWE-89"), "SQL Injection",
    CONTAINSSTRING(Findings[rule_id], "inj-002") || CONTAINSSTRING(Findings[cwe], "CWE-78"), "Command Injection",
    CONTAINSSTRING(Findings[rule_id], "inj-003") || CONTAINSSTRING(Findings[cwe], "CWE-79"), "Cross-Site Scripting (XSS)",
    CONTAINSSTRING(Findings[rule_id], "inj-004") || CONTAINSSTRING(Findings[cwe], "CWE-1336"), "Template Injection (SSTI)",
    CONTAINSSTRING(Findings[rule_id], "inj-005") || CONTAINSSTRING(Findings[cwe], "CWE-90"), "LDAP Injection",
    "Other Injection"
)
```

- **Color:** Stacked by severity color

#### V4.2 — Parameterized Query Coverage
- **Type:** KPI card
- **Position:** Below severity cards, right-aligned
- **Value:** `[Parameterized Query Rate]`

```dax
Parameterized Query Rate =
VAR _sqli =
    CALCULATE(
        COUNTROWS(Findings),
        CONTAINSSTRING(Findings[cwe], "CWE-89"),
        Findings[status] = "open"
    )
VAR _total_db_findings =
    CALCULATE(
        COUNTROWS(Findings),
        CONTAINSSTRING(Findings[cwe], "CWE-89")
    )
RETURN
    IF(
        _total_db_findings = 0,
        "100% (no SQL findings)",
        FORMAT(DIVIDE(_total_db_findings - _sqli, _total_db_findings), "0%") & " resolved"
    )
```

#### V4.3 — Top Affected Files
- **Type:** Table (compact, 5 rows)
- **Position:** Below injection type breakdown
- **Columns:** File, Injection Count, Highest Severity
- **Sort:** Descending by count

```dax
Injection File Count =
CALCULATE(
    COUNTROWS(Findings),
    Findings[owasp] = "A03:2021 - Injection"
)
```

### Drill-Through Target
- From Page 2: OWASP bar "A03:2021 - Injection" or CWE tiles CWE-89, CWE-78, CWE-79
- Row click in detail table → tooltip shows mitigation title from Mitigations table

---

## Page 5: Auth & Access Control

**Purpose:** Broken access control, IDOR, missing auth middleware, tenant isolation failures, privilege escalation, unscoped bulk exports.

**Page-level filter:** `Findings[owasp] = "A01:2021 - Broken Access Control"`
**Rule ID prefixes:** `KRG-auth-*`, `KRG-ac-*`

### Page-Specific Visuals

#### V5.1 — Access Control Sub-Category Breakdown
- **Type:** Stacked bar chart (horizontal)
- **Position:** Top-right
- **Axis:** `[Access Control Type]`
- **Values:** Count of findings
- **Legend:** Findings[severity]

```dax
Access Control Type =
SWITCH(
    TRUE(),
    CONTAINSSTRING(Findings[rule_id], "auth-001") || CONTAINSSTRING(Findings[cwe], "CWE-639"), "Missing Tenant Scope",
    CONTAINSSTRING(Findings[rule_id], "auth-002") || CONTAINSSTRING(Findings[cwe], "CWE-284"), "IDOR",
    CONTAINSSTRING(Findings[rule_id], "auth-003") || CONTAINSSTRING(Findings[cwe], "CWE-306"), "Missing Auth Middleware",
    CONTAINSSTRING(Findings[rule_id], "auth-004") || CONTAINSSTRING(Findings[cwe], "CWE-200"), "Unscoped Bulk Export",
    CONTAINSSTRING(Findings[rule_id], "auth-005") || CONTAINSSTRING(Findings[cwe], "CWE-269"), "Privilege Escalation",
    CONTAINSSTRING(Findings[rule_id], "ac-"), "Access Control (General)",
    "Other Access Control"
)
```

#### V5.2 — Vendor Isolation Status Card
- **Type:** Card (large)
- **Position:** Below severity cards, right-aligned
- **Value:** `[Vendor Isolation Status]`

```dax
Vendor Isolation Status =
VAR _tenant_failures =
    CALCULATE(
        COUNTROWS(Findings),
        OR(
            CONTAINSSTRING(Findings[rule_id], "auth-001"),
            CONTAINSSTRING(Findings[cwe], "CWE-639")
        ),
        Findings[status] = "open"
    )
RETURN
    IF(
        _tenant_failures = 0,
        "ISOLATED — all tenant scoping verified",
        _tenant_failures & " open tenant isolation failure" & IF(_tenant_failures > 1, "s", "")
    )
```

```dax
Vendor Isolation Color =
VAR _tenant_failures =
    CALCULATE(
        COUNTROWS(Findings),
        OR(
            CONTAINSSTRING(Findings[rule_id], "auth-001"),
            CONTAINSSTRING(Findings[cwe], "CWE-639")
        ),
        Findings[status] = "open"
    )
RETURN
    IF(_tenant_failures = 0, "#2E7D32", "#C62828")
```

- **Conditional formatting:** Font color = `[Vendor Isolation Color]`

#### V5.3 — IDOR Heatmap
- **Type:** Matrix
- **Position:** Below the bar chart
- **Rows:** Findings[repo]
- **Columns:** `[Access Control Type]`
- **Values:** Count of findings
- **Conditional formatting:** Background color gradient (white → red by count)
- **Filter:** Only rows where count > 0

### Drill-Through Target
- From Page 2: OWASP bar "A01:2021 - Broken Access Control" or CWE tiles CWE-639, CWE-284, CWE-306
- Links to Page 12 (Vendor Data Isolation Deep Dive, task 19) for tenant-specific analysis

---

## Page 6: Secrets & Credential Exposure

**Purpose:** Hardcoded credentials, API keys, connection strings, private keys, env fallback defaults. Tracks exposure age and rotation urgency.

**Page-level filter:** `Findings[owasp] = "A07:2021 - Identification and Authentication Failures"`
**Rule ID prefix:** `KRG-sec-*`

### Page-Specific Visuals

#### V6.1 — Secret Type Breakdown
- **Type:** Stacked bar chart (horizontal)
- **Position:** Top-right
- **Axis:** `[Secret Type]`
- **Values:** Count of findings
- **Legend:** Findings[severity]

```dax
Secret Type =
SWITCH(
    TRUE(),
    CONTAINSSTRING(Findings[rule_id], "sec-001") || CONTAINSSTRING(Findings[cwe], "CWE-798"), "Hardcoded Password",
    CONTAINSSTRING(Findings[rule_id], "sec-002") || CONTAINSSTRING(Findings[cwe], "CWE-321"), "API Key in Code",
    CONTAINSSTRING(Findings[rule_id], "sec-003") || CONTAINSSTRING(Findings[cwe], "CWE-256"), "Connection String",
    CONTAINSSTRING(Findings[rule_id], "sec-004") || CONTAINSSTRING(Findings[cwe], "CWE-312"), "Private Key",
    CONTAINSSTRING(Findings[rule_id], "sec-005"), "Env Fallback Default",
    "Other Secret"
)
```

#### V6.2 — Exposure Age Distribution
- **Type:** Histogram (column chart)
- **Position:** Below secret type breakdown
- **Axis:** `[Secret Age Bucket]`
- **Values:** Count of findings

```dax
Secret Age Bucket =
SWITCH(
    TRUE(),
    Findings[age_days] <= 1, "< 24h (URGENT)",
    Findings[age_days] <= 7, "1-7 days",
    Findings[age_days] <= 30, "8-30 days",
    Findings[age_days] <= 90, "31-90 days",
    "90+ days (STALE)"
)
```

```dax
Secret Age Bucket Sort =
SWITCH(
    TRUE(),
    Findings[age_days] <= 1, 1,
    Findings[age_days] <= 7, 2,
    Findings[age_days] <= 30, 3,
    Findings[age_days] <= 90, 4,
    5
)
```

- **Color:**
  - < 24h → #C62828 (red, urgent)
  - 1-7 days → #E65100 (orange)
  - 8-30 days → #F9A825 (amber)
  - 31-90 days → #FB8C00 (dark amber)
  - 90+ days → #B71C1C (dark red, critical staleness)

#### V6.3 — Rotation Urgency KPI
- **Type:** Card
- **Position:** Below severity cards, right-aligned
- **Value:** `[Secrets Needing Rotation]`

```dax
Secrets Needing Rotation =
VAR _exposed =
    CALCULATE(
        COUNTROWS(Findings),
        Findings[owasp] = "A07:2021 - Identification and Authentication Failures",
        Findings[status] = "open"
    )
RETURN
    IF(
        _exposed = 0,
        "CLEAR — no exposed secrets",
        _exposed & " secret" & IF(_exposed > 1, "s", "") & " require immediate rotation"
    )
```

```dax
Secrets Urgency Color =
VAR _exposed =
    CALCULATE(
        COUNTROWS(Findings),
        Findings[owasp] = "A07:2021 - Identification and Authentication Failures",
        Findings[status] = "open"
    )
RETURN
    IF(_exposed = 0, "#2E7D32", "#C62828")
```

#### V6.4 — Git History Exposure Flag
- **Type:** Card (warning)
- **Position:** Top banner area
- **Value:** `[Git History Warning]`

```dax
Git History Warning =
VAR _trufflehog =
    CALCULATE(
        COUNTROWS(Findings),
        Findings[scanner] = "trufflehog",
        Findings[status] = "open"
    )
RETURN
    IF(
        _trufflehog > 0,
        "WARNING: " & _trufflehog & " secret(s) found in git history — removing from code is NOT sufficient, history rewrite or rotation required",
        ""
    )
```

- **Conditional formatting:** Background = #C62828 with white text when non-empty, hidden when empty

### Drill-Through Target
- From Page 2: OWASP bar "A07:2021" or CWE tiles CWE-798, CWE-321, CWE-256, CWE-312

---

## Page 7: Data Protection & Encryption

**Purpose:** Encryption at rest, encryption in transit, sensitive data in logs, insecure cookies, client-side storage exposure.

**Page-level filter:** `Findings[owasp] = "A02:2021 - Cryptographic Failures"`
**Rule ID prefixes:** `KRG-enc-*`, `KRG-tls-*`, `KRG-crypto-*`

### Page-Specific Visuals

#### V7.1 — Encryption Category Breakdown
- **Type:** Stacked bar chart (horizontal)
- **Position:** Top-right
- **Axis:** `[Encryption Category]`
- **Values:** Count of findings
- **Legend:** Findings[severity]

```dax
Encryption Category =
SWITCH(
    TRUE(),
    CONTAINSSTRING(Findings[rule_id], "enc-001") || CONTAINSSTRING(Findings[cwe], "CWE-319"), "HTTP Not HTTPS",
    CONTAINSSTRING(Findings[rule_id], "enc-002") || CONTAINSSTRING(Findings[cwe], "CWE-295"), "Missing TLS Verification",
    CONTAINSSTRING(Findings[rule_id], "enc-003") || CONTAINSSTRING(Findings[cwe], "CWE-311"), "Unencrypted DB Connection",
    CONTAINSSTRING(Findings[rule_id], "enc-004") || CONTAINSSTRING(Findings[cwe], "CWE-614"), "Insecure Cookies",
    CONTAINSSTRING(Findings[rule_id], "enc-005"), "Unencrypted Data at Rest",
    CONTAINSSTRING(Findings[rule_id], "tls-"), "Transport Layer Issue",
    CONTAINSSTRING(Findings[rule_id], "crypto-"), "Weak Cryptography",
    "Other Encryption"
)
```

#### V7.2 — Sensitive Data Logging Audit
- **Type:** Table (compact, 10 rows)
- **Position:** Below bar chart
- **Filter:** Findings where rule_id contains "log" or OWASP = "A09"
- **Columns:** Repo, File, Line, Data Term Logged, Severity

```dax
Data Logging Findings =
CALCULATE(
    COUNTROWS(Findings),
    OR(
        CONTAINSSTRING(Findings[rule_id], "log-"),
        Findings[owasp] = "A09:2021 - Security Logging and Monitoring Failures"
    )
)
```

**Note:** This subsection cross-references with the data-protection Semgrep rules that detect client-specific data classification terms (e.g., `pricing`, `vendor_terms`, `planogram`) being logged.

#### V7.3 — Transit vs Rest Donut
- **Type:** Donut chart
- **Position:** Below severity cards, right
- **Legend:** `[Protection Layer]`
- **Values:** Count of findings

```dax
Protection Layer =
SWITCH(
    TRUE(),
    CONTAINSSTRING(Findings[cwe], "CWE-319")
        || CONTAINSSTRING(Findings[cwe], "CWE-295")
        || CONTAINSSTRING(Findings[rule_id], "tls-"),
    "In Transit",
    CONTAINSSTRING(Findings[cwe], "CWE-311")
        || CONTAINSSTRING(Findings[cwe], "CWE-614")
        || CONTAINSSTRING(Findings[rule_id], "enc-005"),
    "At Rest",
    CONTAINSSTRING(Findings[rule_id], "crypto-"),
    "Weak Algorithm",
    "Other"
)
```

- **Color:**
  - In Transit → #1565C0 (blue)
  - At Rest → #6A1B9A (purple)
  - Weak Algorithm → #E65100 (orange)
  - Other → #757575 (grey)

#### V7.4 — Zscaler TLS Impact Banner
- **Type:** Card (info banner)
- **Position:** Top banner, below page title
- **Value:** `[Zscaler TLS Impact]`

```dax
Zscaler TLS Impact =
VAR _tls_verify_issues =
    CALCULATE(
        COUNTROWS(Findings),
        CONTAINSSTRING(Findings[cwe], "CWE-295"),
        Findings[status] = "open"
    )
RETURN
    IF(
        _tls_verify_issues > 0,
        "NOTE: " & _tls_verify_issues & " TLS verification finding(s) may be caused by Zscaler SSL inspection. Cross-reference with Page 10 (Zscaler Compatibility) before remediating.",
        ""
    )
```

- **Conditional formatting:** Background = #16213E (subtle info blue) when visible, hidden when empty

### Drill-Through Target
- From Page 2: OWASP bar "A02:2021 - Cryptographic Failures" or CWE tiles CWE-319, CWE-295, CWE-311

---

## Page 8: Dependency Vulnerabilities

**Purpose:** Known CVEs in dependencies, SBOM analysis, CISA KEV cross-reference, outdated packages.

**Page-level filter:** `Findings[scanner] IN ("pip-audit", "npm-audit", "cyclonedx")` OR `Findings[owasp] = "A06:2021 - Vulnerable and Outdated Components"`
**Rule ID prefix:** `KRG-dep-*`

### Page-Specific Visuals

#### V8.1 — CVE Severity Distribution
- **Type:** Stacked column chart
- **Position:** Top-left
- **Axis:** `[CVE Severity Band]`
- **Values:** Count of findings
- **Legend:** Findings[scanner]

```dax
CVE Severity Band =
SWITCH(
    TRUE(),
    Findings[cvss] >= 9.0, "Critical (9.0+)",
    Findings[cvss] >= 7.0, "High (7.0-8.9)",
    Findings[cvss] >= 4.0, "Medium (4.0-6.9)",
    "Low (0-3.9)"
)
```

```dax
CVE Severity Band Sort =
SWITCH(
    TRUE(),
    Findings[cvss] >= 9.0, 1,
    Findings[cvss] >= 7.0, 2,
    Findings[cvss] >= 4.0, 3,
    4
)
```

- **Color stacks:** By scanner color mapping (pip-audit teal, npm-audit green, cyclonedx brown)

#### V8.2 — CISA KEV Cross-Reference Card
- **Type:** Card
- **Position:** Below severity cards, right-aligned
- **Value:** `[CISA KEV Count]`

```dax
CISA KEV Count =
VAR _kev_cves =
    CALCULATE(
        COUNTROWS(Findings),
        CONTAINSSTRING(Findings[message], "KEV")
            || CONTAINSSTRING(Findings[message], "Known Exploited")
    )
RETURN
    IF(
        _kev_cves > 0,
        _kev_cves & " finding(s) on CISA Known Exploited Vulnerabilities list — prioritize immediately",
        "No CISA KEV matches detected"
    )
```

```dax
CISA KEV Color =
VAR _kev =
    CALCULATE(
        COUNTROWS(Findings),
        CONTAINSSTRING(Findings[message], "KEV")
            || CONTAINSSTRING(Findings[message], "Known Exploited")
    )
RETURN
    IF(_kev > 0, "#C62828", "#2E7D32")
```

#### V8.3 — By Package Manager
- **Type:** Donut chart
- **Position:** Top-right
- **Legend:** Findings[scanner]
- **Values:** Count of dependency findings
- **Filter:** Only dependency scanners

#### V8.4 — Top Vulnerable Packages Table
- **Type:** Table (10 rows)
- **Position:** Bottom half
- **Columns:** Package (from message parsing), CVSS, CWE, Severity, Scanner, Repo
- **Sort:** Descending by CVSS

```dax
Package Name =
VAR _msg = Findings[message]
VAR _colonPos = FIND(":", _msg, 1, 0)
RETURN
    IF(
        _colonPos > 0,
        LEFT(_msg, _colonPos - 1),
        LEFT(_msg, 40)
    )
```

#### V8.5 — Dependency Age Indicator
- **Type:** Gauge
- **Position:** Right of CVE distribution
- **Value:** `[Dependency Health Score]`

```dax
Dependency Health Score =
VAR _dep_findings =
    CALCULATE(
        COUNTROWS(Findings),
        Findings[scanner] IN {"pip-audit", "npm-audit", "cyclonedx"},
        Findings[status] = "open"
    )
VAR _total_deps =
    CALCULATE(
        COUNTROWS(Findings),
        Findings[scanner] IN {"pip-audit", "npm-audit", "cyclonedx"}
    )
RETURN
    IF(
        _total_deps = 0,
        100,
        ROUND((1 - DIVIDE(_dep_findings, _total_deps)) * 100, 0)
    )
```

- **Target:** 90 (green zone)
- **Ranges:** 0-59 red, 60-89 yellow, 90-100 green

### Drill-Through Target
- From Page 2: OWASP bar "A06:2021 - Vulnerable and Outdated Components" or scanner = pip-audit/npm-audit

---

## Page 9: Security Misconfiguration

**Purpose:** Missing security headers, permissive CORS, debug mode in production, missing CSRF protection, insecure defaults, exposed admin endpoints.

**Page-level filter:** `Findings[owasp] = "A05:2021 - Security Misconfiguration"`
**Rule ID prefixes:** Transport rules mapped to A05, netcompat rules (ZSC-*)

### Page-Specific Visuals

#### V9.1 — Misconfiguration Type Breakdown
- **Type:** Stacked bar chart (horizontal)
- **Position:** Top-right
- **Axis:** `[Misconfiguration Type]`
- **Values:** Count of findings
- **Legend:** Findings[severity]

```dax
Misconfiguration Type =
SWITCH(
    TRUE(),
    CONTAINSSTRING(Findings[message], "CORS") || CONTAINSSTRING(Findings[message], "cors"), "Permissive CORS",
    CONTAINSSTRING(Findings[message], "debug") || CONTAINSSTRING(Findings[message], "DEBUG"), "Debug Mode Enabled",
    CONTAINSSTRING(Findings[message], "CSRF") || CONTAINSSTRING(Findings[message], "csrf"), "Missing CSRF Protection",
    CONTAINSSTRING(Findings[message], "header") || CONTAINSSTRING(Findings[message], "Header"), "Missing Security Headers",
    CONTAINSSTRING(Findings[rule_id], "zsc-") || CONTAINSSTRING(Findings[rule_id], "ZSC-"), "Network/Proxy Misconfiguration",
    CONTAINSSTRING(Findings[message], "admin") || CONTAINSSTRING(Findings[message], "Admin"), "Exposed Admin Endpoint",
    "Other Misconfiguration"
)
```

#### V9.2 — Environment Risk Matrix
- **Type:** Matrix
- **Position:** Bottom-left
- **Rows:** Findings[repo]
- **Columns:** `[Misconfiguration Type]`
- **Values:** Count of findings
- **Conditional formatting:** Background gradient (green 0 → red for higher counts)

#### V9.3 — Quick Wins Card
- **Type:** Card (multi-line)
- **Position:** Below severity cards, right
- **Value:** `[Quick Win Count]`

```dax
Quick Win Count =
VAR _header_fixes =
    CALCULATE(
        COUNTROWS(Findings),
        CONTAINSSTRING(Findings[message], "header"),
        Findings[status] = "open"
    )
VAR _debug_fixes =
    CALCULATE(
        COUNTROWS(Findings),
        CONTAINSSTRING(Findings[message], "debug"),
        Findings[status] = "open"
    )
VAR _csrf_fixes =
    CALCULATE(
        COUNTROWS(Findings),
        CONTAINSSTRING(Findings[message], "CSRF"),
        Findings[status] = "open"
    )
RETURN
    (_header_fixes + _debug_fixes + _csrf_fixes) & " quick-win fixes available (headers, debug flags, CSRF tokens)"
```

#### V9.4 — Netcompat Overlay
- **Type:** Info banner
- **Position:** Top of page, below title
- **Value:** `[Netcompat Misconfig Count]`

```dax
Netcompat Misconfig Count =
VAR _netcompat =
    CALCULATE(
        COUNTROWS(Findings),
        OR(
            CONTAINSSTRING(Findings[rule_id], "zsc-"),
            CONTAINSSTRING(Findings[rule_id], "ZSC-")
        ),
        Findings[status] = "open"
    )
RETURN
    IF(
        _netcompat > 0,
        _netcompat & " finding(s) are network/proxy related — see Page 10 (Zscaler Compatibility) for detailed analysis",
        ""
    )
```

- **Conditional formatting:** Background = #16213E when visible, hidden when empty

### Drill-Through Target
- From Page 2: OWASP bar "A05:2021 - Security Misconfiguration"
- Cross-links to Page 10 (Zscaler Compatibility) for ZSC-* findings

---

## Cross-Page Navigation (Pages 4-9)

Each threat drilldown page includes a navigation row at the bottom:

```
[< Back to Threat Landscape] [Injection] [Auth] [Secrets] [Encryption] [Dependencies] [Misconfig]
```

- **Type:** Button row (bookmarks)
- **Current page:** Highlighted with accent-teal underline
- **Other pages:** Text buttons, grey
- **Back button:** Returns to Page 2 (clears drill-through filters)

### Bookmark Configuration

| Bookmark | Target | Preserves Filters |
|---|---|---|
| Nav-Injection | Page 4 | No (clears to page default) |
| Nav-Auth | Page 5 | No |
| Nav-Secrets | Page 6 | No |
| Nav-Encryption | Page 7 | No |
| Nav-Dependencies | Page 8 | No |
| Nav-Misconfig | Page 9 | No |
| Nav-Back-Landscape | Page 2 | No |

---

## Tooltip Page (shared across Pages 4-9)

When hovering over a finding row in the detail table, show a tooltip page:

```
+-----------------------------------+
| [Rule ID]: [Message]              |
| Severity: [sev]  CVSS: [cvss]    |
| CWE: [cwe]  OWASP: [owasp]      |
|                                   |
| Mitigation: [title]              |
| Effort: [effort_estimate]        |
| Compliance: [controls]           |
+-----------------------------------+
```

### Tooltip DAX

```dax
Tooltip Mitigation Title =
RELATED(Mitigations[title])
```

```dax
Tooltip Effort =
RELATED(Mitigations[effort_estimate])
```

```dax
Tooltip Compliance Controls =
Findings[compliance_controls]
```

**Note:** `RELATED()` works because Findings and Mitigations have a 1:1 relationship on id → finding_id.

---

# Pages 10-14: Infrastructure & Operational Pages

These pages shift from threat-category drill-downs to cross-cutting operational views: infrastructure compatibility, compliance posture, vendor isolation, application inventory, and remediation tracking.

---

## Page 10: Zscaler Compatibility

**Purpose:** Per-application proxy compatibility scoring. Shows which repos have cert pinning, DLP trigger risks, non-standard ports, and other patterns that break under Zscaler SSL inspection. Provides bypass recommendations where needed.

**Primary data source:** Netcompat table (netcompat.csv)
**Secondary data source:** Findings table filtered to ZSC-* rules

### Layout (1280 x 720)

```
+--------------------------------------------------------------+
|  ZSCALER COMPATIBILITY              Org Compat: [score]%     |
+--------------------------------------------------------------+
|                                                               |
|  +----------------------------------------------------------+|
|  | PER-APP COMPATIBILITY (bar chart)                         ||
|  | repo-a  ████████████████████░░░░  82%                     ||
|  | repo-b  ████████████████░░░░░░░░  65%                     ||
|  | repo-c  ██████████░░░░░░░░░░░░░░  42%  [!]               ||
|  +----------------------------------------------------------+|
|                                                               |
|  +---------------------------+  +---------------------------+ |
|  | ISSUE CATEGORY (donut)    |  | DLP RISK ASSESSMENT       | |
|  |  Cert Pinning: 35%       |  | HIGH: 3 repos             | |
|  |  Custom SSL: 25%         |  | MEDIUM: 5 repos           | |
|  |  Non-std Ports: 20%      |  | LOW: 4 repos              | |
|  |  WebSocket: 15%          |  |                           | |
|  |  Other: 5%               |  | [data terms at risk]     | |
|  +---------------------------+  +---------------------------+ |
|                                                               |
|  +----------------------------------------------------------+|
|  | DETAIL TABLE                                              ||
|  | repo | score | cert_pin | dlp | ports | fixes_needed     ||
|  +----------------------------------------------------------+|
|                                                               |
|  [Slicer: Score Range] [Slicer: Issue Type]                  |
+--------------------------------------------------------------+
```

### Visuals

#### V10.1 — Org Compatibility Score
- **Type:** Card (large)
- **Position:** Header area, right-aligned
- **Value:** `[Org Zscaler Score]`

```dax
Org Zscaler Score =
AVERAGE(Netcompat[zscaler_score])
```

```dax
Org Zscaler Score Label =
FORMAT([Org Zscaler Score], "0") & "% compatible"
```

```dax
Org Zscaler Color =
SWITCH(
    TRUE(),
    [Org Zscaler Score] >= 85, "#2E7D32",
    [Org Zscaler Score] >= 60, "#F9A825",
    "#C62828"
)
```

- **Conditional formatting:** Font color = `[Org Zscaler Color]`

#### V10.2 — Per-App Compatibility Bar Chart
- **Type:** Bar chart (horizontal)
- **Position:** Top half, full width
- **Axis:** Netcompat[repo]
- **Values:** Netcompat[zscaler_score]
- **Sort:** Ascending by score (worst first)
- **Conditional formatting:** Bar color gradient:
  - 85-100 → #2E7D32 (green)
  - 60-84 → #F9A825 (amber)
  - 0-59 → #C62828 (red)
- **Data labels:** Score percentage at end of bar
- **Reference line:** Vertical at 85% (green dashed, "target")

#### V10.3 — Issue Category Donut
- **Type:** Donut chart
- **Position:** Middle-left
- **Legend:** `[Zscaler Issue Category]`
- **Values:** Count of ZSC-* findings

```dax
Zscaler Issue Category =
SWITCH(
    TRUE(),
    CONTAINSSTRING(Findings[rule_id], "zsc-001") || CONTAINSSTRING(Findings[rule_id], "ZSC-001"), "Certificate Pinning",
    CONTAINSSTRING(Findings[rule_id], "zsc-002") || CONTAINSSTRING(Findings[rule_id], "ZSC-002"), "Custom SSL Context",
    CONTAINSSTRING(Findings[rule_id], "zsc-003") || CONTAINSSTRING(Findings[rule_id], "ZSC-003"), "Hardcoded CA Bundle",
    CONTAINSSTRING(Findings[rule_id], "zsc-004") || CONTAINSSTRING(Findings[rule_id], "ZSC-004"), "Non-Standard Port",
    CONTAINSSTRING(Findings[rule_id], "zsc-005") || CONTAINSSTRING(Findings[rule_id], "ZSC-005"), "WebSocket Without TLS",
    CONTAINSSTRING(Findings[rule_id], "zsc-006") || CONTAINSSTRING(Findings[rule_id], "ZSC-006"), "Custom DNS Resolution",
    CONTAINSSTRING(Findings[rule_id], "zsc-007") || CONTAINSSTRING(Findings[rule_id], "ZSC-007"), "mTLS Configuration",
    "Other Network Issue"
)
```

- **Color mapping:**
  - Certificate Pinning → #C62828
  - Custom SSL Context → #E65100
  - Hardcoded CA Bundle → #F9A825
  - Non-Standard Port → #1565C0
  - WebSocket Without TLS → #6A1B9A
  - Custom DNS Resolution → #00838F
  - mTLS Configuration → #4E342E

#### V10.4 — DLP Risk Assessment Card
- **Type:** Multi-row card
- **Position:** Middle-right
- **Values:**

```dax
DLP High Risk Repos =
CALCULATE(
    DISTINCTCOUNT(Netcompat[repo]),
    Netcompat[dlp_risk] = "high"
)
```

```dax
DLP Medium Risk Repos =
CALCULATE(
    DISTINCTCOUNT(Netcompat[repo]),
    Netcompat[dlp_risk] = "medium"
)
```

```dax
DLP Low Risk Repos =
CALCULATE(
    DISTINCTCOUNT(Netcompat[repo]),
    Netcompat[dlp_risk] = "low"
)
```

```dax
DLP Risk Summary =
"HIGH: " & [DLP High Risk Repos] & " repos" & UNICHAR(10) &
"MEDIUM: " & [DLP Medium Risk Repos] & " repos" & UNICHAR(10) &
"LOW: " & [DLP Low Risk Repos] & " repos"
```

- **Subtitle:** "Repos transmitting data terms that may trigger Zscaler DLP rules"

#### V10.5 — Netcompat Detail Table
- **Type:** Table (full width, paginated)
- **Position:** Bottom half
- **Columns:**

| Column | Source | Width | Format |
|---|---|---|---|
| Repo | Netcompat[repo] | 140px | Text |
| Score | Netcompat[zscaler_score] | 70px | Integer + "%" |
| Cert Pinning | Netcompat[cert_pinning] | 90px | Conditional icon |
| DLP Risk | Netcompat[dlp_risk] | 80px | Conditional bg color |
| Port Issues | Netcompat[port_issues] | 120px | Text |
| Fixes Needed | Netcompat[fixes_needed] | 300px | Text, wrapped |

- **Conditional formatting:**
  - Cert Pinning: "fail" → red bg, "pass" → green bg, "not_applicable" → grey
  - DLP Risk: "high" → red bg, "medium" → amber bg, "low" → green bg
  - Score: data bars with RAG coloring

#### V10.6 — Slicers
- Score range slicer (buttons: 0-59, 60-84, 85-100)
- Issue type slicer (dropdown, `[Zscaler Issue Category]`)

### Page-Level Filters
- None (shows all repos with netcompat data)

### Drill-Through
- Click a repo row → drills to Page 13 (Application Inventory) filtered to that repo
- Cross-references Page 7 for TLS verification findings that overlap with Zscaler issues

---

## Page 11: Compliance Mapping

**Purpose:** Framework-by-framework compliance posture. Shows which SOC 2, NIST CSF, and OWASP ASVS controls are covered by automated scanning, which have gaps, and the finding density per control.

**Primary data source:** Compliance table (compliance.csv)
**Secondary data source:** Findings table (for control-level drill-through)

### Layout (1280 x 720)

```
+--------------------------------------------------------------+
|  COMPLIANCE MAPPING         [Covered]% coverage | [Gaps] gaps|
+--------------------------------------------------------------+
|                                                               |
|  [Tab: SOC 2] [Tab: NIST CSF] [Tab: OWASP ASVS]            |
|                                                               |
|  +----------------------------------------------------------+|
|  | CONTROL TABLE                                             ||
|  | framework | control_id | title | covered | findings | gap ||
|  | SOC2      | CC6.1      | ...   | yes     | 12       |     ||
|  | SOC2      | CC6.6      | ...   | yes     | 8        |     ||
|  | SOC2      | CC7.1      | ...   | partial | 0        | GAP ||
|  +----------------------------------------------------------+|
|                                                               |
|  +---------------------------+  +---------------------------+ |
|  | COVERAGE GAUGE            |  | GAP SUMMARY               | |
|  |    [====75%====]          |  | SOC 2: 2 gaps             | |
|  |                           |  | NIST CSF: 4 gaps          | |
|  |                           |  | OWASP ASVS: 1 gap        | |
|  +---------------------------+  +---------------------------+ |
|                                                               |
|  +----------------------------------------------------------+|
|  | FINDING DENSITY HEATMAP (controls × severity)             ||
|  +----------------------------------------------------------+|
+--------------------------------------------------------------+
```

### Visuals

#### V11.1 — Coverage KPI Cards
- **Type:** Card row (header area)
- **Values:**

```dax
Compliance Coverage Pct =
VAR _total = COUNTROWS(Compliance)
VAR _covered =
    CALCULATE(
        COUNTROWS(Compliance),
        Compliance[gap_status] = "covered"
    )
RETURN
    IF(_total > 0, DIVIDE(_covered, _total) * 100, 0)
```

```dax
Compliance Coverage Label =
FORMAT([Compliance Coverage Pct], "0") & "% coverage"
```

```dax
Total Gaps =
CALCULATE(
    COUNTROWS(Compliance),
    Compliance[gap_status] = "gap"
)
```

#### V11.2 — Framework Tab Selector
- **Type:** Slicer (horizontal buttons, single-select)
- **Position:** Below header
- **Field:** Compliance[framework]
- **Values:** SOC2, NIST-CSF, OWASP-ASVS, CWE-TOP25
- **Style:** Tab-style buttons with accent-teal active indicator

#### V11.3 — Control Table
- **Type:** Table (full width, paginated 20 rows)
- **Position:** Upper half
- **Columns:**

| Column | Source | Width | Format |
|---|---|---|---|
| Framework | Compliance[framework] | 80px | Text |
| Control ID | Compliance[control_id] | 120px | Text, bold |
| Title | Compliance[title] | 280px | Text, wrapped |
| Covered | Compliance[covered_by_scan] | 80px | Conditional icon |
| Findings | Compliance[finding_count] | 80px | Integer |
| Gap Status | Compliance[gap_status] | 80px | Conditional bg |

- **Conditional formatting:**
  - Covered: "yes" → green check icon, "partial" → amber warning, "no" → red X
  - Gap Status: "gap" → #C62828 background with white text, "covered" → transparent
  - Finding Count: data bars (teal)
- **Sort:** Framework asc, then gap_status desc (gaps first), then control_id asc

#### V11.4 — Coverage Gauge
- **Type:** Gauge
- **Position:** Bottom-left
- **Value:** `[Compliance Coverage Pct]`
- **Target:** 100
- **Min:** 0, **Max:** 100
- **Ranges:** 0-59 red, 60-84 yellow, 85-100 green
- **Label:** "Control Coverage"

#### V11.5 — Gap Summary by Framework
- **Type:** Multi-row card
- **Position:** Bottom-right
- **Values:**

```dax
SOC2 Gaps =
CALCULATE(
    COUNTROWS(Compliance),
    Compliance[framework] = "SOC2",
    Compliance[gap_status] = "gap"
)
```

```dax
NIST Gaps =
CALCULATE(
    COUNTROWS(Compliance),
    Compliance[framework] = "NIST-CSF",
    Compliance[gap_status] = "gap"
)
```

```dax
OWASP ASVS Gaps =
CALCULATE(
    COUNTROWS(Compliance),
    Compliance[framework] = "OWASP-ASVS",
    Compliance[gap_status] = "gap"
)
```

```dax
CWE Top 25 Gaps =
CALCULATE(
    COUNTROWS(Compliance),
    Compliance[framework] = "CWE-TOP25",
    Compliance[gap_status] = "gap"
)
```

- **Format:** "{framework}: {N} gap(s)" per row
- **Conditional formatting:** Row color red if gaps > 0, green if 0

#### V11.6 — Finding Density Heatmap
- **Type:** Matrix
- **Position:** Bottom, full width
- **Rows:** Compliance[control_id] (top 15 by finding_count)
- **Columns:** Fixed: "Critical", "High", "Medium", "Low"
- **Values:** Count of findings per control per severity

```dax
Control Finding Count by Severity =
VAR _control = SELECTEDVALUE(Compliance[control_id])
RETURN
    CALCULATE(
        COUNTROWS(Findings),
        CONTAINSSTRING(Findings[compliance_controls], _control)
    )
```

- **Conditional formatting:** Background gradient (white → severity color by cell value)
- **Filter:** Top 15 controls by finding_count to avoid clutter

### Page-Level Filters
- Framework tab slicer (default: show all)

### Drill-Through
- Click a control row → filters the Finding Detail table on Pages 4-9 to findings with that control in compliance_controls

---

## Page 12: Vendor Data Isolation Deep Dive

**Purpose:** Dedicated view for multi-tenant data isolation audit. Shows tenant scoping coverage across all repos, IDOR findings matrix, and vendor data leakage risks. Critical for Kroger vendor data protection.

**Primary data source:** Findings table filtered to access control rules
**Filter:** Rule IDs containing `auth-001`, `auth-002`, `auth-004`, or CWE-639, CWE-284, CWE-200

### Layout (1280 x 720)

```
+--------------------------------------------------------------+
|  VENDOR DATA ISOLATION             [Status Badge]            |
+--------------------------------------------------------------+
|                                                               |
|  +---------+---------+---------+                             |
|  | TENANT  | IDOR    | BULK    |  category KPI cards        |
|  | SCOPE   | VULNS   | EXPORT  |                            |
|  |   5     |   3     |   2     |                            |
|  +---------+---------+---------+                             |
|                                                               |
|  +---------------------------+  +---------------------------+ |
|  | ISOLATION BY REPO (matrix)|  | RISK FLOW DIAGRAM         | |
|  |         | tenant | idor   |  | [user] → [API] → [DB]    | |
|  | repo-a  |  FAIL  | FAIL   |  |   ↓ missing scope ↓      | |
|  | repo-b  |  PASS  | PASS   |  |  [vendor_id filter?]     | |
|  | repo-c  |  FAIL  | PASS   |  |                           | |
|  +---------------------------+  +---------------------------+ |
|                                                               |
|  +----------------------------------------------------------+|
|  | FINDING DETAIL (filtered to isolation rules)              ||
|  | repo | file | line | rule | sev | age | message          ||
|  +----------------------------------------------------------+|
+--------------------------------------------------------------+
```

### Visuals

#### V12.1 — Isolation Status Badge
- **Type:** Card (large)
- **Position:** Header area, right-aligned
- **Value:** `[Isolation Status]`

```dax
Isolation Status =
VAR _open_tenant =
    CALCULATE(
        COUNTROWS(Findings),
        OR(
            CONTAINSSTRING(Findings[rule_id], "auth-001"),
            CONTAINSSTRING(Findings[cwe], "CWE-639")
        ),
        Findings[status] = "open"
    )
VAR _open_idor =
    CALCULATE(
        COUNTROWS(Findings),
        OR(
            CONTAINSSTRING(Findings[rule_id], "auth-002"),
            CONTAINSSTRING(Findings[cwe], "CWE-284")
        ),
        Findings[status] = "open"
    )
VAR _open_export =
    CALCULATE(
        COUNTROWS(Findings),
        OR(
            CONTAINSSTRING(Findings[rule_id], "auth-004"),
            CONTAINSSTRING(Findings[cwe], "CWE-200")
        ),
        Findings[status] = "open"
    )
VAR _total = _open_tenant + _open_idor + _open_export
RETURN
    IF(
        _total = 0,
        "FULLY ISOLATED",
        "AT RISK — " & _total & " isolation finding(s) open"
    )
```

```dax
Isolation Status Color =
VAR _open =
    CALCULATE(
        COUNTROWS(Findings),
        OR(
            CONTAINSSTRING(Findings[rule_id], "auth-001"),
            CONTAINSSTRING(Findings[rule_id], "auth-002"),
            CONTAINSSTRING(Findings[rule_id], "auth-004")
        ),
        Findings[status] = "open"
    )
RETURN
    IF(_open = 0, "#2E7D32", "#C62828")
```

#### V12.2 — Category KPI Cards
- **Type:** Card row (3 cards)
- **Position:** Below header

```dax
Tenant Scope Findings =
CALCULATE(
    COUNTROWS(Findings),
    OR(
        CONTAINSSTRING(Findings[rule_id], "auth-001"),
        CONTAINSSTRING(Findings[cwe], "CWE-639")
    ),
    Findings[status] = "open"
)
```

```dax
IDOR Findings =
CALCULATE(
    COUNTROWS(Findings),
    OR(
        CONTAINSSTRING(Findings[rule_id], "auth-002"),
        CONTAINSSTRING(Findings[cwe], "CWE-284")
    ),
    Findings[status] = "open"
)
```

```dax
Bulk Export Findings =
CALCULATE(
    COUNTROWS(Findings),
    OR(
        CONTAINSSTRING(Findings[rule_id], "auth-004"),
        CONTAINSSTRING(Findings[cwe], "CWE-200")
    ),
    Findings[status] = "open"
)
```

- **Labels:** "Tenant Scope", "IDOR Vulns", "Bulk Export"
- **Conditional formatting:** Card border red if > 0, green if 0

#### V12.3 — Isolation by Repo Matrix
- **Type:** Matrix
- **Position:** Middle-left
- **Rows:** Repos[name]
- **Columns:** "Tenant Scope", "IDOR", "Bulk Export"
- **Values:** `[Isolation Cell Status]`

```dax
Tenant Scope Cell =
VAR _count =
    CALCULATE(
        COUNTROWS(Findings),
        OR(
            CONTAINSSTRING(Findings[rule_id], "auth-001"),
            CONTAINSSTRING(Findings[cwe], "CWE-639")
        ),
        Findings[status] = "open"
    )
RETURN
    IF(_count = 0, "PASS", "FAIL (" & _count & ")")
```

```dax
IDOR Cell =
VAR _count =
    CALCULATE(
        COUNTROWS(Findings),
        OR(
            CONTAINSSTRING(Findings[rule_id], "auth-002"),
            CONTAINSSTRING(Findings[cwe], "CWE-284")
        ),
        Findings[status] = "open"
    )
RETURN
    IF(_count = 0, "PASS", "FAIL (" & _count & ")")
```

```dax
Bulk Export Cell =
VAR _count =
    CALCULATE(
        COUNTROWS(Findings),
        OR(
            CONTAINSSTRING(Findings[rule_id], "auth-004"),
            CONTAINSSTRING(Findings[cwe], "CWE-200")
        ),
        Findings[status] = "open"
    )
RETURN
    IF(_count = 0, "PASS", "FAIL (" & _count & ")")
```

- **Conditional formatting:**
  - Cell background: PASS → #2E7D32 (green), FAIL → #C62828 (red)
  - Font: white on colored background

#### V12.4 — Data Flow Risk Diagram
- **Type:** Image or text card (static reference diagram)
- **Position:** Middle-right
- **Content:** Visual representation of the multi-tenant data flow:
  - User Request → API Layer (auth check?) → DB Query (vendor_id WHERE clause?)
  - Highlights where tenant isolation should be enforced
- **Implementation:** Static SVG or text-based diagram embedded in a text card. Use a bookmark to toggle between diagram and a detailed explanation text.

```dax
Data Flow Risk Text =
"Multi-tenant isolation checkpoint:" & UNICHAR(10) &
"1. API Auth → tenant context extracted from JWT?" & UNICHAR(10) &
"2. Query Layer → vendor_id in every WHERE clause?" & UNICHAR(10) &
"3. Export → scoped to authenticated tenant only?" & UNICHAR(10) &
UNICHAR(10) &
"Open failures: " & [Tenant Scope Findings] & " scope, " &
[IDOR Findings] & " IDOR, " & [Bulk Export Findings] & " export"
```

#### V12.5 — Isolation Finding Detail Table
- **Type:** Table (paginated, 15 rows)
- **Position:** Bottom half
- **Filter:** Findings where rule_id contains "auth-001", "auth-002", "auth-004", or CWE IN (639, 284, 200)
- **Columns:** Repo, File, Line, Rule ID, Category (`[Access Control Type]`), Severity, Age, Status, Message
- **Sort:** Severity desc, then age desc

### Page-Level Filters
- Findings filtered to isolation-related rules (auth-001, auth-002, auth-004)
- Status slicer (Open / Resolved / All)

### Drill-Through
- From Page 5 (Auth & Access Control): link for tenant-specific deep dive
- Click repo row → drills to Page 13 (Application Inventory)

---

## Page 13: Application Inventory Heatmap

**Purpose:** Bird's-eye view of all repositories as colored tiles. Each tile represents a repo, colored by risk score, sized by finding count. Click any tile to drill through to its findings.

**Primary data source:** Repos table (repos.csv)
**Secondary data source:** Findings table (for drill-through)

### Layout (1280 x 720)

```
+--------------------------------------------------------------+
|  APPLICATION INVENTORY       [Total Repos] repos | [At Risk] |
+--------------------------------------------------------------+
|                                                               |
|  +----------------------------------------------------------+|
|  |  REPO HEATMAP (treemap)                                   ||
|  |  +----------+--------+------+-------+--------+           ||
|  |  |          |        |      |       |        |           ||
|  |  | repo-a   | repo-b |repo-c|repo-d | repo-e |           ||
|  |  | 78/100   | 62/100 |51/100|45/100 | 38/100 |           ||
|  |  |  RED     | AMBER  |AMBER | GREEN | GREEN  |           ||
|  |  |          |        |      |       |        |           ||
|  |  +----------+--------+------+-------+--------+           ||
|  |  |  repo-f  |repo-g  |repo-h| repo-i|repo-j  |           ||
|  |  +----------+--------+------+-------+--------+           ||
|  +----------------------------------------------------------+|
|                                                               |
|  +---------------------------+  +---------------------------+ |
|  | RISK DISTRIBUTION (hist)  |  | REPO STATS SUMMARY        | |
|  | 0-25  ██  2               |  | Highest risk: repo-a (78) | |
|  | 26-50 ████████ 5          |  | Lowest risk: repo-j (12)  | |
|  | 51-75 ██████ 3            |  | Average: 48.3             | |
|  | 76+   ██ 2                |  | Repos > 60: 3             | |
|  +---------------------------+  +---------------------------+ |
|                                                               |
|  [Slicer: Language] [Slicer: Risk Range]                     |
+--------------------------------------------------------------+
```

### Visuals

#### V13.1 — Header KPIs
- **Type:** Card row
- **Values:** `[Total Repos]`, `[Repos At Risk]`

```dax
Repos At Risk Label =
[Repos At Risk] & " at risk (score > " & [YellowThreshold] & ")"
```

#### V13.2 — Repo Heatmap Treemap
- **Type:** Treemap
- **Position:** Upper 60% of page
- **Group:** Repos[name]
- **Size:** Repos[finding_count]
- **Tooltips:** Name, risk_score, finding_count, critical_count, high_count, last_scan

```dax
Repo Heatmap Color =
SWITCH(
    TRUE(),
    MAX(Repos[risk_score]) >= 70, "#C62828",
    MAX(Repos[risk_score]) >= 50, "#E65100",
    MAX(Repos[risk_score]) >= 30, "#F9A825",
    "#2E7D32"
)
```

- **Conditional formatting:** Tile background color = risk score gradient
  - 0-29 → #2E7D32 (green)
  - 30-49 → #66BB6A (light green)
  - 50-69 → #F9A825 (amber)
  - 70-84 → #E65100 (orange)
  - 85-100 → #C62828 (red)
- **Labels:** Repo name + risk score

#### V13.3 — Risk Distribution Histogram
- **Type:** Column chart
- **Position:** Bottom-left
- **Axis:** `[Risk Bucket]`
- **Values:** Count of repos

```dax
// Calculated column on Repos table
Risk Bucket =
SWITCH(
    TRUE(),
    Repos[risk_score] < 25, "0-24 (Low)",
    Repos[risk_score] < 50, "25-49 (Moderate)",
    Repos[risk_score] < 75, "50-74 (High)",
    "75+ (Critical)"
)
```

```dax
// Calculated column on Repos table
Risk Bucket Sort =
SWITCH(
    TRUE(),
    Repos[risk_score] < 25, 1,
    Repos[risk_score] < 50, 2,
    Repos[risk_score] < 75, 3,
    4
)
```

- **Sort:** By Risk Bucket Sort ascending
- **Color:** Matches heatmap gradient per bucket

#### V13.4 — Repo Stats Summary Card
- **Type:** Multi-row card
- **Position:** Bottom-right

```dax
Highest Risk Repo =
VAR _maxScore = MAX(Repos[risk_score])
VAR _repoName =
    CALCULATE(
        MAX(Repos[name]),
        Repos[risk_score] = _maxScore
    )
RETURN
    _repoName & " (" & FORMAT(_maxScore, "0") & ")"
```

```dax
Lowest Risk Repo =
VAR _minScore = MIN(Repos[risk_score])
VAR _repoName =
    CALCULATE(
        MIN(Repos[name]),
        Repos[risk_score] = _minScore
    )
RETURN
    _repoName & " (" & FORMAT(_minScore, "0") & ")"
```

```dax
Average Risk Score =
AVERAGE(Repos[risk_score])
```

```dax
Repos Above Threshold =
CALCULATE(
    COUNTROWS(Repos),
    Repos[risk_score] >= [YellowThreshold]
)
```

#### V13.5 — Slicers
- Language slicer (dropdown, Repos[language])
- Risk range slicer (buttons: Low 0-24, Moderate 25-49, High 50-74, Critical 75+)

### Page-Level Filters
- None (shows all repos)

### Drill-Through
- **Click any treemap tile:** Drill-through to a filtered view showing all findings for that repo across Pages 4-9. The drill-through passes `Repos[name]` as the filter.
- **Drill-through target page:** This page itself serves as a drill-through target from Pages 1, 10, and 12 (filter by repo name).

---

## Page 14: Mitigation Tracker

**Purpose:** Remediation status board. Track mitigation progress across all findings — what's been fixed, what's in progress, what hasn't started. Effort estimates, burndown projections, and an export function for sprint planning.

**Primary data source:** Mitigations table (mitigations.csv) joined with Findings table
**Filter states:** Not Started, In Progress, Verified Fixed (derived from Findings[status])

### Layout (1280 x 720)

```
+--------------------------------------------------------------+
|  MITIGATION TRACKER           [Progress]% complete           |
+--------------------------------------------------------------+
|                                                               |
|  [Tab: Not Started] [Tab: In Progress] [Tab: Verified Fixed] |
|                                                               |
|  +---------------------------+  +---------------------------+ |
|  | STATUS DISTRIBUTION       |  | EFFORT BREAKDOWN          | |
|  | (stacked bar)             |  | (donut)                   | |
|  | Not Started ████████ 62%  |  |  < 1 hour: 25%           | |
|  | In Progress ████ 28%     |  |  1-4 hours: 40%          | |
|  | Fixed       ██ 10%       |  |  1-2 days: 25%           | |
|  +---------------------------+  |  3+ days: 10%            | |
|                                 +---------------------------+ |
|                                                               |
|  +----------------------------------------------------------+|
|  | MITIGATION TABLE                                          ||
|  | finding_id | rule | title | effort | repo | sev | status ||
|  | ...        | ...  | ...   | 2h     | ...  | ... | open   ||
|  +----------------------------------------------------------+|
|                                                               |
|  +---------------------------+  +---------------------------+ |
|  | BURNDOWN CHART            |  | EFFORT SUMMARY            | |
|  |  ~~~~~~~~~~\              |  | Total: 340h               | |
|  |             \~~~~         |  | Completed: 48h            | |
|  |                  \        |  | Remaining: 292h           | |
|  +---------------------------+  +---------------------------+ |
|                                                               |
|  [Slicer: Severity] [Slicer: Repo] [EXPORT BUTTON]          |
+--------------------------------------------------------------+
```

### Visuals

#### V14.1 — Progress KPI
- **Type:** Card (large)
- **Position:** Header area, right-aligned
- **Value:** `[Mitigation Progress Pct]`

```dax
Mitigation Progress Pct =
VAR _total = COUNTROWS(Findings)
VAR _fixed =
    CALCULATE(
        COUNTROWS(Findings),
        Findings[status] = "resolved"
    )
RETURN
    IF(_total > 0, DIVIDE(_fixed, _total) * 100, 0)
```

```dax
Mitigation Progress Label =
FORMAT([Mitigation Progress Pct], "0") & "% mitigated"
```

```dax
Mitigation Progress Color =
SWITCH(
    TRUE(),
    [Mitigation Progress Pct] >= 80, "#2E7D32",
    [Mitigation Progress Pct] >= 40, "#F9A825",
    "#C62828"
)
```

#### V14.2 — Status Tab Selector
- **Type:** Slicer (horizontal buttons, single-select + "All")
- **Position:** Below header
- **Field:** `[Mitigation Status]`

```dax
// Calculated column on Findings table
Mitigation Status =
SWITCH(
    Findings[status],
    "resolved", "Verified Fixed",
    "suppressed", "Suppressed",
    "open", "Not Started",
    "Not Started"
)
```

- **Style:** Tab buttons
  - Not Started → #C62828 text
  - In Progress → #F9A825 text
  - Verified Fixed → #2E7D32 text

#### V14.3 — Status Distribution Bar
- **Type:** Stacked bar chart (horizontal, single bar)
- **Position:** Middle-left
- **Values:** Count per `[Mitigation Status]`
- **Color:**
  - Not Started → #C62828
  - In Progress → #F9A825
  - Verified Fixed → #2E7D32
  - Suppressed → #757575
- **Data labels:** Percentage inside each segment

#### V14.4 — Effort Breakdown Donut
- **Type:** Donut chart
- **Position:** Middle-right
- **Legend:** `[Effort Bucket]`
- **Values:** Count of mitigations per bucket

```dax
// Calculated column on Mitigations table
Effort Bucket =
SWITCH(
    TRUE(),
    CONTAINSSTRING(Mitigations[effort_estimate], "minute") || Mitigations[effort_estimate] = "< 1 hour", "< 1 hour",
    CONTAINSSTRING(Mitigations[effort_estimate], "hour") && NOT(CONTAINSSTRING(Mitigations[effort_estimate], "day")), "1-4 hours",
    CONTAINSSTRING(Mitigations[effort_estimate], "1 day") || CONTAINSSTRING(Mitigations[effort_estimate], "2 day"), "1-2 days",
    "3+ days"
)
```

```dax
Effort Bucket Sort =
SWITCH(
    [Effort Bucket],
    "< 1 hour", 1,
    "1-4 hours", 2,
    "1-2 days", 3,
    "3+ days", 4,
    5
)
```

- **Color:**
  - < 1 hour → #66BB6A (green, quick win)
  - 1-4 hours → #00BFA5 (teal)
  - 1-2 days → #F9A825 (amber)
  - 3+ days → #E65100 (orange)

#### V14.5 — Mitigation Detail Table
- **Type:** Table (paginated, 15 rows)
- **Position:** Center, full width
- **Columns:**

| Column | Source | Width | Format |
|---|---|---|---|
| Finding | Mitigations[finding_id] | 100px | Text |
| Rule | Mitigations[rule_id] | 90px | Text |
| Title | Mitigations[title] | 200px | Text, wrapped |
| Effort | Mitigations[effort_estimate] | 80px | Text |
| Repo | Findings[repo] (via relationship) | 120px | Text |
| Severity | Findings[severity] (via relationship) | 80px | Conditional bg |
| Status | `[Mitigation Status]` | 100px | Conditional icon/color |
| Fix | Mitigations[immediate_fix] | 200px | Text, truncated |

- **Conditional formatting:**
  - Severity: background by severity color
  - Status: Not Started = red circle, In Progress = amber clock, Verified Fixed = green check
- **Sort:** Severity desc, then effort estimate asc (quick wins first within severity)
- **Row expand:** Click to show code_before / code_after / verification_test

#### V14.6 — Burndown Chart
- **Type:** Line chart
- **Position:** Bottom-left
- **Axis:** Trends[date]
- **Values:**
  - `[Remaining Findings Trend]` — line (red, decreasing)
  - `[Projected Burndown]` — dashed line (grey, projected to zero)

```dax
Remaining Findings Trend =
MAX(Trends[total_findings]) - MAX(Trends[resolved_count])
```

```dax
Resolution Velocity =
VAR _trend_rows = COUNTROWS(Trends)
VAR _first_remaining =
    CALCULATE(
        MAX(Trends[total_findings]) - MAX(Trends[resolved_count]),
        TOPN(1, ALL(Trends), Trends[date], ASC)
    )
VAR _last_remaining =
    CALCULATE(
        MAX(Trends[total_findings]) - MAX(Trends[resolved_count]),
        TOPN(1, ALL(Trends), Trends[date], DESC)
    )
RETURN
    IF(
        _trend_rows > 1 && _first_remaining > _last_remaining,
        DIVIDE(_first_remaining - _last_remaining, _trend_rows),
        BLANK()
    )
```

- **Reference line:** Horizontal at 0 (dashed green, "target: zero")

#### V14.7 — Effort Summary Card
- **Type:** Multi-row card
- **Position:** Bottom-right

```dax
Total Effort Hours =
VAR _hourValues =
    ADDCOLUMNS(
        Mitigations,
        "hours",
        SWITCH(
            TRUE(),
            CONTAINSSTRING(Mitigations[effort_estimate], "minute"), 0.5,
            CONTAINSSTRING(Mitigations[effort_estimate], "< 1 hour"), 0.5,
            CONTAINSSTRING(Mitigations[effort_estimate], "1-2 hour"), 1.5,
            CONTAINSSTRING(Mitigations[effort_estimate], "2-4 hour"), 3,
            CONTAINSSTRING(Mitigations[effort_estimate], "4-8 hour"), 6,
            CONTAINSSTRING(Mitigations[effort_estimate], "1 day"), 8,
            CONTAINSSTRING(Mitigations[effort_estimate], "2 day"), 16,
            CONTAINSSTRING(Mitigations[effort_estimate], "1 week"), 40,
            4
        )
    )
RETURN
    SUMX(_hourValues, [hours])
```

```dax
Completed Effort Hours =
VAR _resolved =
    CALCULATETABLE(
        Mitigations,
        Findings[status] = "resolved"
    )
VAR _hourValues =
    ADDCOLUMNS(
        _resolved,
        "hours",
        SWITCH(
            TRUE(),
            CONTAINSSTRING(Mitigations[effort_estimate], "minute"), 0.5,
            CONTAINSSTRING(Mitigations[effort_estimate], "< 1 hour"), 0.5,
            CONTAINSSTRING(Mitigations[effort_estimate], "1-2 hour"), 1.5,
            CONTAINSSTRING(Mitigations[effort_estimate], "2-4 hour"), 3,
            CONTAINSSTRING(Mitigations[effort_estimate], "4-8 hour"), 6,
            CONTAINSSTRING(Mitigations[effort_estimate], "1 day"), 8,
            CONTAINSSTRING(Mitigations[effort_estimate], "2 day"), 16,
            CONTAINSSTRING(Mitigations[effort_estimate], "1 week"), 40,
            4
        )
    )
RETURN
    SUMX(_hourValues, [hours])
```

```dax
Remaining Effort Hours =
[Total Effort Hours] - [Completed Effort Hours]
```

- **Format:** "Total: {N}h | Completed: {N}h | Remaining: {N}h"

#### V14.8 — Export Button
- **Type:** Button
- **Position:** Bottom bar, right-aligned
- **Action:** Export current table view to CSV via Power BI "Export data" action
- **Label:** "Export to CSV for Sprint Planning"
- **Style:** Accent-teal background, white text

#### V14.9 — Slicers
- Severity slicer (buttons, multi-select)
- Repo slicer (dropdown, multi-select)

### Page-Level Filters
- None by default (shows all mitigations across all statuses)

### Drill-Through
- Click a finding row → drills to the relevant threat page (4-9) filtered by that finding's OWASP category
- Status tab filters the entire page including burndown chart

---

## Cross-Page Navigation (Pages 10-14)

Each infrastructure/operational page includes a navigation row:

```
[< Executive Summary] [Zscaler] [Compliance] [Isolation] [Inventory] [Tracker]
```

- **Type:** Button row (bookmarks)
- **Current page:** Highlighted with accent-teal underline
- **Back button:** Returns to Page 1 (Executive Summary)

### Bookmark Configuration

| Bookmark | Target |
|---|---|
| Nav-Zscaler | Page 10 |
| Nav-Compliance | Page 11 |
| Nav-Isolation | Page 12 |
| Nav-Inventory | Page 13 |
| Nav-Tracker | Page 14 |
| Nav-DAST | Page 15 |
| Nav-Binary | Page 16 |
| Nav-Back-Executive | Page 1 |

---

## New Shared DAX Measures (Multi-Target Type)

These measures support the DAST and Binary Analysis pages. Add them to the `_Measures` table alongside the existing measures.

### Target Type Filters

```dax
DAST Findings =
CALCULATE(
    COUNTROWS(Findings),
    Findings[target_type] = "webapp"
)
```

```dax
Binary Findings =
CALCULATE(
    COUNTROWS(Findings),
    Findings[target_type] = "binary"
)
```

```dax
SAST Findings =
CALCULATE(
    COUNTROWS(Findings),
    Findings[target_type] = "repo"
)
```

```dax
Web Apps Scanned =
CALCULATE(
    DISTINCTCOUNT(Findings[target_name]),
    Findings[target_type] = "webapp"
)
```

```dax
Binaries Analyzed =
CALCULATE(
    DISTINCTCOUNT(Findings[target_name]),
    Findings[target_type] = "binary"
)
```

```dax
Critical DAST =
CALCULATE(
    COUNTROWS(Findings),
    Findings[target_type] = "webapp",
    Findings[severity] = "critical"
)
```

```dax
Failed Hardening Checks =
CALCULATE(
    COUNTROWS(Findings),
    Findings[target_type] = "binary",
    LEFT(Findings[rule_id], 7) = "BIN-chk"
)
```

```dax
YARA Matches =
CALCULATE(
    COUNTROWS(Findings),
    Findings[target_type] = "binary",
    LEFT(Findings[rule_id], 7) = "BIN-yar"
)
```

---

## Data Model Updates for Multi-Target Support

### Findings table — new columns

| Column | Type | Description |
|---|---|---|
| target_type | string | `repo` / `webapp` / `binary` (default: `repo`) |
| target_name | string | Target identifier from client profile |
| url | string | nullable — full URL for webapp findings |
| http_method | string | nullable — GET/POST/PUT for webapp findings |
| binary_hash | string | nullable — SHA256 for binary findings |

### New table: Targets

| Column | Type | Source |
|---|---|---|
| name | string | targets.csv |
| target_type | string | targets.csv |
| url | string | targets.csv (webapp only) |
| platform | string | targets.csv (binary only) |
| last_scan | date | targets.csv |
| risk_score | float | targets.csv |
| finding_count | int | targets.csv |

### New relationships

| From | To | Key | Cardinality |
|---|---|---|---|
| Findings.target_name | Targets.name | target_name → name | M:1 |

### Page 1 update: Add target_type slicer

Add a **Slicer** visual to Page 1 (Org Security Score):
- **Field:** Findings[target_type]
- **Type:** Dropdown
- **Position:** Top-right, next to client/enterprise title
- **Default:** "All" (no filter)
- **Purpose:** Exec can filter entire dashboard by repo/webapp/binary

### Page 13 update: Rename to "Target Inventory"

Rename Page 13 from "Application Inventory" to "Target Inventory":
- Change table to source from Targets table instead of Repos
- Add `target_type` column to the table
- Add `url` column (shows URL for webapps, blank for repos/binaries)
- Add `platform` column (shows platform for binaries, blank otherwise)
- Keep existing risk_score and finding_count columns

---

## Page 15: DAST Overview

**Purpose:** Web application security posture from dynamic testing. What vulnerabilities were found by actively scanning running applications?

**Background:** Dark (#1A1A2E)
**Accent:** Orange (#FF6D00) for DAST-specific highlights

### Layout (1280 x 720)

```
+--------------------------------------------------------------+
|  DAST OVERVIEW                       [Client] / [Enterprise] |
+--------------------------------------------------------------+
|                                                               |
|  +----------+ +----------+ +----------+                      |
|  | DAST     | | CRITICAL | | WEB APPS |                      |
|  | FINDINGS | | DAST     | | SCANNED  |                      |
|  |    42    | |    3     | |    2     |                      |
|  +----------+ +----------+ +----------+                      |
|                                                               |
|  +-----------------------------+  +-------------------------+ |
|  | FINDINGS BY OWASP CATEGORY  |  | FINDINGS BY WEB APP     | |
|  | A03 Injection    ████ 12   |  |  [DONUT CHART]          | |
|  | A05 Misconfig    ███ 9    |  |  vendor-portal: 28      | |
|  | A01 Access       ██ 7     |  |  pricing-api: 14        | |
|  | A02 Crypto       ██ 6     |  |                         | |
|  | A07 Auth         █ 4      |  |                         | |
|  | A10 SSRF         █ 2      |  |                         | |
|  | Other            █ 2      |  |                         | |
|  +-----------------------------+  +-------------------------+ |
|                                                               |
|  +----------------------------------------------------------+ |
|  | DAST FINDINGS TABLE                                       | |
|  | URL | Method | Severity | Rule | Parameter | Message     | |
|  | ... | POST   | HIGH     | ... | search    | SQL Inj...  | |
|  | ... | GET    | MEDIUM   | ... |           | CSP Not...  | |
|  +----------------------------------------------------------+ |
+--------------------------------------------------------------+
```

### Visuals

#### V15.1 — DAST Findings Card
- **Type:** Card
- **Value:** `[DAST Findings]`
- **Format:** Integer, 48pt bold, orange accent

#### V15.2 — Critical DAST Card
- **Type:** Card
- **Value:** `[Critical DAST]`
- **Format:** Integer, 48pt bold, red (#C62828) conditional if > 0

#### V15.3 — Web Apps Scanned Card
- **Type:** Card
- **Value:** `[Web Apps Scanned]`
- **Format:** Integer, 48pt bold, teal accent

#### V15.4 — Findings by OWASP Category
- **Type:** Clustered bar chart (horizontal)
- **Axis:** Findings[owasp]
- **Values:** Count of Findings
- **Filter:** Findings[target_type] = "webapp"
- **Sort:** Descending by count
- **Colors:** Severity-based conditional (critical=red, high=orange, medium=yellow)

#### V15.5 — Findings by Web App
- **Type:** Donut chart
- **Values:** Count of Findings
- **Legend:** Findings[target_name]
- **Filter:** Findings[target_type] = "webapp"
- **Colors:** Auto-assigned from theme palette

#### V15.6 — DAST Findings Table
- **Type:** Table
- **Columns:** url, http_method, severity, rule_id, message
- **Filter:** Findings[target_type] = "webapp"
- **Sort:** severity (critical first)
- **Conditional formatting:** severity column background (critical=red, high=orange, medium=yellow, low=gray)
- **Row limit:** Top 100

---

## Page 16: Binary Analysis

**Purpose:** Binary hardening posture and malware/secrets detection. Are our executables hardened against exploitation?

**Background:** Dark (#1A1A2E)
**Accent:** Purple (#7C4DFF) for binary-specific highlights

### Layout (1280 x 720)

```
+--------------------------------------------------------------+
|  BINARY ANALYSIS                     [Client] / [Enterprise] |
+--------------------------------------------------------------+
|                                                               |
|  +----------+ +----------+ +----------+                      |
|  | BINARY   | | FAILED   | | YARA     |                      |
|  | FINDINGS | | HARDENING| | MATCHES  |                      |
|  |    12    | |    5     | |    3     |                      |
|  +----------+ +----------+ +----------+                      |
|                                                               |
|  +----------------------------------------------------------+ |
|  | CHECKSEC RESULTS                                          | |
|  | Binary     | NX  | PIE | RELRO | Canary | FORTIFY | CFG | |
|  | data-proc  | ✗   | ✗   | ○     | ✗      | ○       | —   | |
|  | etl-daemon | ✓   | ✓   | ✓     | ✓      | ○       | —   | |
|  +----------------------------------------------------------+ |
|                                                               |
|  +-----------------------------+  +-------------------------+ |
|  | YARA MATCHES TABLE          |  | FINDINGS BY BINARY      | |
|  | Binary | Rule    | Severity |  |  [BAR CHART]            | |
|  | data.. | Hardco..| HIGH     |  |  data-processor: 9      | |
|  | data.. | Intern..| MEDIUM   |  |  etl-daemon: 3          | |
|  | data.. | UPXPa..| LOW      |  |                         | |
|  +-----------------------------+  +-------------------------+ |
+--------------------------------------------------------------+
```

### Visuals

#### V16.1 — Binary Findings Card
- **Type:** Card
- **Value:** `[Binary Findings]`
- **Format:** Integer, 48pt bold, purple accent

#### V16.2 — Failed Hardening Checks Card
- **Type:** Card
- **Value:** `[Failed Hardening Checks]`
- **Format:** Integer, 48pt bold, red conditional if > 3

#### V16.3 — YARA Matches Card
- **Type:** Card
- **Value:** `[YARA Matches]`
- **Format:** Integer, 48pt bold, orange conditional if > 0

#### V16.4 — checksec Results Table
- **Type:** Matrix
- **Rows:** Findings[file] (binary name)
- **Columns:** Split by hardening check name
- **Values:** Pass/Fail indicator
- **Filter:** Findings[target_type] = "binary" AND LEFT(Findings[rule_id], 7) = "BIN-chk"
- **Conditional formatting:** Cell background green (pass) / red (fail)

```dax
Checksec Pass Fail =
IF(COUNTROWS(Findings) > 0, "✗ FAIL", "✓ PASS")
```

#### V16.5 — YARA Matches Table
- **Type:** Table
- **Columns:** file (binary_name), rule_id, severity, message
- **Filter:** Findings[target_type] = "binary" AND LEFT(Findings[rule_id], 7) = "BIN-yar"
- **Sort:** severity descending
- **Conditional formatting:** severity column background

#### V16.6 — Findings by Binary Target
- **Type:** Clustered bar chart (horizontal)
- **Axis:** Findings[target_name]
- **Values:** Count of Findings
- **Filter:** Findings[target_type] = "binary"
- **Colors:** Severity-based stacking (critical, high, medium, low)
