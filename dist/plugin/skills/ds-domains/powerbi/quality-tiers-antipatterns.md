# Quality Bar and Anti-Patterns

How to recognize a high-quality Power BI artifact, and what to flag back to the user when a
low-quality pattern shows up in the working repo.

## Five anti-patterns to flag on detection

When any of these appear in the user's working repo, **say so before continuing**. Recommend the
right structure first; only mirror the bad pattern if the user explicitly says to just match the
existing structure.

### 1. Inline measures on fact tables

**Smell:** a fact table TMDL file (e.g. `tables/POS.tmdl`) contains `measure '...' = ...` blocks.

**Why bad:** discoverability — users hunt across many tables to find measures. Hard to share
across reports. Can't apply `excludeFromModelRefresh` to a fact table, so refreshes try to
re-load source data unnecessarily.

**Right pattern:** all measures in a dedicated `Measures Table` with `excludeFromModelRefresh`.
Reference fact-table columns from there.

**Example:** a fact table with inline measures vs. a dedicated Measures Table doing it right —
both are the same underlying mechanism; cite whatever example exists in the current repo when
flagging this.

### 2. Raw source column names surfaced to users

**Smell:** the field list shows names like `IMF_Record_ID`, `ConsumerGTIN`, `BRAND_DESC_RAW`,
`Sales_CUR` — source-system naming leaking straight through.

**Why bad:** confusing for end users. Brittle — when the source schema changes, every report
visual that references the raw name breaks.

**Right pattern:** friendly column names at the column level (`Request Number`, `Consumer GTIN`,
`Brand Description`, `$ Sales`). Hide raw columns with `isHidden`. Surface only curated names.

```tmdl
column 'Sales_CUR'
    dataType: double
    isHidden                          ← hide raw
    summarizeBy: none
    sourceColumn: SCANNED_RETAIL_DOLLARS_CUR

column '$ Sales'                      ← friendly alias
    dataType: double
    formatString: \$#,0;(\$#,0);\$#,0
    summarizeBy: sum
    sourceColumn: SCANNED_RETAIL_DOLLARS_CUR
```

(In practice, keep just one column with a friendly name and the raw `sourceColumn` reference.
Don't duplicate.)

### 3. Bidirectional cross-filter on every dimension-to-fact relationship

**Smell:** multiple relationships in `relationships.tmdl` with `crossFilteringBehavior:
bothDirections`, especially when one dimension links to multiple facts.

**Why bad:** causes ambiguous filter context. Power BI may pick a different evaluation path than
expected; measures can return wrong values silently.

**Right pattern:** default to many-to-one single-direction. Use bidirectional sparingly —
typically one relationship per benchmark/share table where it's semantically required. If a
single calculation needs bidirectional behavior, use `CROSSFILTER()` inside the measure instead
of changing the relationship globally.

```dax
$ Sales (Benchmark) =
    CALCULATE(
        [$ Sales],
        CROSSFILTER('Brand Sales Detail'[commodity], 'Commodity Benchmark'[commodity], BOTH)
    )
```

A dimension fanned out bidirectionally to several fact tables is resolved by picking one fact as
primary and leaving the others single-direction.

### 4. Legacy `.bim` JSON model format

**Smell:** the project uses `<ReportName>.bim` (a single big JSON file) instead of TMDL — a PBIP
folder with `Model.bim` instead of a `definition/` subfolder.

**Why bad:** no source-control benefits — every change shows up as a giant JSON diff. No
DevMode capabilities. A pre-April-2024 format Microsoft has moved away from.

**Right pattern:** convert to TMDL. In Power BI Desktop, open the `.pbip` and resave — Desktop
auto-converts to the modern `definition/` folder structure. Test thoroughly afterward; some
legacy `.bim` features (older M source dialects, deprecated annotations) may need manual cleanup.

### 5. No DAX defensive coding

**Smell:** measures that compute change percentages without `DIVIDE` guards and without outlier
suppression.

```dax
-- BAD
Sales % Change = (SUM(POS[Sales]) - SUM(POS[Sales LY])) / SUM(POS[Sales LY])
```

**Why bad:** `#DIV/0!` errors on rows with zero LY; nonsensical 4000% spikes from new-item
launches make charts unreadable.

**Right pattern:**

```dax
-- GOOD
Sales % Change =
    VAR _cur = SUM(POS[Sales])
    VAR _ly = SUM(POS[Sales LY])
    VAR _change = DIVIDE(_cur - _ly, _ly)
    RETURN
        IF(ABS(_change) > 1, BLANK(), _change)
```

`DIVIDE()` returns `BLANK()` on a zero divisor. The `IF` blanks extreme outliers (beyond ±100%).
See `dax-patterns.md` for more defensive-DAX patterns.

## Quality bar quick check

Before delivering work, run through this:

- [ ] All measures in `Measures Table`, none inline on fact tables.
- [ ] Friendly column names exposed; raw source names hidden.
- [ ] `lineageTag` UUID on every column and measure, including new ones.
- [ ] `formatString` on every numeric/percentage/date measure.
- [ ] `DIVIDE` guards on every percent-change measure; outlier suppression where applicable.
- [ ] Star schema; bidirectional cross-filter only where justified, max one per pair.
- [ ] PBIP TMDL format, not legacy `.bim`.
- [ ] `definition.pbism` not hand-edited (Power BI regenerates it on save).
- [ ] The active brand profile's theme applied (`report.json.themeCollection.baseTheme` points
      at it — see `brand-profile.md`).
