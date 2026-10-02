# PBIR and TMDL Gotchas

Hand-edited `visual.json`, `page.json`, and `.tmdl` files hit a small set of recurring traps. The
PBIR JSON schema is permissive — Power BI Desktop's renderer is stricter than the schema, and
several of these fail **silently** (clean schema, wrong or blank render) rather than with an
error on open. Check each before declaring a change done.

All `scripts/...` paths below are relative to the power-platform mode's own directory:
`canonical/skills/domains/modes/power-platform/`.

---

## 1. `visualContainerObjects` placement

**Rule:** `visualContainerObjects` (holds `border`, `background`, `padding`, `title`) MUST be a
child of `visual`, NOT a top-level sibling.

```json
{
  "name": "...",
  "position": {...},
  "visual": {
    "visualType": "...",
    "objects": {...},
    "visualContainerObjects": {...},   // ← HERE
    "drillFilterOtherVisuals": true
  }
}
```

Top-level placement fails schema validation on `.pbip` open:
> Property 'visualContainerObjects' has not been defined and the schema does not allow additional properties.

---

## 2. Slicer shape — start minimal, expand from a proven example

**Rule:** The schema validator passes slicer shapes Power BI Desktop silently rejects (renders the
page blank). The minimal shape below is a **safe floor**, not a hard ceiling — properties beyond
it are not automatically fatal, but if a hand-authored slicer renders the page blank, strip back
to this floor and re-add one property at a time.

Safe-floor shape:
- `objects.data[].properties.mode` = `'Dropdown'`
- `objects.items[].properties.textSize` = a numeric `D` literal (NO `fontFamily`)
- `visualContainerObjects.title` — may set `show`, `text`, `fontColor`. NOT `fontFamily` or
  `textSize`.
- `query.queryState.Values.projections[]` with `"active": true`

**Confirmed working beyond the floor** (don't treat these as forbidden — a production slicer can
render cleanly with all of them):
- `objects.selection[].properties.singleSelect = false` (explicit multi-select; omitting it also
  defaults to multi-select)
- `objects.general[].properties.filter` — a pre-selected default value
- `objects.header[].properties.show = false` (hide the built-in header when using a container
  title instead)
- `objects.items[].properties.textSize = '11D'`
- `visualContainerObjects.border[].properties.radius = '4D'` (rounded corners work)

