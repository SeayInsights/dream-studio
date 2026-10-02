# Custom Visual (pbiviz) Development

Building, theming, packaging, and certifying Power BI custom visuals (pbiviz / IVisual /
TypeScript). Companion to this domain's `dax-patterns.md` / `m-query-patterns.md` /
`tmdl-authoring.md` / `pbip-format.md` (semantic-model and report-JSON side) and to
`visual-verification.md` (self-verifying a report change). Read `brand-profile.md` first if this
work touches any color, font, or logo default.

All `scripts/...` paths below are relative to the power-platform mode's own directory:
`canonical/skills/domains/modes/power-platform/` (sibling to that mode's `SKILL.md`).

## When to build custom vs. stock

Build a custom visual when:

- **Grid consolidation** — replacing dozens of card visuals with one (a KPI-grid pattern).
- **Embedded controls** — the visual needs its own dropdown/toggle, avoiding a separate slicer.
- **Domain-specific visualization** — a distribution heatmap, a status strip, a timeline with
  event markers and shaded regions — where stock matrix/line visuals can't render the shape.
- **Quadrant analysis with auto-computed thresholds** — a scatter plot that computes its own
  median/quartile lines from the bound data.
- **Complex cross-filtering** — selection logic that's awkward to express in a stock slicer.

Use a stock visual when:

- Simple bar/line/scatter with no special interactivity.
- Standard table or matrix.
- KPI cards — including the trapezoid/cut-corner look (`shapeCustomRectangle.tileShape:
  'tabCutTopCornersByPixel'`, a stock `cardVisual` property — see `report-visual-json.md`). This
  is **not** a reason to build a custom visual.

**Escalation discipline (from the main build skill):** after three distinct stock-visual
approaches have failed to meet a requirement, custom-visual development is the right tool — but
confirm with the user before starting; it's a multi-day commitment, not a one-off edit. For an
immediate, unambiguous custom-visual request (the user says "pbiviz", "capabilities.json",
"IVisual", "build a custom visual", etc.), start directly — no three-attempt threshold needed.

## Project structure

```
<org-prefix>-<kebab-case-name>/
├── pbiviz.json                       ← visual metadata + entry points
├── capabilities.json                 ← data roles, formatting properties, dataView mapping
├── package.json                      ← npm dependencies + scripts
├── tsconfig.json                     ← TypeScript config
├── eslint.config.mjs                 ← Power BI ESLint rules
├── src/
│   ├── visual.ts                     ← main Visual class (IVisual)
│   └── settings.ts                   ← FormattingSettingsModel
├── style/
│   └── visual.less                   ← LESS stylesheet
├── assets/
│   └── icon.png                      ← visual thumbnail (20×20; also 64×64 for org install)
└── dist/                             ← .pbiviz output (gitignored)
```

### Naming conventions

Use your organization's own short prefix, consistently, across folder name, `pbiviz.json`'s
`name`, `guid`, and `displayName`:

| Field | Format | Example (prefix `acme`) |
|---|---|---|
| Folder | `<prefix>-<kebab-case-name>` | `acme-status-slicer` |
| `name` in JSON | `<prefix><PascalCaseName>` | `acmeStatusSlicer` |
| `guid` | `<prefix><PascalCaseName>` + 32 hex chars | `acmeStatusSlicerA1B2C3D4...` |
| `displayName` | `<Org> <Spaced Name>` | `Acme Status Slicer` |

Generate the GUID suffix fresh from any UUID generator (strip dashes) for every new visual —
never copy-paste from another visual's GUID. The full GUID must be globally unique across every
custom visual ever published, anywhere.

### Scaffold script

```powershell
pwsh scripts/new-visual.ps1 -Name "MyVisual" -DisplayName "My Visual" -BrandProfile <path-to-profile.yml>
```

Wraps `pbiviz new` and patches in the active brand profile's defaults (typography and format-pane
color defaults in `style/visual.less`, author info, org prefix). Omit `-BrandProfile` to fall back
to `brand-profiles/default.yml`. See `scripts/new-visual.ps1`.

### `pbiviz.json`