- [ ] Page chrome conventions followed: logo, refresh indicator, footer methodology positioned
      per the active brand profile's `page_chrome` (see `report-visual-json.md`).
- [ ] Custom visuals (if any) use `host.colorPalette` for theme awareness (see
      `custom-visuals.md`).
- [ ] Typography matches the active brand profile's `typography.font_family` throughout (set in
      the theme; override per-visual only when needed).
- [ ] No ad-hoc accent-color substitutions for default positive/negative coloring — sentiment
      coloring follows the active brand profile's `palette.accent.sentiment_policy`, not a color
      picked in the moment.

## Visual.json preflight (after any layout edit)

Run before invoking the visual-verification tooling (`visual-verification.md`) or surfacing
changes to the operator/reviewer. These catch the regressions that keep recurring:

- [ ] **No visual bottom exceeds the body envelope's max y** (overlaps the footer band). See the
      page-layout-grid convention in `report-visual-json.md`; programmatic check in
      `scripts/exec-quality-check.mjs`.
- [ ] **No visual right edge exceeds the right margin**, except a deliberately wider chrome
      element like a refresh indicator.
- [ ] **Every `image` visual declares `padding=0` on all four sides** under
      `visualContainerObjects.padding`. Power BI Desktop's default ~12px image padding makes
      logos look indented.
- [ ] **Every `pivotTable` styling object has `selector: { id: "default" }`.** Without it, Power
      BI silently falls back to theme. `tableEx` is exempt. (`pbir-gotchas.md` #3.)
- [ ] **Card height fits typical data height + small headroom.** Not the full body envelope.
      Empty space below the last data row reads as broken.
- [ ] **Repeated chrome visuals (`v_logo`, `v_title`, `v_refresh`, `v_footer_bar`) match across
      all pages.** Run `scripts/check-page-chrome-drift.mjs` to confirm position, schema, and
      property parity.
- [ ] **`general.layout` on `pivotTable` matches the intended drill model.** `Compact` = `+`/`−`
      icons in published view. `Tabular` = no drill, always expanded. Setting `Tabular` and then
      asking why there are no drill icons is the canonical mistake.
- [ ] **Container background contrasts with the page background.** A container tinted the same
      as the page is invisible — either change the container or add a strong border.
- [ ] **Every visual-level filter has `isHiddenInViewMode: true`.** No exceptions. Users
      interact with filters at the page or report level via the Filter pane, or via an on-canvas
      slicer visual — never a visible visual-level filter. `exec-quality-check.mjs` fails on any
      visible one. (`pbir-gotchas.md` #7.)

If any item fails, fix BEFORE a Path A capture (see `visual-verification.md`) — Path A is
expensive (~20-30s per page); use it to verify the *final* state, not to discover preflight
issues.

## Flagging language for the user

When an anti-pattern is detected, surface it clearly. Sample phrasings — generalize the specific
nouns to whatever the actual working repo contains:

- *"This file has measures inline on the fact table — that pattern is hard to maintain. Want me
  to set up a `Measures Table` and migrate them first, or just add this measure to the existing
  structure?"*
- *"`IMF_Record_ID` is a raw source column name. Convention is to alias it to something like
  `Request Number` and hide the raw. Want me to do that as part of this change?"*
- *"This project is on legacy `.bim` JSON format. Modern PBIP uses TMDL — much better for source
  control. Want me to convert before adding new measures?"*
- *"This % change measure has no `DIVIDE` guard. New-item launches will produce 4000% spikes that
  wreck the charts. I'll add the guard and outlier suppression unless you'd rather match the
  existing measure exactly."*

Then proceed based on the user's choice. Don't silently mirror a flagged anti-pattern without
asking first.