The earlier blanket rule ("no radius, omit singleSelect, omit general.filter, textSize must be
10D") was over-restrictive — none of those were ever the proven cause of a blank page. The
reliable failure mode is putting `fontFamily`/`textSize` on the **title**
(`visualContainerObjects.title`) or other styling properties Power BI doesn't emit there.

Path B (the static layout preview — see `visual-verification.md`) doesn't catch a silent
rejection, since the JSON is schema-clean. Only Path A (live render) surfaces it. Numeric columns
work fine in Dropdown mode.

---

## 3. `pivotTable` (matrix) requires `selector` on styling objects

**Rule:** Every styling object under a `pivotTable`'s `visual.objects.*` needs `"selector": {
"id": "default" }` as a sibling of `"properties"`. Without it, Power BI silently ignores the
explicit values and falls back to the active theme.

Applies to: `grid`, `columnHeaders`, `rowHeaders` (the first, styling entry), `values` (both
`backColorPrimary`/`Secondary`), `total`, `subTotals`.

`tableEx` does **not** have this requirement — its property overrides win against the theme
without selectors. This is `pivotTable`-specific.

Example — setting `values.backColorPrimary` without a selector gets silently overridden by the
theme's own `pivotTable.values.backColorPrimary`; adding `"selector": { "id": "default" }` makes
the override stick. `exec-quality-check.mjs` enforces this on `entries[0]`. Subsequent entries
(like a `showExpandCollapseButtons` toggle) are legitimately selector-less.

---

## 4. Matrix `+`/`-` drill icons need `showExpandCollapseButtons`

**Rule:** To show `+`/`-` drill icons next to matrix row headers, add a SECOND entry to
`objects.rowHeaders` with only `showExpandCollapseButtons: true`. The first entry holds default
styling (with selector). The second entry is a per-property override and does **not** need a
selector.

```json
"rowHeaders": [
  {
    "properties": { "fontFamily": ..., "backColor": {...} },
    "selector": { "id": "default" }
  },
  {
    "properties": {
      "showExpandCollapseButtons": {
        "expr": { "Literal": { "Value": "true" } }
      }
    }
  }
]
```

`expansionStates.isCollapsed: true` controls the INITIAL collapsed state. `showExpandCollapseButtons:
true` makes the click-icons visible. These are independent.

---

## 5. `visualGroup` children use RELATIVE positions

**Rule:** A `visual.json` with `parentGroupName: "<group>"` has its `position.x`/`position.y`
interpreted **relative to the parent group's origin**, NOT as absolute canvas coordinates.

Workflow when authoring groups:
1. Decide the group's bounding box (`groupX`, `groupY`, `groupW`, `groupH`).
2. Create the group with `visualGroup: { displayName, groupMode: "ScaleMode" }` and no `visual`
   key.
3. For each child: set `parentGroupName: "<group>"` AND rewrite `position.x = absoluteX - groupX`,
   `position.y = absoluteY - groupY`.
4. Child width/height stay unchanged.

Minimum group shape:

```json
{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.5.0/schema.json",
  "name": "v_group_r0",
  "position": { "x": 384, "y": 80, "z": 100, "height": 130, "width": 851, "tabOrder": 0 },
  "visualGroup": { "displayName": "Row r0", "groupMode": "ScaleMode" }
}
```

Symptom of using absolute coordinates for children: opaque white rectangles where the groups sit,
plus children appearing at wrong offsets.

### 5b. `visualContainerObjects.title` sizes text with `fontSize`, NOT `textSize`

**Rule:** the container title object takes `fontSize`. `textSize` is valid in some OTHER objects
(e.g. `pivotTable`'s `grid.textSize`) but on a title it hard-fails the `.pbip` open with:

> An additional property 'textSize' was included in the /visual/visualContainerObjects/title/0/properties property

Unlike the silent-fallback gotchas above, this one is LOUD — Desktop refuses the file outright.

---

## 6. Textbox vertical centering

**Rule:** Textboxes default to top-aligned. To center vertically inside the container, add
`verticalAlignment` as a sibling of `paragraphs` inside `objects.general[0].properties`:

```json
"visual": {
  "visualType": "textbox",
  "objects": {
    "general": [
      {
        "properties": {
          "verticalAlignment": { "expr": { "Literal": { "Value": "'Middle'" } } },
          "paragraphs": [...]
        }
      }
    ]
  }
}
```

Valid values: `'Top'` (default), `'Middle'`, `'Bottom'`. Single-quotes inside the Literal Value,
matching the convention for other Power BI string literals.

Apply whenever the container height is taller than the text content (title cards in card rows,
body textboxes, header/footer labels).

---

## 7. Visual-level filters always hidden

**Rule:** Every entry in a visual's `filterConfig.filters[]` MUST have `isHiddenInViewMode: true`.
No exceptions.

```json
"filterConfig": {
  "filters": [
    {
      "name": "...",
      "field": {...},
      "type": "Categorical",
      "isHiddenInViewMode": true     ← REQUIRED
    }
  ]
}
```

User-facing filters belong on the page (`page.json.filterConfig`), the report
(`report.json.filterConfig`), or an on-canvas slicer visual. "Filters on this visual" is a
developer-side surface only.

**Critical:** filter `name` values MUST be 20-char lowercase hex (Power BI Desktop's internal
UUID format). Readable names cause Power BI to silently reject the filter and render the visual
blank.

Two-step auto-fix workflow:

```bash
node scripts/hide-visual-filters.mjs "<...>.Report"       # hide existing visible entries
node scripts/preemptive-hide-fields.mjs "<...>.Report"    # pre-create hidden entries for bound fields
```

Both idempotent. Run after every Power BI Desktop save session. `exec-quality-check.mjs` fails on
any visible visual-level filter.

Two filter sources to be aware of:
1. **Auto-bound field filters** — Power BI Desktop emits one `Categorical` entry per bound column
   when fields are added to a `tableEx`, matrix, or chart's data roles.
2. **Deliberate developer filters** — pinning a card to one slice. A layout choice, not a user
   lever.

### 7b. Hand-authored TopN filters — one unknown property = EMPTY REPORT SHELL

An invalid property in a `filterConfig` entry doesn't break just that visual — **Power BI Desktop
opens the whole report as an empty shell**: blank canvas, no page tabs, empty Data pane, and (when
launched off-screen for a Path A capture) no visible error dialog. Every page captures as a
uniform blank.

Rules for hand-authoring a `"type": "TopN"` filter:
- **Mirror a Desktop-authored example structurally.** Copy one from a working report (grep for
  `'"TopN"'` under `<Report>/definition/pages`) and swap only entities/properties/Top count.
- The count lives ONLY in `filter.From[].Expression.Subquery.Query.Top` — there is **no**
  top-level `howMany` property, even though it looks like it should exist.
- Include `"howCreated": "User"` and `"isHiddenInViewMode": true`; `name` = 20-char lowercase hex.
- A Path A capture that comes back as a uniform blank after a filter edit means a *report-level*
  parse failure — bisect `filterConfig` edits first, before suspecting TMDL.

`validate-visual-json.mjs` passes this case (the schema is permissive) — only a live Desktop load
catches it.

---

## 8. `tableEx` auto-fit doesn't equalize column widths

**Rule:** Setting `objects.general.autoSizeColumnWidth = false` on a `tableEx` does NOT make Power
BI distribute columns evenly across the visual width. Even with auto-fit off, Power BI sizes each
column to its content, producing a horizontal scrollbar whenever long text columns exceed the
visual's display width.

**Symptom:** a bottom scroll bar on a `tableEx` even after toggling auto-fit off in JSON. Long
left-side columns hog space; right-side columns disappear off-canvas.

**Workarounds (pick one):**
1. **Drop columns to fit.** Keep 4–6 essential columns; move secondary ones to a tooltip or drill
   page. Usually the right answer.
2. **Specify explicit `columnWidth` per projection.** Heavy — must measure and tune each width;
   brittle when data changes.
3. **Word-wrap long text values** via `objects.values[0].properties.wordWrap = true`. Grows row
   height instead of column width, but Power BI still picks column widths from the longest
   single-line content within the column.
4. **Widen the visual.** No-op if the table already occupies the available width.

**What didn't help (tried and verified failures):** `general.autoSizeColumnWidth = false` alone;
`values.wordWrap = true` alone; changing `columnHeaders.wordWrap` (headers wrap, columns stay
content-sized).

See also the `tableEx` total-row hiding pattern in `report-visual-json.md`, which is similarly
counterintuitive.

---

## 9. `azureMap` bubbles need a conditional `fillColor` to color by category

**Rule:** On the Azure Map visual (`visualType: "azureMap"`), binding a field to the `Legend` role
shows a legend and is necessary, but does **NOT** give each category a distinct bubble color on
its own — every bubble renders in the default blue. To color bubbles by category, hand-author a
**second `bubbleLayer` entry** whose `fillColor` is a `Conditional` expression mapping each
category value to a hex.

Role layout that works:
- `Category` — the point identity column.
- `Latitude` / `Longitude` — the lat/lon columns, each wrapped in a `Min` aggregation
  (`"Function": 4`). (`X`/`Y` mirror them with `Avg`, `"Function": 1`, for the auto-zoom center.)
- `Legend` — the category column you want colored.
- `Tooltips` — extra columns for hover.

`bubbleLayer` takes **two** array entries: layer settings (`show`, `clusteringEnabled: false` —
clustering hides individual points — `markerType: 'image'`, `bubbleRadius`), then the per-category
`fillColor` as a `Conditional` with one `Cases[]` entry per category:

```json
"bubbleLayer": [
  {
    "properties": {
      "show":              { "expr": { "Literal": { "Value": "true" } } },
      "clusteringEnabled": { "expr": { "Literal": { "Value": "false" } } },
      "markerType":        { "expr": { "Literal": { "Value": "'image'" } } },
      "bubbleRadius":      { "expr": { "Literal": { "Value": "13L" } } }
    }
  },
  {
    "properties": {
      "fillColor": {
        "solid": { "color": { "expr": { "Conditional": { "Cases": [
          {
            "Condition": { "Comparison": {
              "ComparisonKind": 0,
              "Left":  { "Aggregation": { "Expression": { "Column": {
                "Expression": { "SourceRef": { "Entity": "<your entity>" } },
                "Property": "<category column>" } }, "Function": 3 } },
              "Right": { "Literal": { "Value": "'<category value>'" } }
            } },
            "Value": { "Literal": { "Value": "'#6B007B'" } }
          }
          // … one Case per category value …
        ] } } } }
      }
    }
  }
]
```

Notes:
- The `Left` side aggregates the category column with `"Function": 3` (Min) — matching how Power
  BI Desktop emits the conditional when "Format by → field value" is set on the bubble color.
- `ComparisonKind: 0` is equality; the literal on `Right` is single-quoted.
- This is verbose — one `Cases` entry per category. If the category set is large and stable,
  generate the `Cases[]` array programmatically rather than by hand.

Path B can't catch this — it draws the map as a placeholder; only Path A (or a published report)
shows the real bubble colors.

---

## 10. Bookmark visibility — `display.mode` is a strict enum; "visible" does not exist

**Rule:** In a `*.bookmark.json`, `singleVisual.display.mode` accepts ONLY `maximize | spotlight |
elevation | hidden`. There is no `"visible"` — writing it makes Power BI Desktop reject the
definition and open to a BLANK report with **no page tabs** (looks like a hang/timing issue; it
isn't — check for schema errors first).

To express visibility in a show/hide toggle bookmark (the Desktop-emitted shape):

```json
"visualContainers": {
  "v_shown":  { "singleVisual": { "visualType": "pivotTable", "objects": {} } },
  "v_hidden": { "singleVisual": { "visualType": "pivotTable", "objects": {}, "display": { "mode": "hidden" } } }
}
```

- **Visible** = the `singleVisual` block present (visualType + objects) with NO `display` key.
- An **empty container `{}` does NOT restore visibility** — it hides whichever visual is
  referenced and never un-hides the other.
- Definition-level `"isHidden": true` on a `visual.json` sets the default state; a bookmark with
  the shapes above toggles it correctly.
- `options.targetVisualNames` must list every visual the bookmark controls; `suppressData: true`
  keeps filters/slicers untouched.

---

## 11. `actionButton` — label and styling use STATE-OBJECT pairs, not single default entries

**Rule:** `actionButton`'s `objects.text` / `fill` / `outline` follow the theme's state model: a
**selectorless entry holding only `show`**, then one entry per state with `selector: {"id":
"default"}` (plus optional `"hover"`, `"selected"`, `"disabled"`). Packing `show` + `text` + fonts
into one default-selector entry gets the whole block silently dropped → an empty, unstyled button.

```json
"text": [
  { "properties": { "show": {...true} } },
  { "properties": { "text": {...}, "fontColor": {...}, "fontSize": {...} }, "selector": { "id": "default" } }
]
```

- Do NOT use `visualContainerObjects.title` as the button label — it renders as a caption ABOVE
  the button face (production buttons set title `show: false` while keeping a `text` value for
  the tooltip/alt name).
- Size buttons to their label: default ~10pt Segoe needs roughly 6.2px/char + 24px padding.

---

## 12. `cardVisual` (new card) silently rejects hand-authored single-measure bindings in some shapes

**Rule:** A hand-authored `cardVisual` bound to one (especially text) measure can render as an
empty white skeleton with ALL formatting objects ignored — the binding is rejected wholesale, not
partially. The legacy `card` visual (`queryState.Values`, `objects.labels`/`categoryLabels`)
accepts the same binding reliably and renders transparent-on-band chrome fine. For simple dynamic
text (period stamps, refresh stamps), prefer the legacy `card`.

---

## 13. Verification is per-render-state: ANY later geometry/format tweak voids it

**Process rule:** "verified live" attaches to the exact JSON that was rendered. If width,
position, or font is nudged afterward — even trivially — the verification is void; re-render
before handoff. Text-bearing containers are the highest-risk class for this, since
truncation/wrap is width-sensitive at the pixel level.

---

## 14. Theme wildcard `color` silently kills visual-level Conditional formatting

**Rule:** A custom theme whose `visualStyles` `*` → `*` → `*` wildcard entry sets `color`
OVERRIDES visual-level `Conditional` color expressions — the visual renders the theme color even
when the condition matches. The wildcard entry should set `fontFamily` only; default text color
belongs in the theme's `foreground` / `firstLevelElements`.

**Symptom:** conditional formatting (per-category accent bars, sentiment fills) renders in the
theme's flat color; the visual's JSON looks correct; validators pass. Only a live A/B render (same
visual, theme with vs. without the wildcard color) exposes it.

---

## 15. NEVER hide the visual header on data visuals — it kills Export data in the Service

**Rule:** `visualContainerObjects.visualHeader` `show: false` removes the entire on-hover header
in the Service reading view — including the "⋯ More options" menu, which is the ONLY path report
consumers have to **Export data**. On any data-bearing visual (pivotTable, tableEx, charts,
decompositionTreeVisual, data-bound custom visuals), do not set `show: false`. In almost all cases
the header stays ON; de-noise it by suppressing individual icons instead, always keeping
`showOptionsMenu: true`:

```json
"visualHeader": [
  {
    "properties": {
      "show":                          { "expr": { "Literal": { "Value": "true"  } } },
      "showOptionsMenu":               { "expr": { "Literal": { "Value": "true"  } } },
      "showFocusModeButton":           { "expr": { "Literal": { "Value": "true"  } } },
      "showDrillRoleSelector":         { "expr": { "Literal": { "Value": "false" } } },
      "showDrillUpButton":             { "expr": { "Literal": { "Value": "false" } } },
      "showDrillToggleButton":         { "expr": { "Literal": { "Value": "false" } } },
      "showDrillDownLevelButton":      { "expr": { "Literal": { "Value": "false" } } },
      "showDrillDownExpandButton":     { "expr": { "Literal": { "Value": "false" } } },
      "showPinButton":                 { "expr": { "Literal": { "Value": "false" } } },
      "showSmartNarrativeButton":      { "expr": { "Literal": { "Value": "false" } } },
      "showSeeDataLayoutToggleButton": { "expr": { "Literal": { "Value": "false" } } },
      "showTooltipButton":             { "expr": { "Literal": { "Value": "false" } } }
    }
  }
]
```

Notes:
- Desktop **edit mode always shows headers regardless of this setting**, so the regression is
  invisible while authoring — it only bites the published report. Neither Path A nor Path B
  catches it (the header only exists on hover in reading view).
- Export also requires report-level `settings.exportDataMode` to allow it (`AllowSummarized` is a
  common standard) — check both when export is "missing", but the hidden header is the usual
  culprit.
- Custom visuals additionally need `supportsExport: true` in `capabilities.json`, or Export data
  stays unavailable even with the header visible.
- The carve-out: decorative visuals (textbox, image, shape, actionButton, header-chrome/period
  cards, refresh-stamp cards) and slicers may keep hidden headers — there is nothing meaningful to
  export and the hover chrome is pure noise there.

---

## 16. Theme retrofit: hexes inside `Conditional` expressions are design, not theme candidates

**Rule:** When applying a brand theme to an existing report and remapping literal colors to
`ThemeDataColor`, ONLY remap plain `Literal` fills/font colors. Hex literals inside `Conditional`
`Cases[].Value` entries encode the report author's conditional logic (per-bucket colors,
sentiment thresholds) — remapping them flattens every branch to one theme color.

---

## 17. New StaticResources must be registered in `report.json`'s `resourcePackages`

**Rule:** Dropping a PNG/JSON into `StaticResources/RegisteredResources/` is not enough — the file
must also appear as an item under `report.json` → `resourcePackages` → `RegisteredResources`. An
unregistered image renders **silently blank** (no error, no placeholder); an unregistered theme is
ignored.

```json
{ "name": "my_asset.png", "path": "my_asset.png", "type": "Image" }
```

---

## TMDL and semantic-model gotchas

`.tmdl` files live under `<...>.SemanticModel/definition/`. They define tables, measures,
columns, relationships, and the model itself. These are the recurring traps that block a `.pbip`
from loading, with symptoms Power BI Desktop surfaces poorly. (TMDL's base syntax rules —
tabs-not-spaces indentation, `/// Description` annotations, measure placement — live in this
domain's `tmdl-authoring.md`; these are the deeper, burn-case-level traps.)