```json
{
  "visual": {
    "name": "acmeMyVisual",
    "displayName": "Acme My Visual",
    "guid": "acmeMyVisualXXXXXXXXXXXXXXXXXXXXXX",
    "visualClassName": "Visual",
    "version": "1.0.0.0",
    "description": "One-line description of what the visual does."
  },
  "apiVersion": "5.3.0",
  "author": {
    "name": "<your organization>",
    "email": "<contact address>"
  },
  "assets": {
    "icon": "assets/icon.png"
  },
  "style": "style/visual.less",
  "capabilities": "capabilities.json"
}
```

### `package.json`

```json
{
  "name": "visual",
  "version": "1.0.0.0",
  "scripts": {
    "pbiviz": "pbiviz",
    "start": "pbiviz start",
    "package": "pbiviz package",
    "lint": "npx eslint ."
  },
  "dependencies": {
    "@types/d3": "7.4.3",
    "d3": "7.9.0",
    "powerbi-visuals-api": "~5.3.0",
    "powerbi-visuals-utils-formattingmodel": "6.0.4"
  },
  "devDependencies": {
    "@typescript-eslint/eslint-plugin": "^8.8.0",
    "eslint": "^9.11.1",
    "eslint-plugin-powerbi-visuals": "^1.0.0",
    "typescript": "5.5.4"
  }
}
```

