# Report / Page / Visual JSON Authoring

The report side of a PBIP project — the JSON files Power BI Desktop reads to render pages,
visuals, filters, and bookmarks. This file covers JSON-**authoring patterns**; for the
structural file-layout overview (what lives where, the `.pbip`/`.pbir`/`.pbism` entry points),
see this domain's `pbip-format.md`. For the dense burn-case list of traps in these files, see
`pbir-gotchas.md` — this file cross-references rather than duplicates those.

Read `brand-profile.md` first if any of this touches theme color.

## Folder layout

```
<ReportName>.Report/
├── definition.pbir                                         ← report manifest
├── StaticResources/
│   ├── SharedResources/BaseThemes/<theme>.json             ← theme JSON(s)
│   └── RegisteredResources/<image>.png                     ← embedded images
└── definition/
    ├── report.json                                         ← top-level config
    ├── pages/
    │   ├── pages.json                                      ← page order, active page
    │   └── <page-UUID>/
    │       ├── page.json                                   ← page config + filters
    │       └── visuals/
    │           └── <visual-UUID>/
    │               └── visual.json                         ← per-visual config
    ├── bookmarks/
    │   ├── bookmarks.json                                  ← bookmark manifest
    │   └── <bookmark-UUID>.bookmark.json                   ← exploration state
    └── CustomVisuals/                                      ← embedded .pbiviz packages
        └── <visual-name>/
```