### T1. NO standalone `/* */` block comments

**Rule:** the TMDL parser rejects standalone `/* ... */` block comments between objects. The
parser error is `InvalidLineType: Unexpected line type: Other!` and Power BI Desktop refuses to
load the entire `.pbip`. The user sees the "Add data to your report" welcome screen — the actual
error only surfaces by clicking "Issues were found" in the file-open flow.

**What IS allowed:**
- `/// description text` — attaches as a description to the IMMEDIATELY following object
  (measure/column/table). One or more lines, no blank line between the `///` block and the target.
- `/* ... */` — ONLY inside DAX expression bodies. Treated as a DAX comment, not TMDL syntax.

**What ISN'T allowed:** standalone `/* ... */` block comments between objects; `// single-line`
comments anywhere in the TMDL body; `#` comments anywhere.

**How to apply:** when generating measures/columns, skip section-header comments entirely. If you
must document, use `///` immediately above the target object.

### T2. Auto Date/Time removal needs `variation` cleanup

**Rule:** disabling Auto Date/Time requires FIVE coordinated edits, not just one. Missing step 3
silently breaks model load.

1. `model.tmdl` — set `annotation __PBI_TimeIntelligenceEnabled = 0` (down from `1`).
2. `model.tmdl` — remove every `ref table LocalDateTable_*` and `ref table DateTableTemplate_*`
   line.
