# BI Domain — DAX Patterns

Domain knowledge for Power BI semantic modeling and DAX authoring.
Referenced by: client-work

---

## Data Modeling

- **Star schema**: fact tables + dimension tables, no wide flat tables
- **Naming**: `dim_[entity]`, `fact_[process]`, `bridge_[relationship]`
- **Date table**: always create a dedicated date dimension — never use auto date/time
- **Relationships**: avoid bi-directional unless the model explicitly requires it; document why when used

---

## DAX Patterns

### Measures
- Always use `VAR` for multi-step measures — never nest `CALCULATE` without reason
- Standard pattern:
  ```dax
  Measure Name =
  VAR result = CALCULATE(SUM(Table[Column]), Filter)
  RETURN result
  ```

### Time Intelligence
- Use `DATEADD`, `SAMEPERIODLASTYEAR` with the dedicated date table (never with auto date/time)
- MTD/QTD/YTD: use `TOTALMTD`, `TOTALQTD`, `TOTALYTD` — pass the date column from the date dimension
- Rolling periods: `DATESINPERIOD` with negative interval

### Row-Level Security
- Implement per client requirement: `USERPRINCIPALNAME()` against a security table
- Test with `Modeling → View As Role` for every defined role
- Document the security table structure and expected behavior in the handoff doc

### Context Issues
- Implicit context transition in calculated columns: always explicit `CALCULATE([Measure])`
- Filter propagation: use `TREATAS` when joining tables without a physical relationship
- `ALL` vs `ALLEXCEPT`: `ALL` removes all filters from a table; `ALLEXCEPT` removes all except named columns

---

## DAX Error Reference

| Error | Likely cause | Fix |
|---|---|---|
| "A function has been used in a True/False expression" | Filter arg is not boolean | `CALCULATE([M], Table[Col] = "x")` |
| "Circular dependency detected" | Measure references itself through chain | Trace the chain; use `VAR` to break the loop |
| "The column X does not exist" | Wrong table prefix or renamed column | Verify exact name in field list |
| "EARLIER cannot be used" | EARLIER outside row context | Replace with `VAR prev = [value]` pattern |
| Wrong totals / context issues | Implicit context transition | Wrap with explicit `CALCULATE([Measure])` |
| "Cannot convert value 'X' to type Integer" | Data type mismatch at join | Check both sides of relationship for identical types |

---

## Annotated DAX Patterns — Why They Work

### Pattern 1: VAR-before-CALCULATE (prevents circular evaluation)

When a measure uses CALCULATE inside itself, the outer filter context can interfere with nested aggregations. Using VAR to capture a scalar value BEFORE the outer CALCULATE applies is the correct way to compute a global baseline inside a filtered measure. Without the VAR, the inner CALCULATE re-evaluates inside the outer filter context, often producing wrong (circular) results.

```dax
Universities Above Avg =
VAR GlobalAvg = CALCULATE(AVERAGE(FactUniversity[Score]), ALL(FactUniversity))
RETURN
CALCULATE(
    COUNTROWS(FactUniversity),
    FactUniversity[Score] > GlobalAvg
)
```

Key point: `VAR GlobalAvg` captures the scalar value once, in global context (ALL removes filters). The outer CALCULATE then applies row-level filters without disturbing GlobalAvg.

---

### Pattern 2: ALL vs ALLSELECTED — decision guide

These two functions look similar but produce fundamentally different results in a report with slicers. ALL removes ALL filters from the table, giving a true global baseline regardless of any user selection. ALLSELECTED removes only the implicit filters from the current query context while keeping explicit slicer selections — it "respects the slicer."

```dax
-- True global benchmark (ignores all slicers)
Global Benchmark Score =
CALCULATE(AVERAGE(FactUniversity[Score]), ALL(FactUniversity))

-- Slicer-aware benchmark (filters to what user has selected)
Selected Benchmark Score =
CALCULATE(AVERAGE(FactUniversity[Score]), ALLSELECTED(FactUniversity))
```

Decision guide:
- Use `ALL` when: KPI card should always show the global total regardless of slicer
- Use `ALLSELECTED` when: benchmark should update as user filters (e.g., "average score for selected region")

---

### Pattern 3: AVERAGEX for composite expressions

When computing an average of a formula that combines multiple columns, AVERAGEX is the correct function. Using AVERAGE on separate columns and then combining them produces wrong results under filters because each AVERAGE evaluates independently. AVERAGEX evaluates the composite expression row-by-row and then averages the per-row results — which is the mathematically correct approach.