Pin versions exactly. Mismatches between `powerbi-visuals-api` and
`powerbi-visuals-utils-formattingmodel` are a common build-failure source (see Gotcha #9 below) —
the 5.3.0 API expects 6.0.4 of the formatting utils; bump both together.

### `tsconfig.json`

```json
{
  "compilerOptions": {
    "target": "es2022",
    "moduleResolution": "node",
    "lib": ["es2022", "dom"],
    "outDir": "./.tmp/build/",
    "strict": true
  },
  "files": ["./src/visual.ts"]
}
```

### `eslint.config.mjs`

```js
import powerbiVisualsConfigs from "eslint-plugin-powerbi-visuals";

export default [
    powerbiVisualsConfigs.configs.recommended,
    { ignores: ["node_modules/**", "dist/**", ".vscode/**", ".tmp/**"] }
];
```

### `style/visual.less`

Derive the color/font variables from the active brand profile rather than hardcoding a specific
palette:

```less
@font-family: "<active profile typography.font_family>", "Segoe UI", sans-serif;
@text-color: <active profile palette.primary default_text hex>;
@accent-color: <active profile palette.primary accent_selected hex>;
@border-color: <active profile palette.secondary divider hex>;
@white: #FFFFFF;

.visual-container {
  font-family: @font-family;
  color: @text-color;
  overflow-y: auto;

  .tile {
    background: @white;
    color: @text-color;
    border: 1px solid @border-color;
    padding: 8px 12px;

    &--selected {
      background: @border-color;
      border-color: @accent-color;
    }

    &--dimmed {
      opacity: 0.35;
    }
  }
}
```

`scripts/new-visual.ps1` generates this block automatically from whatever `-BrandProfile` you
pass it (or the default profile if omitted) — you shouldn't normally hand-write it.

## `capabilities.json`

Defines what fields the user can drop on the visual, how Power BI delivers data, and what
formatting properties appear in the format pane. Three main sections: `dataRoles`,
`dataViewMappings`, `objects`.

### Categorical data role pattern (most common)

```json
{
  "dataRoles": [
    {
      "displayName": "Category",
      "name": "category",
      "kind": "Grouping",
      "description": "What to group rows by"
    },
    {
      "displayName": "Value",
      "name": "value",
      "kind": "Measure",
      "description": "Numeric value driving the visual"
    }
  ],
  "dataViewMappings": [
    {
      "categorical": {
        "categories": {
          "for": { "in": "category" },
          "dataReductionAlgorithm": { "top": { "count": 500 } }
        },
        "values": {
          "select": [{ "bind": { "to": "value" } }]
        }
      }
    }
  ],
  "objects": {
    "myCard": {
      "properties": {
        "color": { "type": { "fill": { "solid": { "color": true } } } },
        "fontSize": { "type": { "formatting": { "fontSize": true } } },
        "showLabels": { "type": { "bool": true } }
      }
    }
  },
  "privileges": []
}
```

### Matrix data role (heatmap, cross-tab)

```json
"dataViewMappings": [{
  "matrix": {
    "rows": { "for": { "in": "rows" }, "dataReductionAlgorithm": { "top": { "count": 2000 } } },
    "columns": { "for": { "in": "columns" }, "dataReductionAlgorithm": { "top": { "count": 200 } } },
    "values": { "select": [{ "bind": { "to": "values" } }] }
  }
}]
```

### `kind` values for data roles

- `Grouping` — dimension fields users group by
- `Measure` — numeric aggregates
- `GroupingOrMeasure` — accepts either

### `dataReductionAlgorithm` is required

Without a cap, large datasets crash the visual. Common values:

- `{ "top": { "count": 500 } }` — first 500 categories
- `{ "sample": { "count": 1000 } }` — random sample
- `{ "bottom": { "count": 100 } }` — last 100 categories

Pick a value that's a reasonable upper bound for the visual's purpose. A KPI grid might cap at
50; a distribution heatmap might cap at 2,000; a matrix at 2,000 rows.

### `objects` types (formatting pane properties)

| Type | Use for |
|---|---|
| `{ "numeric": true }` | Number input (font size, columns, etc.) |
| `{ "bool": true }` | Toggle |
| `{ "text": true }` | Text input |
| `{ "fill": { "solid": { "color": true } } }` | Color picker |
| `{ "formatting": { "fontSize": true } }` | Font-size dropdown |
| `{ "enumeration": [...] }` | Dropdown with predefined choices |
| `{ "formatting": { "fontFamily": true } }` | Font family picker |

The `objects` IDs and property names here must match the names used in `settings.ts` — that's how
Power BI wires format-pane controls to your TypeScript.

### `privileges`

Most visuals: `"privileges": []`. Add specific privileges only if needed:

```json
"privileges": [
  { "name": "WebAccess", "essential": true, "parameters": ["https://*.example.com"] }
]
```

For org-wide or certified visuals, reviewers scrutinize any non-empty `privileges` — see the
Certification Checklist below.

## `src/settings.ts`

`FormattingSettingsModel` pattern using `powerbi-visuals-utils-formattingmodel` — the TypeScript
side of the format pane. The `objects` IDs in `capabilities.json` must match the `name` fields
here.

```ts
import { formattingSettings } from "powerbi-visuals-utils-formattingmodel";

import FormattingSettingsCard = formattingSettings.SimpleCard;
import FormattingSettingsSlice = formattingSettings.Slice;
import FormattingSettingsModel = formattingSettings.Model;

class MyCard extends FormattingSettingsCard {
    color = new formattingSettings.ColorPicker({
        name: "color",
        displayName: "Color",
        value: { value: "<active brand profile default_text hex>" }
    });

    fontSize = new formattingSettings.NumUpDown({
        name: "fontSize",
        displayName: "Font Size",
        value: 12,
        options: {
            minValue: { type: powerbi.visuals.ValidatorType.Min, value: 8 },
            maxValue: { type: powerbi.visuals.ValidatorType.Max, value: 36 }
        }
    });

    showLabels = new formattingSettings.ToggleSwitch({
        name: "showLabels",
        displayName: "Show Labels",
        value: true
    });

    name: string = "myCard";              // ← matches capabilities.json objects.myCard
    displayName: string = "My Card";
    slices: Array<FormattingSettingsSlice> = [this.color, this.fontSize, this.showLabels];
}

export class VisualFormattingSettingsModel extends FormattingSettingsModel {
    myCard = new MyCard();
    cards = [this.myCard];
}
```

### Common slice types

| Slice | Use for |
|---|---|
| `ColorPicker` | Color selection. `value: { value: "#HEX" }`. |
| `NumUpDown` | Numeric input with min/max. |
| `Slider` | 0–100 range. |
| `ToggleSwitch` | Boolean toggle. |
| `TextInput` | Free-text entry. |
| `AutoDropdown` | Enum from `capabilities.json`'s `enumeration` list. |
| `FontPicker` | Font family. |

Full list is in `powerbi-visuals-utils-formattingmodel`'s typings — when in doubt, check the
package's `.d.ts` or the Microsoft Learn format-pane docs.

### Default values for a new visual's format-pane controls

Use the active brand profile as the starting `value:` for each slice, not a hardcoded client's
colors:

| Slice | Source |
|---|---|
| Default text color | active profile `palette.primary` role `default_text` |
| Default accent color | active profile `palette.primary` role `accent_selected` |
| Default neutral / borders | active profile `palette.secondary` role `divider` |
| Default font family | active profile `typography.font_family` |
| Default font size | 10–12pt (10 for table cells, 11 for body, 12 for cards) is a reasonable starting range |
| Default series colors | **Don't hardcode.** Pull from `host.colorPalette` in `visual.ts` — see Theme-Aware Colors below. |

### Repopulate on every `update()`

Critical: call `populateFormattingSettingsModel` on every `update()` invocation, not just in the
constructor. Otherwise format-pane changes don't take effect (Gotcha #6 below).

## `src/visual.ts`

The `IVisual` class — main lifecycle, dataView handling, host APIs, selection, tooltip.

```ts
"use strict";

import "./../style/visual.less";
import powerbi from "powerbi-visuals-api";
import { FormattingSettingsService } from "powerbi-visuals-utils-formattingmodel";

import IVisual = powerbi.extensibility.visual.IVisual;
import VisualConstructorOptions = powerbi.extensibility.visual.VisualConstructorOptions;
import VisualUpdateOptions = powerbi.extensibility.visual.VisualUpdateOptions;
import IVisualHost = powerbi.extensibility.visual.IVisualHost;
import ISelectionManager = powerbi.extensibility.ISelectionManager;
import IColorPalette = powerbi.extensibility.IColorPalette;

import { VisualFormattingSettingsModel } from "./settings";

export class Visual implements IVisual {
    private target: HTMLElement;
    private host: IVisualHost;
    private selectionManager: ISelectionManager;
    private colorPalette: IColorPalette;
    private formattingSettings: VisualFormattingSettingsModel;
    private formattingSettingsService: FormattingSettingsService;

    constructor(options: VisualConstructorOptions) {
        this.target = options.element;
        this.host = options.host;
        this.selectionManager = this.host.createSelectionManager();
        this.colorPalette = this.host.colorPalette;        // ← honor active theme
        this.formattingSettingsService = new FormattingSettingsService();
        // Initialize root container in this.target (DOM or SVG)
    }

    public update(options: VisualUpdateOptions): void {
        // 1. Validate dataView
        const dataView = options.dataViews?.[0];
        if (!dataView?.categorical?.categories?.length) {
            this.renderEmptyState();
            return;
        }

        // 2. Populate formatting settings from dataView (every update, not just constructor)
        this.formattingSettings = this.formattingSettingsService.populateFormattingSettingsModel(
            VisualFormattingSettingsModel,
            dataView
        );

        // 3. Transform data
        const data = this.transformData(dataView.categorical);

        // 4. Render
        this.render(data, options.viewport);
    }

    public getFormattingModel(): powerbi.visuals.FormattingModel {
        return this.formattingSettingsService.buildFormattingModel(this.formattingSettings);
    }

    private transformData(categorical: powerbi.DataViewCategorical) {
        const categories = categorical.categories[0];
        const values = categorical.values[0];

        return categories.values.map((cat, i) => ({
            category: <string>cat,
            value: <number>values.values[i],
            selectionId: this.host.createSelectionIdBuilder()
                .withCategory(categories, i)
                .createSelectionId()
        }));
    }

    private render(data: any[], viewport: powerbi.IViewport) {
        // Clear container — DOM accumulates across update() calls otherwise
        while (this.target.firstChild) this.target.removeChild(this.target.firstChild);

        // Use this.colorPalette.getColor(seriesName).value for theme-aware series colors
        // Use this.formattingSettings.<card>.<property>.value for user settings

        data.forEach((row, i) => {
            const el = document.createElement("div");
            el.className = "tile";
            el.style.color = this.formattingSettings.myCard.color.value.value;
            el.style.fontSize = this.formattingSettings.myCard.fontSize.value + "px";
            el.textContent = `${row.category}: ${row.value}`;

            // Cross-filter on click
            el.addEventListener("click", (e) => {
                this.selectionManager.select(row.selectionId, (e as MouseEvent).ctrlKey)
                    .then(() => this.updateSelectionStyle());
            });

            this.target.appendChild(el);
        });
    }

    private renderEmptyState() {
        while (this.target.firstChild) this.target.removeChild(this.target.firstChild);
        const empty = document.createElement("div");
        empty.className = "visual-empty";
        empty.innerHTML = "<h3>Add data to see the visual</h3>";
        this.target.appendChild(empty);
    }

    private updateSelectionStyle() {
        // Re-render with dimming for unselected items
    }
}
```

### Selection manager + cross-filter

```ts
this.selectionManager.select(selectionId, multiSelect).then(() => {
    const selectedIds = this.selectionManager.getSelectionIds();
    // Re-render with dimming for non-selected items
});
```

Build selection IDs at data-transform time (not at click time — they need the categorical
metadata):

```ts
const selectionId = this.host.createSelectionIdBuilder()
    .withCategory(categories, rowIndex)
    .createSelectionId();
```

For matrix data, use `.withMatrixNode(node, levels)`. For series data, `.withSeries(seriesGroups,
seriesValue)`.

### Tooltip service

```ts
private tooltipService = this.host.tooltipService;

el.addEventListener("mouseover", (e) => {
    this.tooltipService.show({
        coordinates: [e.clientX, e.clientY],
        isTouchEvent: false,
        dataItems: [
            { displayName: "Category", value: row.category },
            { displayName: "Value", value: row.value.toString() }
        ],
        identities: [row.selectionId]
    });
});

el.addEventListener("mouseout", () => {
    this.tooltipService.hide({ immediately: false, isTouchEvent: false });
});
```

## Theme-Aware Colors

Why `host.colorPalette` matters, and why hardcoded hex constants (`#118DFF` or any other fixed
value) are a smell to fix.

### The pattern

```ts
const seriesColor = this.colorPalette.getColor("Series 1").value;  // pulls from active theme dataColors
```

When the report's active theme is the active brand profile's theme, this returns that profile's
`dataColors[]` entries in order (`"Series 0"` → `palette.primary[0]`, `"Series 1"` →
`palette.primary[1]`, and so on). When the analyst applies a different theme, the same code
produces that theme's colors — no rebuild required.

### Why this matters

Custom visuals are one of the few places in a PBIP project where it's tempting to hardcode
colors: the LESS stylesheet can define fixed variables, the format-pane color picker needs a
default value, and TypeScript drawing a series sees a clean `colors[i]` API. It's faster to
write `colors[i] = "#118DFF"` than to wire up the host palette correctly. But the cost is real:

- The visual ignores the report theme — every brand profile's report looks wrong.
- The visual is hostile to certified-visual review (org-wide rollout requires theme-aware colors).
- Swapping a client's colors means rebuilding and republishing the visual instead of just
  swapping the active brand profile's theme.

### What to use `host.colorPalette` for vs. format-pane defaults

| Use case | Use |
|---|---|
| Series colors (a category's bar, a line, a quadrant point) | `host.colorPalette.getColor(seriesName).value` |
| Default value for a user-facing color picker (the analyst can override) | The active brand profile's default in `settings.ts` |
| Fixed neutral chrome (borders, hover backgrounds, dimmed states) | The active brand profile's secondary color, hardcoded in `style/visual.less` as a LESS variable |
| Conditional fills based on a value (positive vs. negative) | `host.colorPalette.getColor("Positive")`/`"Negative"` if the theme defines them — otherwise the active profile's `palette.accent.positive`/`negative` (if `sentiment_policy: accent-coded`) or its neutral glyph+weight convention |

Rule of thumb: **anything driven by data** (series, categorical fills, conditional formatting)
goes through `host.colorPalette`. **Anything driven by the visual's chrome** (borders, the format
pane's default color value, dimming) is the active brand profile's value, hardcoded at build
time.

### Migrating an existing visual off hardcoded hex

1. Find hex constants in `src/visual.ts` and `style/visual.less`.
2. For each, decide: is this series-driven (data-bound) or chrome (fixed)?
3. Series-driven → replace with `this.colorPalette.getColor(name).value`. Pick a stable `name`
   (the category value, or `"Series 0"`/`"Series 1"`/etc.).
4. Chrome → keep hardcoded but swap the value to the active brand profile's equivalent.
5. Test with the active profile's theme applied — colors should match the report.
6. Test with a different theme applied — colors should change. If they don't, a hardcoded
   constant was missed.

### Custom palette without a theme

Sometimes the requirement is "use these specific colors regardless of theme" — a status-color
encoding where Green = Active, Yellow = Warning, Red = Inactive must always be those colors
regardless of the active brand profile. That's fine:

```ts
const STATUS_COLORS = { active: "#2E7D32", warning: "#F9A825", inactive: "#C62828" };
```

This is not a series color, it's a fixed semantic encoding. Document why it's hardcoded so a
future reviewer doesn't try to "fix" it into `host.colorPalette`.

## Packaging & Sideload

### Pre-flight check

Before scaffolding, verify the toolchain:

```powershell
pwsh scripts/check-pbiviz-env.ps1
```

Verifies Node ≥ 18, the `pbiviz` CLI (`npm i -g powerbi-visuals-tools`), and the pbiviz dev SSL
certificate (`pbiviz install-cert`). Prints the exact fix command for anything missing.

### Dev loop

```bash
cd <org-prefix>-<visual-name>/
npm install          # first time
npm start             # dev server at https://localhost:8080/
```

In Power BI Desktop:

1. File → Options & Settings → Options → Preview features → enable **Developer Visual**
   (one-time, per machine).
2. Insert tab → "..." More visuals → Get more visuals → search "Developer Visual" → drop the
   placeholder onto the report. It loads from `https://localhost:8080/`.
3. Drop fields onto the visual. It hot-reloads on every TypeScript save.

If changes don't appear: visual's "..." menu → **Refresh visual**. Still stuck: kill `npm start`,
reload PBI Desktop, restart `npm start`.

### Lint and package

```bash
npm run lint                        # ESLint with Power BI rules — fix all warnings before packaging
npm run package                     # produces dist/<visualName>.<guid>.<version>.pbiviz
```

Bump `pbiviz.json`'s `version` for each release: `1.0.0.0` → `1.0.1.0` for a patch, `1.1.0.0` for
a feature.

### Installing the `.pbiviz` in one report

Power BI Desktop → Insert → "..." More visuals → Import a visual from a file → pick the
`.pbiviz`. The visual is embedded in that report only; it lives under the report's
`.Report/CustomVisuals/` folder when saved as PBIP.

### Installing organization-wide

Power BI admin portal → Tenant settings → Organizational visuals → Add custom visual → upload the
`.pbiviz`. Once a tenant admin approves, every user in the org finds it under "Get more visuals →
My organization." Check the Certification Checklist below before submitting.

### What to commit / ignore

```gitignore
node_modules/
.tmp/
dist/
*.pbiviz                # if generated locally; commit only released versions
```

Commit released `.pbiviz` files separately as part of a release tag if a versioned download
artifact is needed.

## Gotchas

Ten common failures during pbiviz development, in rough frequency order.

### 1. GUID collision

**Symptom:** the visual loads but data doesn't bind, or another report's custom visual shows
instead.

**Cause:** copy-pasting from another visual without changing `guid` in `pbiviz.json`. Power BI
uses the GUID as the visual's identity.

**Fix:** always generate a fresh GUID — `<name>` + 32 hex chars from any UUID generator (strip
dashes). The full GUID must be globally unique across every custom visual ever published.

### 2. `dataReductionAlgorithm` missing

**Symptom:** works on small data, crashes or hangs on large datasets.

**Cause:** `capabilities.json`'s `dataViewMappings` has no `dataReductionAlgorithm`.

**Fix:**

```json
"categories": {
  "for": { "in": "category" },
  "dataReductionAlgorithm": { "top": { "count": 500 } }
}
```

500 is fine for tile/grid visuals; 2000 for matrices; 50 for KPI cards.

### 3. Hardcoded color hex

**Symptom:** visual ignores the report theme regardless of which one is applied.

**Cause:** series colors hardcoded as hex literals instead of `host.colorPalette`.

**Fix:** see Theme-Aware Colors above. Replace `colors[i] = "#118DFF"` with `colors[i] =
this.colorPalette.getColor("Series " + i).value`.

### 4. No `renderEmptyState`

**Symptom:** the visual throws (`Cannot read property 'values' of undefined`) the moment it's
added with no fields bound.

**Fix:** validate at the top of `update()`:

```ts
const dataView = options.dataViews?.[0];
if (!dataView?.categorical?.categories?.length) {
    this.renderEmptyState();
    return;
}
```

### 5. Forgetting to clear the container

**Symptom:** DOM elements accumulate on every interaction — after 10 clicks, 10 stacked copies
of every tile.

**Fix:** clear at the top of every render:

```ts
while (this.target.firstChild) this.target.removeChild(this.target.firstChild);
```

### 6. Stale formatting settings

**Symptom:** changing a format-pane value (font size, color) doesn't update the visual until
re-added.

**Cause:** `populateFormattingSettingsModel` only called in the constructor.

**Fix:** call it on every `update()`:

```ts
this.formattingSettings = this.formattingSettingsService.populateFormattingSettingsModel(
    VisualFormattingSettingsModel,
    dataView
);
```

### 7. Selection IDs not regenerated when data changes

**Symptom:** clicking a tile cross-filters the wrong row, or stops filtering after a slicer
change.

**Fix:** rebuild selection IDs in `transformData` on every `update()`. Don't cache them at the
class level.

### 8. D3 scales not recomputed on viewport change

**Symptom:** after resizing the visual on the canvas, points clip or axes misalign.

**Fix:** recompute scales every `update()` from `options.viewport.width` / `.height`.

### 9. API version mismatch

**Symptom:** `npm install` succeeds but `npm start`/`npm run package` fails with cryptic
TypeScript errors.

**Cause:** `powerbi-visuals-api` and `powerbi-visuals-utils-formattingmodel` versions out of sync.

**Fix:** pin both to versions known to work together (5.3.0 API ↔ 6.0.4 formatting utils). When
upgrading, bump both at once and check the API release notes for breaking changes.

### 10. Visual broke after a Power BI Desktop update

**Symptom:** worked yesterday, broken today, no code change.

**Cause:** Desktop pinned a newer API version than the sideloaded `.pbiviz` was built against.

**Fix:** rebuild with `npm run package` against the current API version.

## Certification Checklist

Requirements before org-wide rollout, and the additional bar for Microsoft AppSource
certification.

### Org-wide minimum bar

Required for any visual uploaded via Admin portal → Organizational visuals:

- [ ] **Unique GUID.** No collision with any other org or Microsoft AppSource visual.
- [ ] **`dataReductionAlgorithm` set on every `dataViewMapping`** — must not crash on a 100K-row table.
- [ ] **Validates `dataView` at top of `update()`** — renders empty state on missing data.
- [ ] **Theme-aware series colors** — `host.colorPalette` for all data-driven colors.
- [ ] **No `console.log`** in the production build (lint should catch this).
- [ ] **No external network calls** unless `privileges` declares them with a real reason.
- [ ] **No `eval` / `Function` constructor** — fails security review.
- [ ] **Linter passes** — `npm run lint` clean.
- [ ] **Visual icon** — 20×20 PNG in `assets/icon.png`, optionally 64×64 for a listing.
- [ ] **`description`** in `pbiviz.json` is one real human sentence, not "Custom visual."
- [ ] **`version` is bumped** since the previous upload.
- [ ] **Tested with the active brand profile's theme applied** — colors/fonts read correctly.
- [ ] **Tested with empty data** — no JS error in console.
- [ ] **Tested with maximum-cap data** — visual remains responsive.

### Microsoft AppSource certified — additional bar

Certified visuals can be embedded in exported PowerPoints/PDFs and pass through Power BI
Service's stricter sandbox. Only pursue this if the visual will be published in AppSource.

- [ ] **No external resources at runtime** — no fetched JS, fonts, images, or stylesheets. All
      assets bundled.
- [ ] **No `WebAccess` privilege** unless absolutely necessary; even then, declared with specific
      URL patterns.
- [ ] **Export-to-image works** — renders correctly when Power BI captures it as PNG/PDF (no
      animations, no on-load delays).
- [ ] **Consistent rendering across viewport sizes** — test at 200×100 (small mobile tile) and
      1900×1000 (full canvas).
- [ ] **Source code submission** — Microsoft reviews the TypeScript before certifying. No
      embarrassing comments, no hardcoded internal URLs.
- [ ] **Public author info** in `pbiviz.json` — `author.email` will be visible.
- [ ] **Privacy policy URL** required for AppSource listing.

### Submission process

**Org-wide:** `npm run package` → upload via admin portal → Tenant settings → Organizational
visuals → Add custom visual → tenant admin approves → visual appears under "Get more visuals → My
organization."

**Microsoft AppSource (certified):** submit via Partner Center, provide source code, Microsoft
reviews (typically 2-4 weeks), approval adds the visual to AppSource with the certified checkmark.

### Common rejection reasons

- Missing `dataReductionAlgorithm` — crashes on test datasets.
- Hardcoded colors — ignores the active theme.
- Console errors on empty data — no `renderEmptyState`.
- Network access without justification.
- Mismatched `apiVersion` — submitted against a deprecated API version.

Walk the Gotchas list above before submitting; it's the same checklist reviewers use.