3. **For each source-of-truth date column** with auto-date wiring, DELETE the inline `variation`
   block:
   ```
   variation Variation
       isDefault
       relationship: <guid>
       defaultHierarchy: LocalDateTable_<guid>.'Date Hierarchy'
   ```
4. `relationships.tmdl` — delete the relationships that linked source date columns to the deleted
   LocalDateTables.
5. `tables/` — delete `LocalDateTable_*.tmdl` + `DateTableTemplate_*.tmdl` files.

**Symptom of missing step 3:** Power BI Desktop opens to the "Add data to your report" welcome
screen with no error popup — Path A would show the window title stuck at `Untitled - Power BI
Desktop`. The date columns themselves stay, but their `variation` blocks point to deleted tables,
and the parser fails silently.

**How to apply:** after deleting `LocalDateTable`/`DateTableTemplate` tmdl files, grep
`definition/tables/` for `LocalDateTable_` and `DateTableTemplate_` — any hit inside a `variation`
block needs the whole 3-line block removed.

### T3. PowerShell file editing — UTF-8 NO BOM, always explicit

**Rule:** when bulk-editing `.tmdl` from PowerShell:
- ALWAYS read with explicit UTF-8: `Get-Content -Encoding UTF8` or
  `[System.IO.File]::ReadAllText($p, [System.Text.UTF8Encoding]::new($false))`