UUIDs are 20-hex-character lowercase strings (Power BI's internal format), not standard UUID-v4.

## `report.json`

Top-level config. Notable sections:

```json
{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.1.0/schema.json",
  "themeCollection": {
    "baseTheme": {
      "name": "<active brand profile's theme name>",
      "version": "1.0.0",
      "type": 1
    }
  },
  "settings": {
    "useNewFilterPaneExperience": true
  },
  "resourcePackages": [
    {
      "name": "RegisteredResources",
      "type": 1,
      "items": [
        {
          "name": "<logo file name>",
          "path": "<logo file name>",
          "type": "Image"
        }
      ]
    }
  ]
}
```

- **`themeCollection.baseTheme`** — references the theme JSON in
  `StaticResources/SharedResources/BaseThemes/`. Point this at the active brand profile's
  `theme_file` (see `brand-profile.md`).
- **`resourcePackages`** — declares embedded images. Reference these from `image` visuals via
  `ResourcePackageItem`. Every registered item must also physically exist under
  `StaticResources/RegisteredResources/` — see `pbir-gotchas.md` #17 for what happens when it
  doesn't.
- **`reportVersionAtImport`** — schema version per artifact type (visual: 2.5.0, report: 3.1.0).
  Power BI manages these; don't hand-edit.

## `pages/pages.json`

```json
{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json",
  "pageOrder": [
    "4f4dcef64806020a36bc",
    "cdfdb57fd60eee9dc9a5"
  ],
  "activePageName": "4f4dcef64806020a36bc"
}
```

Order here = order in the page tab strip. `activePageName` = page that opens by default.

## `pages/<UUID>/page.json`

```json
{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.0.0/schema.json",
  "name": "<UUID>",
  "displayName": "KPI Overview",
  "displayOption": "FitToPage",
  "height": 720,
  "width": 1280,
  "filterConfig": {
    "filters": [
      {
        "name": "<UUID>",
        "displayName": "Region",
        "ordinal": 0,
        "field": {
          "Column": {
            "Expression": { "SourceRef": { "Entity": "Sales Detail" } },
            "Property": "Region"
          }
        },
        "type": "Categorical",
        "howCreated": "User"
      }
    ],
    "filterSortOrder": "Custom"
  }
}
```

Patterns:

- **`displayOption: "FitToPage"`** — responsive, scales with viewport. Use this; avoid `"Actual
  Size"` unless a pixel-perfect layout is required.
- **Default size: 1280×720** is the common exec-report canvas (see the grid convention below);
  taller canvases are used for scroll-style dashboards.
- **Page-level filters cascade** to all visuals on the page. Set common dimensions here (region,
  period, business unit).
- **`filterSortOrder: "Custom"`** + `ordinal` per filter controls the left-rail order in view mode.
- **Background image**, if used, is registered in `RegisteredResources` and referenced the same
  way a visual's image would be — used for a watermark or brand pattern on every page.

## `pages/<UUID>/visuals/<UUID>/visual.json`

The big one. Structure:

```json
{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.5.0/schema.json",
  "name": "<UUID>",
  "position": {
    "x": 64, "y": 96, "z": 8000,
    "height": 200, "width": 320,
    "tabOrder": 5000
  },
  "visual": {
    "visualType": "cardVisual",
    "query": {
      "queryState": {
        "Data": {
          "projections": [
            {
              "field": { ... measure or column expression ... },
              "queryRef": "Measures Table.$ Sales",
              "nativeQueryRef": "$ Sales",
              "displayName": "$ Sales"
            }
          ]
        }
      }
    },
    "objects": { ... },
    "visualContainerObjects": { ... },
    "drillFilterOtherVisuals": true
  },
  "filterConfig": { ... }
}
```

- **`visualType`** — common values: `cardVisual` (current card format), `card` (legacy, see
  `pbir-gotchas.md` #12), `tableEx`, `pivotTable`, `lineClusteredColumnComboChart`, `barChart`,
  `columnChart`, `lineChart`, `slicer`, `scatterChart`, `donutChart`, `image`, `textbox`,
  `actionButton`. Custom visuals use their full GUID as the value (see `custom-visuals.md`).
- **`position.z`** — z-index. Higher = on top.
- **`query.queryState.<role>.projections[]`** — binds fields to visual roles. Roles vary by
  visual type (`Card` has `Data`; a combo chart has `Category`, `Y`, `Y2`, `Series`).
- **`objects`** — visual-internal styling (the formatting pane on the right).
- **`visualContainerObjects`** — outer container styling (background, border, padding, title — at
  the wrapping container level). See `pbir-gotchas.md` #1 for the placement rule.

### Sort order (`sortDefinition`)

To control how a table/matrix/chart is sorted, add a `sortDefinition` block as a **sibling of
`query`** inside `visual` (NOT inside `query`, NOT at the top level). Omitting it lets Power BI
pick a default sort, which is rarely the one you want for an exec deliverable.

```json
"visual": {
  "visualType": "tableEx",
  "query": { "queryState": { ... } },
  "sortDefinition": {
    "sort": [
      {
        "field": {
          "Measure": {
            "Expression": { "SourceRef": { "Entity": "Measures Table" } },
            "Property": "$ Sales"
          }
        },
        "direction": "Descending"
      }
    ],
    "isDefaultSort": true
  },
  "objects": { ... }
}
```

- `sort[]` — each entry is `{ field, direction }`. `field` uses the same `Measure`/`Column`
  expression shape as a projection. `direction` is `"Ascending"` or `"Descending"`.
- `isDefaultSort: true` — marks this as the visual's initial sort (the state before any user click
  on a column header).
- The sort field does **not** have to be a displayed column — sorting by a measure that isn't one
  of the table's columns works.

Hand-authoring `sortDefinition` in the wrong position (inside `query`, or as a top-level sibling)
throws a schema error on `.pbip` open.

## Stock card trapezoid styling

The trapezoidal/cut-corner KPI card look is a **stock `cardVisual`** with `shapeCustomRectangle`
settings — NOT a custom visual (see `custom-visuals.md` for when a custom visual actually is
warranted; this isn't one of those cases):

```json
"objects": {
  "shapeCustomRectangle": [
    {
      "properties": {
        "rectangleRoundedCurveCustomStyle": { "expr": { "Literal": { "Value": "false" } } },
        "tileShape": { "expr": { "Literal": { "Value": "'tabCutTopCornersByPixel'" } } },
        "tabCutCornerSnipSizeTop": { "expr": { "Literal": { "Value": "20L" } } },
        "tabCutCornerSnipSizeBottom": { "expr": { "Literal": { "Value": "20L" } } },
        "tabCutCornerSnipSizeCustomStyle": { "expr": { "Literal": { "Value": "false" } } }
      },
      "selector": { "id": "default" }
    }
  ]
}
```

Key fields:

- **`tileShape: 'tabCutTopCornersByPixel'`** — produces the trapezoidal silhouette with cut
  corners.
- **`tabCutCornerSnipSizeTop` / `Bottom`** — corner snip size in pixels. 20 is comfortable for
  ~200px-tall cards.

A theme can bundle these settings as a named style preset (Power BI Desktop exposes applying a
style preset via the format pane's "Style preset" dropdown) if the active brand profile's theme
defines one.

## Conditional `fontColor` on `cardVisual`

```json
"value": [{
  "properties": {
    "fontColor": {
      "solid": {
        "color": {
          "expr": {
            "Conditional": {
              "Cases": [
                { "Condition": { "Comparison": { "ComparisonKind": 2, "Left": <measure>, "Right": { "Literal": { "Value": "0D" } } } },
                  "Value": { "Literal": { "Value": "'<positive-case hex>'" } } },
                { "Condition": { "Comparison": { "ComparisonKind": 3, "Left": <measure>, "Right": { "Literal": { "Value": "0D" } } } },
                  "Value": { "Literal": { "Value": "'<negative-case hex>'" } } }
              ]
            }
          }
        }
      }
    }
  },
  "selector": { "data": [{ "dataViewWildcard": { "matchingOption": 0 } }], "metadata": "Sum(<table>.<measure>)" }
}]
```

Resolve `<positive-case hex>`/`<negative-case hex>` from the active brand profile's
`palette.accent`:
- `sentiment_policy: neutral` → use the same hex (the profile's `default_text` color) for both
  cases, and convey direction with an arrow glyph in the display measure instead.
- `sentiment_policy: accent-coded` → use the profile's `positive`/`negative` hexes directly.

## Transparent containers over page backgrounds

When a page has a background image (a logo watermark, a brand pattern), set the visual containers
transparent so the image shows through:

```json
"visualContainerObjects": {
  "background": [
    {
      "properties": {
        "show": { "expr": { "Literal": { "Value": "true" } } },
        "transparency": { "expr": { "Literal": { "Value": "100D" } } }
      }
    }
  ]
}
```

`100D` = 100% transparent. For `cardVisual` specifically, also set
`objects.layout.backgroundTransparency: 100D`.

## Theme-driven color via `ThemeDataColor`

To pull a color from the theme palette (so swapping themes — i.e. swapping the active brand
profile — propagates everywhere):

```json
"fontColor": {
  "solid": {
    "color": {
      "expr": {
        "ThemeDataColor": {
          "ColorId": 0,
          "Percent": 0
        }
      }
    }
  }
}
```

`ColorId` indexes into the active brand profile's theme `dataColors[]` array — `0` is
`palette.primary[0]` (`default_text`/first series), `1` is the next primary entry, and so on, in
whatever order the profile's `palette.primary` list is defined (see `brand-profile.md`).
`Percent` shifts the resolved color toward white (positive) or black (negative).

Use this instead of a hardcoded hex whenever the color should follow theme swaps.

## Page chrome (the master-report look)

Codify these elements across every body page of a multi-page report:

### Top-left: Logo

An `image` visual near the top-left corner, pointing to a registered resource:

```json
"visualType": "image",
"objects": {
  "general": [{
    "properties": {
      "imageUrl": {
        "expr": {
          "ResourcePackageItem": {
            "PackageName": "RegisteredResources",
            "PackageType": 1,
            "ItemName": "<active brand profile logo variant file name>"
          }
        }
      }
    }
  }]
}
```

Which logo variant to reference (`full_color`, `white`, `on_dark`) is the active brand profile's
`logo.selection_rule`, applied against this page's background — see `brand-profile.md`.

### Top-right: Data refresh indicator

A `textbox` or `cardVisual` bound to a "Data Refreshed" measure, positioned near the top-right of
the header band. Typography per the active brand profile's `typography.roles.label`.

### Bottom: Methodology footnote

A `textbox` at the bottom of the page, full-width minus margins. Typography per the active brand
profile's `typography.roles.footnote` (typically italic, smallest role size).

### Optional: Left-rail master nav

For multi-page reports, a vertical pill list of `actionButton` visuals — one per page — with the
active page highlighted in the active brand profile's accent color and inactives in its default
text color.

## Filters (page vs. visual level)

Page-level filter config goes in `page.json`'s `filterConfig.filters[]`. These cascade to every
visual on the page.

Visual-level filters go in a visual's own `filterConfig.filters[]`. These layer on top of page
filters and can override or add.

Filter `type` values:
- `"Categorical"` — slicer-style multi-select
- `"Advanced"` — a DAX-expression filter
- `"TopN"` — top/bottom N (see `pbir-gotchas.md` #7b for the hand-authoring footgun)
- `"RelativeDate"` — last N days/weeks/months

### ALL visual-level filters must be hidden — no exceptions

**Every entry in `filterConfig.filters[]` on a `visual.json` gets `isHiddenInViewMode: true`. No
exceptions.** Full rule, mechanism, and the two-script cleanup workflow (`hide-visual-filters.mjs`
then `preemptive-hide-fields.mjs`) are in `pbir-gotchas.md` #7. The model: viewers interact with
page-level and report-level filters via the Filter pane, or with an on-canvas slicer visual — they
never interact with "Filters on this visual".

Where filters legitimately stay visible (NOT in `visual.json`):

| User control | Where it lives |
|---|---|
| "Filter this whole report" | `report.json` → `filterConfig.filters[]` (no `isHiddenInViewMode`) |
| "Filter this page" | `page.json` → `filterConfig.filters[]` (no `isHiddenInViewMode`) |
| On-canvas selection control (e.g., a region picker) | A `slicer`/`advancedSlicer` **visual** on the canvas — it IS the filter; no separate filter entry needed |

### Hidden technical filters (date scoping without a slicer)

Same `isHiddenInViewMode: true` flag, used to scope a visual to a date range without exposing a
slicer:

```json
{
  "name": "<UUID>",
  "field": { "Column": { ..., "Property": "term_date" } },
  "type": "Advanced",
  "filter": {
    "Version": 2,
    "From": [{ "Name": "c", "Entity": "<entity>", "Type": 0 }],
    "Where": [{
      "Condition": {
        "And": {
          "Left": { "Comparison": { "ComparisonKind": 2, "Left": { "Column": { "Expression": { "SourceRef": { "Source": "c" } }, "Property": "term_date" } }, "Right": { "DateSpan": { "Expression": { "Literal": { "Value": "datetime'2025-01-01T00:00:00'" } }, "TimeUnit": 5 } } } },
          "Right": { "Comparison": { "ComparisonKind": 4, "Left": { ... }, "Right": { ... } } }
        }
      }
    }]
  },
  "isHiddenInViewMode": true
}
```

## Bookmarks

`bookmarks/bookmarks.json` lists the bookmarks; one `<UUID>.bookmark.json` per bookmark.

```json
{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/bookmark/1.0.0/schema.json",
  "name": "<UUID>",
  "displayName": "Hide Filters",
  "options": { "suppressActiveSection": false, "suppressData": true },
  "explorationState": {
    "version": "1.0",
    "activeSection": "<page-UUID>",
    "sections": {
      "<page-UUID>": {
        "visualContainers": {
          "<visual-UUID>": {
            "filters": { "byExpr": [...] },
            "singleVisual": { "activeProjections": {...} }
          }
        }
      }
    }
  }
}
```

A common pattern is a "Hide Filters" bookmark with `suppressData: true` that collapses the filter
pane for cleaner viewing. See `pbir-gotchas.md` #10 for the `display.mode` enum trap on
show/hide-toggle bookmarks.

### Page-level filter with no default (show all)

When a filter should be available in the pane for optional refinement but with NO preset value
(filter pane shows "is (All)"):

```json
{
  "name": "<UUID>",
  "displayName": "Business Manager",
  "ordinal": 1,
  "field": {
    "Column": {
      "Expression": { "SourceRef": { "Entity": "<entity>" } },
      "Property": "Business_Manager"
    }
  },
  "type": "Categorical",
  "howCreated": "User"
}
```

The minimal shape: `field` + `type: "Categorical"` + `howCreated: "User"`. No `filter` body block,
no `objects.general.requireSingleSelect`. A common cloned-page trap: an inherited filter carrying
`requireSingleSelect: true` plus a hardcoded default value — both must come out for a true
"All by default" filter.

To go the other way (lock to a value, hidden from view): keep the `filter` body, add
`isHiddenInViewMode: true` + `isLockedInViewMode: true`.

### Hiding totals on `tableEx`

The bottom total row on a `tableEx` is suppressed by `objects.total[0].properties.totals = false`:

```json
"total": [
  {
    "properties": {
      "totals": { "expr": { "Literal": { "Value": "false" } } }
    }
  }
]
```

NOT `total.show`. NOT `general.totals`. NOT `subTotals.rowSubtotals` (that's the `pivotTable`
property). Power BI Desktop's linter strips the wrong property names and they have no effect —
`total.totals` is what survives a save and actually suppresses the row.

For `pivotTable` (matrix) instead use `subTotals.rowSubtotals = false` +
`subTotals.columnSubtotals = false`. See `pbir-gotchas.md` #3 for the wider matrix-selector story.

## Visual variety — when to use what

| Use case | Visual type |
|---|---|
| Single number with optional secondary | `cardVisual` |
| Multiple cards in a row | Several `cardVisual` (trapezoid pattern, or a custom KPI grid — see `custom-visuals.md`) |
| Time series, two metrics | `lineClusteredColumnComboChart` |
| Time series, one metric | `lineChart` |
| Categorical comparison | `barChart` (horizontal) or `columnChart` (vertical) |
| Distribution / quadrant analysis | `scatterChart`, or a custom quadrant visual with auto-thresholds — see `custom-visuals.md` |
| Heatmap with two dimensions | A custom visual — stock matrix doesn't render colors well |
| Detail table | `tableEx` |
| Cross-tab | `pivotTable` |
| Multi-select dimension | `slicer` |
| Selector with status colors | A custom status-slicer visual — see `custom-visuals.md` |
| Geographic points | `azureMap` — but the `Legend` role does NOT color bubbles distinctly on its own; see `pbir-gotchas.md` #9 |
| Page navigation | `actionButton` |

If stock visuals don't fit, build custom — see `custom-visuals.md`.

## Common mistakes

1. **Treating the trapezoid card as a custom visual** — it's stock `cardVisual` with
   `shapeCustomRectangle.tileShape`.
2. **Hardcoded color hex on every visual** — use `ThemeDataColor` so a theme/brand-profile swap
   propagates.
3. **No page-level filters** — every visual ends up with its own filter; impossible to slice the
   whole page at once.
4. **Any visible visual-level filter** — see "ALL visual-level filters must be hidden" above and
   `pbir-gotchas.md` #7.
5. **Not registering an image as a `RegisteredResources` package item** — pasting it directly
   into a visual works but doesn't share across pages and doesn't update on logo swap.
6. **Pixel-perfect layouts at `Actual Size`** — breaks on any non-default screen. Use
   `FitToPage`.

## Page layout grid

A common PBI exec-report canvas convention — not a mandate, but a reasonable default to lock in
when there's no reason to deviate:

```
Canvas:        1280 × 720
Outer margin:  24 left/right (footer is full-bleed)
Header band:   y = 20-90  (logo @ y=24 h=56, title @ y=20 h=70, refresh @ y=24 h=30)
Body band:     y = 96-652 (556 px tall — MAXIMUM body envelope, not a fixed card height)
Footer band:   y = 660-720 (full bleed, image)
Inner gap:     16 px between visuals (vertical AND horizontal)
Body→footer:   ≥8 px breathing room (last visual bottom ≤ 652)
```

Right margin: most body visuals end at `x ≤ 1256`. A refresh-indicator card is a common exception,
sitting closer to the far edge than other body visuals.

**Card height is a MAXIMUM, not a target.** A card sized to the full 556px body envelope but
containing 10 rows of data looks half-empty and reads as broken. Size cards to typical-data-height
plus small headroom.

## Page chrome canonical shape

Repeats on every body page. Treat as a single source of truth — if these drift across pages, the
report looks inconsistent. `scripts/check-page-chrome-drift.mjs` (relative to the power-platform
mode's own directory — see `visual-verification.md`) enforces this programmatically.

| Visual name | Position | Visual type | Notes |
|---|---|---|---|
| `v_logo` | x=24, y=24, w=92, h=56 | `image` | Active brand profile's logo (variant per `logo.selection_rule`). **Requires `padding=0` on all sides** (see below) |
| `v_title` | x=130, y=20, w=700, h=70 | `textbox` | Active profile's `typography.roles.title`, bold + a lighter secondary line if split |
| `v_refresh` | x=936, y=24, w=296, h=30 | `cardVisual` | bound to a "Refresh Display" measure. Right-aligned, italic, active profile's `label` typography. **Add a `filterConfig` Advanced filter on the bound measure** to suppress the visual when blank |
| `v_footer_bar` | x=0, y=660, w=1280, h=60 | `image` | Full-bleed footer image. **Requires `padding=0` on all sides** |

## Image visual padding=0 (required for logos and decorative images)

Power BI image visuals apply default internal padding (~10–14px) around the rendered image. Logos
in tight header bars and full-bleed footers look indented or floating unless padding is explicitly
zeroed.

```json
"visualContainerObjects": {
  "border": [
    { "properties": { "show": { "expr": { "Literal": { "Value": "false" } } } } }
  ],
  "background": [
    { "properties": { "show": { "expr": { "Literal": { "Value": "false" } } } } }
  ],
  "padding": [
    {
      "properties": {
        "top":    { "expr": { "Literal": { "Value": "0D" } } },
        "right":  { "expr": { "Literal": { "Value": "0D" } } },
        "bottom": { "expr": { "Literal": { "Value": "0D" } } },
        "left":   { "expr": { "Literal": { "Value": "0D" } } }
      }
    }
  ]
}
```

Path B (the static layout preview) cannot show this difference — image padding is only visible in
Power BI Desktop or published view (Path A). See `visual-verification.md`.

## Matrix (`pivotTable`) canonical shape

The matrix is the most footgun-heavy visual in PBIR. The selector requirement and drill-icon
mechanics are covered in full in `pbir-gotchas.md` #3 and #4; the remaining shape rules:

### `general.layout` controls drill-down icon visibility

| Value | Row-header rendering | Drill icons (`+`/`−`) |
|---|---|---|
| `'Compact'` (default) | Stacked with indentation | **Appear in published view** when subtotals enabled |
| `'Tabular'` | One column per row level | None — always-expanded look |
| `'Outline'` | Similar to Compact, different indent | Appear in published view |

Choose `Compact` when end-users should drill. Choose `Tabular` when the report should always show
every row level with no interactivity. Setting `Tabular` and then asking why there are no `+`
icons is the most common matrix authoring mistake.

### `expansionStates.isPinned: true` overrides `isCollapsed: true`

A pinned level always renders. For a collapsed-by-default initial state, remove `isPinned` from
the level you want collapsed.

```json
"expansionStates": [
  {
    "roles": ["Rows"],
    "levels": [
      { "queryRefs": ["<entity>.<level-1-column>"] },
      {
        "queryRefs": ["<entity>.<level-2-column>"],
        "isCollapsed": true
      }
    ],
    "root": {}
  }
]
```

### Power BI Desktop edit mode renders the matrix fully expanded

Path A captures edit mode. Drill icons appear on hover in edit mode and persistently in published
view. Don't chase them in static Path A captures — verify by publishing or toggling Desktop's
View → Reading View.

### Container background choice depends on page background

| Page bg | Container bg | Result |
|---|---|---|
| Active profile's `background_alt` | White `#FFFFFF` | Clean: a white card pops against a tinted page; tinted data rows pop against the white container |
| Active profile's `background_alt` | Same tint | **Card is invisible** — data and container both blend with the page. Either add a strong border (the profile's `default_text` color) or change the container |
| Active profile's `background_alt` | Transparent (`show: false`) | Card edge depends on data rows only; empty area below data shows the page tint. Sometimes desirable, sometimes visually "off" |

**Recommendation:** white container + a strong border in the active profile's `default_text`
color + the profile's `background_alt` tint on data rows, over a tinted page.

## How hand-authored properties survive Power BI Desktop saves

Power BI Desktop rewrites `visual.json` on every save. Properties it doesn't recognize, or
properties matching theme defaults, are at risk of being stripped:

1. **Include the selector.** Covered in `pbir-gotchas.md` #3 for `pivotTable`. Properties without
   selectors are first to be dropped.
2. **Don't set properties to values identical to the theme.** Power BI sees these as "no override
   needed" and drops them. To lock a property at a value the theme already sets, use a
   one-shade-different value instead.
3. **Place properties on object blocks Power BI emits.** An invented `objects.foo` block Power BI
   doesn't know about gets dropped on save. Compare against an existing Desktop-authored
   `visual.json` for the same `visualType`.
4. **Schema version drift is a smoke signal.** A page last touched in Power BI Desktop has a newer
   `$schema` than pages touched only programmatically. Mixed versions in one Report mean someone
   hand-edited one page in Desktop.

Workflow consequence: when iterating with a human editing in Power BI Desktop concurrently, do
save → close → reopen between edits. Disk-read state and Desktop's in-memory state diverge
silently otherwise.