```dax
International Index =
AVERAGEX(
    FactUniversity,
    (FactUniversity[InternationalStudents] + FactUniversity[InternationalFaculty]) / 2
)
```

Wrong approach (produces different results under filters):

```dax
-- WRONG: each AVERAGE is independent
Bad International Index =
(AVERAGE(FactUniversity[InternationalStudents]) + AVERAGE(FactUniversity[InternationalFaculty])) / 2
```

---

### Pattern 4: Mean absolute deviation (ranking volatility)

For volatility or spread measures, AVERAGEX + ABS computes mean absolute deviation:

```dax
Ranking Volatility =
AVERAGEX(
    FactUniversity,
    ABS(FactUniversity[CurrentRank] - AVERAGE(FactUniversity[CurrentRank]))
)
```

---

## Concrete TMDL Measure Examples

### Quarter-over-Quarter with REMOVEFILTERS + DATEADD

```dax
Sales PQ =
VAR PreviousQuarterSales =
    CALCULATE(
        [Total Sales],
        REMOVEFILTERS(DimDate),
        DATEADD(DimDate[Date], -1, QUARTER)
    )
RETURN PreviousQuarterSales

Sales QoQ % =
DIVIDE(
    [Total Sales] - [Sales PQ],
    [Sales PQ]
)
```

Why REMOVEFILTERS: removes the current quarter filter from DimDate so DATEADD can navigate to the previous quarter cleanly. Without REMOVEFILTERS, the current quarter filter intersects with DATEADD, often returning blank.

---

### Conditional reference line: MEDIANX + KEEPFILTERS + SUMMARIZE + ALLSELECTED

For adding a median reference line to a bar chart that respects slicers:

```dax
Median Sales Reference =
MEDIANX(
    KEEPFILTERS(
        SUMMARIZE(
            ALLSELECTED(FactSales),
            FactSales[Category]
        )
    ),
    [Total Sales]
)
```

Why this combination: ALLSELECTED gets the slicer-filtered rows. SUMMARIZE groups by Category (one row per category). KEEPFILTERS preserves any additional filter context. MEDIANX then computes the median [Total Sales] across categories.

---

### Dynamic slicer label: CONCATENATEX + VALUES

```dax
Filter Label =
IF(
    ISFILTERED(DimProduct[Category]),
    CONCATENATEX(VALUES(DimProduct[Category]), DimProduct[Category], ", "),
    "All Categories"
)
```

---

### Calculated column pre-segmentation (reduces runtime overhead)

Pre-compute classification at load time as a calculated column rather than in runtime measures:

```dax
-- In TMDL as a calculated column on FactUniversity:
Ranking Tier =
IF(FactUniversity[Rank] <= 100, "Top 100",
IF(FactUniversity[Rank] <= 500, "Top 500", "Other"))
```

Use this for any segmentation that is expensive to compute at runtime and doesn't change per filter context.

---

## Power BI Toolchain

| Tool | Purpose | When to use |
|---|---|---|
| `pbir` CLI | Edit PBIR report JSON files from command line | Bulk report changes, CI automation |
| Tabular Editor | Semantic model scripting, Best Practice Analyzer (BPA), bulk measure editing | Model audits, batch DAX changes, BPA gate |
| DAX Studio | DAX query execution, Server Timings profiler, VertiPaq Analyzer | Performance debugging, measure validation |
| `pbi-tools` | PBIX/PBIT source control extraction, diff-friendly format conversion | Legacy .pbix projects not yet on PBIP |
| Fabric CLI (`fab`) | Workspace management, deployment pipelines, service operations | Fabric workspace automation, CI/CD |

---

## DAX Measure Output Template

When specifying or documenting a measure, use this format:

```
Name: [measure name, matching the TMDL declaration]
Business definition: [what this measures in plain business language — no DAX jargon]
DAX: [the measure expression]
Format string: [e.g., "$#,0.00" or "0.0%" or "#,0"]
Display folder: [e.g., "Revenue" or "Time Intelligence" or "KPIs"]
Description: [tooltip text visible to report consumers — one sentence]
Validation idea: [how to verify correctness — e.g., "spot-check against source system total for last full month"]
```

Example:

```
Name: Sales QoQ %
Business definition: Percentage change in total sales compared to the same quarter last year
DAX: DIVIDE([Total Sales] - [Sales PQ], [Sales PQ])
Format string: "0.0%"
Display folder: Revenue\Variance
Description: Quarter-over-quarter sales growth rate
Validation idea: Compare to finance team's QoQ report for Q1 FY2025 — should match within rounding
```