- ALWAYS write UTF-8 no-BOM:
  `[System.IO.File]::WriteAllText($p, $text, (New-Object System.Text.UTF8Encoding $false))`

**Why:** default `Get-Content` uses the system codepage (Windows-1252 on en-US), silently mangling
non-ASCII characters (an en-dash or a checkmark glyph turns into mojibake). Default `Out-File` /
`Set-Content` / `WriteAllLines` use UTF-16 LE with a BOM — TMDL files should be UTF-8 NO BOM
throughout a repo; adding a BOM doesn't crash Power BI but breaks encoding consistency and shows
up in diffs.

**Counterintuitive constructor:** `[System.Text.UTF8Encoding]::new($true)` means "with BOM".
`$false` = no BOM. Easy to flip by accident.

**Verify after each write:**
```powershell
[System.IO.File]::ReadAllBytes($p)[0..2]
# First 3 bytes should NOT be 0xEF 0xBB 0xBF
```

### T4. Where to look when a `.pbip` fails to load

Power BI Desktop opens the welcome screen ("Add data to your report") instead of the report when
the model fails to parse. Diagnose in this order:

1. **TMDL Format Error popup** — click "Issues were found" on the file-open flow. Names the file
   and line.
2. **`model.tmdl`** — `ref table` lines pointing to deleted tables, or annotations with wrong
   values.
3. **`tables/*.tmdl`** — orphan `variation` blocks (T2), references to deleted measures inside DAX
   bodies, standalone `/* */` comments (T1).
4. **`relationships.tmdl`** — relationships referencing deleted tables/columns.
5. **`expressions.tmdl`** — broken parameter expressions.
6. **`cultures/en-US.tmdl`** — usually tolerant of orphan refs to deleted objects (it's metadata),
   but worth a grep if other diagnostics come up clean.

**Path A as a smoke test:** when the title-gate clears in under 60s and the window title shows the
report name, the model parsed cleanly. If it stays `Untitled - Power BI Desktop`, the model didn't
load.

---

## `visualType` taxonomy (for the layout-preview renderer)

How `scripts/preview-layout.mjs` (Path B — see `visual-verification.md`) renders each
`visual.visualType` value. Match is case-insensitive; pattern matching falls through in the order
shown.

| `visualType` (regex) | Rendered as |
|---|---|
| `tableEx` / `pivotTable` / `matrix` | Striped grid: header row with column-name cells (from bound fields), placeholder body rows |
| `card` / `cardVisual` | Soft background, big-number placeholder, centered, in the active brand profile's accent color |
| `slicer` / `advancedSlicer` | Bordered box, label from first bound field, a chevron |
| `azureMap` / `shapeMap` / `filledMap` / `map` | Diagonal striped pattern, "MAP" centered in monospace |
| `image` | Dashed grey border, "IMG" centered in monospace, white background |
| `shape` | Solid fill with rounded corners |
| `*chart` / `*column` / `*bar` / `*line` / `*area` / `*pie` / `*donut` / `*scatter` / `*combo` / `*funnel` / `*gauge` / `*kpi` / `*treemap` | Y/X axis lines, stepped placeholder bars, cycling through the active brand profile's primary/secondary/tertiary series colors (`palette.primary` entries in order) |
| Custom/organizational visual (a GUID/hash embedded in the `visualType` string) | Detected FIRST, before the stock patterns above — a custom visual's name often contains a stock-sounding substring ("scatter", "slicer", "map"), which would otherwise hijack it into a misleading stock mock. Renders as an explicit "custom visual — not rendered in Path B" badge with the type string. |
| anything else | Soft background, raw `visualType` string shown verbatim |

Custom visuals come through with their pbiviz `name` as the `visualType` and render per the
custom-visual branch above — the chip displays the name verbatim.

Adjusting the taxonomy: add a regex branch to `renderFiller()` in `scripts/preview-layout.mjs`,
the matching CSS to `templates/preview.html.tmpl`, and a row to this table. The renderer is
intentionally a wireframe, not a faithful rendering — small visual cues (a striped pattern, a
chevron, an axis line) are enough for "is the right kind of visual in the right place" without the
engineering cost of a real render.
