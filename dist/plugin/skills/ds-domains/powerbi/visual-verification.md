# Visual Verification — Two-Path Self-Verification

All `scripts/...` and `templates/...` paths in this file are relative to the power-platform
mode's own directory: `canonical/skills/domains/modes/power-platform/` (sibling to that mode's
`SKILL.md` and `version-detection.sh`) — not to this `powerbi/` domain folder.

Self-verify Power BI report changes via two complementary paths before declaring a layout or
visual-JSON change done. Both paths feed a multimodal `Read` so the agent verifies its own work
instead of asserting it looks right from the JSON alone.

- **Path B — static layout preview** (`scripts/preview-layout.mjs`): fast (~3s), no credentials,
  deterministic. Reads `visual.json` bounding boxes and renders a wireframe mock — rectangles,
  type chips, bound-field names. Does **not** show real colors, real data, or real chart/custom-
  visual rendering. The inner-loop default for layout iteration.
- **Path A — live Power BI Desktop screenshot** (`scripts/screenshot-pbi-desktop.ps1`): slower
  (~20-45s), requires Power BI Desktop installed and (for the very first launch) a signed-in
  session. Captures the real rendered report off-screen — real theme, real DAX values, real
  chart/custom-visual output. The approval-gate render before surfacing work to the operator or
  reviewer.

**The operator/reviewer is the approver, not the verifier.** Work should never reach them with a
defect either path's checklist would have caught.

## When to use which

| | Path B (static layout) | Path A (live Desktop) |
|---|---|---|
| Stack | Node + Playwright | PowerShell + System.Drawing (Win32 PrintWindow) |
| Input | A `*.Report` folder | A `.pbip` file |
| Output | PNG of every visual's rectangle at correct x/y/w/h, with type chip, title, bound fields | PNG of the rendered report canvas |
| Speed | ~3 seconds | ~20s warm / ~45s cold |
| Credentials | None | Power BI Desktop installed; first launch may need a signed-in session |
| Determinism | Same input → same output | Captures whatever actually renders |
| Sees real data? | No | Yes |
| Sees real theme/colors? | No — fixed wireframe mock chrome | Yes |
| Sees custom-visual (pbiviz) rendering? | No — rectangle + type chip only | Yes |
| Can target a specific page? | Yes, `--page` | Yes, `-PageId` |

### Use Path B by default for any layout question

- "Did I move the visual to the right place?"
- "Is anything overlapping after the rearrange?"
- "Is the table cropped past the canvas?"
- "Is the title still visible?"
- "Did I bind the right fields?"
- "Is the page chrome (logo, divider, header) intact after my edit?"
- A quick sanity check after a bulk edit across multiple `visual.json` files.

It's deterministic, fast, free, and answers layout-correctness questions in the large majority of
cases.

### Use Path A when the question is about rendered output

- "Did the theme apply correctly? Are the colors right?"
- "Does the conditional formatting on this column actually highlight the values I expect?"
- "Is the data correct? Does the measure return what I expect?"
- "Is the custom visual rendering its actual TypeScript output?" (Path B draws a generic
  placeholder for any visual type it doesn't recognize, including custom visuals.)
- "How does it look at full canvas size?"
- "Did saving from Desktop break anything that doesn't show up in the JSON?"

Use Path A sparingly — it's materially more expensive per iteration (cold start, process
lifecycle, image-token cost) than Path B.

### Combining the two

A reasonable loop for a substantive visual rework:

1. Edit `visual.json`.
2. Run Path B to confirm position/binding.
3. Loop 1–2 until layout is right.
4. Run Path A once at the end to confirm theme/data/render.
5. If Path A reveals an issue Path B couldn't see, fix and re-run Path A.

Don't run Path A on every iteration — most edits are layout-only, and its cost is roughly an
order of magnitude higher than Path B's.

### Context budget — every Path A run costs multimodal tokens

Each Path A round-trip can write both a full-window capture and a cropped canvas-only PNG.
Reading both costs real tokens that stay in conversation history through every subsequent turn —
image cost is unrecoverable. Rules of thumb:

- **Read only the `_canvas.png` crop** in the inner verification loop. The full-window capture
  (with Desktop's ribbon/pane chrome) is for diagnostic moments only.
- **Pass `-CanvasOnly`** to the screenshot script when only the canvas is needed — it deletes the
  full-window capture after cropping.
- **Pass `-HighRes` only when pixel-precision matters** (diagnosing a 4px overflow, a 0.5pt font
  weight question). The default resolution is legible for ordinary layout/typography/color
  review.
- **Cap visible Path A iterations per page per conversation** (roughly 10). Past that, image
  context dominates working context — recommend a fresh conversation.
- **Skip intermediate reads.** When iterating, run Path A → adjust → run again, but only `Read`
  the final canvas before declaring done.

## The troubleshooting loop

When a `visual.json` has just been edited, or a user reports a visual issue, follow this 7-step
loop.

### 1. Identify the page and visual(s) in scope

Every `visual.json` lives at `<Report>/definition/pages/<pageId>/visuals/<visualId>/visual.json`.
From an edited file path you can derive both. If the user reports an issue without a path, ask
which page, or grep `pages/*/visuals/<id>/visual.json` for the visual `name` they mentioned.

### 2. Validate before rendering

```bash
node scripts/validate-visual-json.mjs "<...>.Report" --page <pageId>
```

Catches: missing `position` or non-numeric x/y/w/h, missing `visual.visualType`, a `name` field
that doesn't match its folder, off-canvas warnings, plain JSON parse errors. Fix schema breaks
first — there's no point rendering a broken JSON.

### 3. Exec-quality scan

```bash
node scripts/exec-quality-check.mjs "<...>.Report"
```

Catches static defects a reviewer calls out repeatedly: opaque white textbox/image container
backgrounds, on-canvas slicers (if the convention is Filter-pane-only), mismatched image aspect
ratios, fractional pixel positions from a Desktop mouse-resize, missing `pivotTable` selectors,
visible visual-level filters. **Must be clean before Path A.** See `pbir-gotchas.md` and
`quality-tiers-antipatterns.md` for the mechanisms behind each check.

### 4. Preview (Path B, fast)

```bash
node scripts/preview-layout.mjs "<...>.Report" --page <pageId> --out .preview/iter<N>-<pageId>.png
```

Number iterations (`iter1`, `iter2`, ...) so failed attempts aren't overwritten.

### 5. Read and decide

`Read` the PNG. Sanity-check: are visuals where expected? Any overlap? Is the title visible? Do
bound fields match the ask?

- **Layout correct and the change was layout-only** → done. Cite the PNG path.
- **Layout wrong** → propose **one** minimal JSON edit and loop back to step 2. Don't shotgun
  multiple changes at once — small, reversible edits are easier to verify.
- **The change touched theme/colors/data/conditional formatting/custom visuals** → Path B can't
  answer this. Run Path A as a follow-up.

### 6. Approval gate (Path A, real render)

Once Path B says layout looks right, or the question needs real colors/DAX/charts:

```powershell
powershell -File scripts/screenshot-pbi-desktop.ps1 `
    -Pbip "<file>.pbip" `
    -Out .preview/approval-<pageId>.png `
    -PageId "<pageId>" `
    -AssumeLoggedIn `
    -CanvasOnly
```

**Set the tool timeout to at least 360000 ms (6 minutes).** The script's own render hard cap is
300s; a shorter tool timeout kills the wrapper mid-run and orphans the spawned Power BI Desktop
process (the next run's recovery logic cleans it up, but that run's capture is lost). `Read` the
resulting PNG and walk it through the Exec-Grade Checklist below. **If any item fails, fix and
re-render. Do not declare done.**

### 7. Stop after 3 iterations

If the visual still looks wrong after 3 self-verification passes, **stop and surface the PNGs and
diagnosis to the operator/reviewer.** Three failures in a row usually means one of:

- The static preview is missing the dimension that's actually broken (a data issue — run Path A).
- The mental model of the fix is wrong — a human's eyes are faster than another speculative edit.
- There's a Power BI rendering quirk that can't be fixed from JSON alone.

Don't grind silently. Three is the cap.

## Path A — how it works

The live screenshot script (`scripts/screenshot-pbi-desktop.ps1`) does the following, end to end:

1. **Resolves Power BI Desktop's path** — explicit parameter > `$env:PBI_DESKTOP_EXE` > `.pbip`
   file association > App Paths registry > known install locations > `PATH`. Handles both the
   classic installer and the Microsoft Store package.
2. **Snapshots existing Power BI Desktop PIDs** — any process running before launch is sacred and
   is never touched, even if the user has other projects open.
3. **Applies reversible pre-launch JSON edits** — `pages/pages.json`'s `activePageName` set to the
   requested page, `report.json`'s `outspacePane.expanded` set to `false` (collapses the filter
   pane for more canvas). Originals are captured in memory and on disk for crash recovery.
4. **Launches Power BI Desktop**, waits for the window it spawned (ignoring any pre-existing
   session).
5. **Three-stage adaptive wait:** a title gate (file loaded — window title contains the `.pbip`
   stem, max 60s), a pixel-stability poll (a 16×9 fingerprint grid, mean-delta threshold, several
   consecutive stable frames, max 4 min), and a hard cap on total elapsed time (max 5 min).
6. **Off-screen capture** — moves the window to `(-32000, -32000)` so it never visibly sits over
   the user's other work, resizes it to a deterministic size, then captures via `PrintWindow` with
   `PW_RENDERFULLCONTENT`. (Not `ShowWindow(SW_HIDE)` — that crashes Power BI Desktop's
   WPF/DirectX renderer.)
7. **Auto-closes without a save prompt** — force-kills only the PIDs identified as spawned by this
   run. Any pre-existing session is left untouched. Runs in a `finally` block, so every exit path
   (success, timeout, capture error) closes the spawned instance.
8. **Restores the original JSON** in the same `finally` block.
9. **Crash recovery** — a stale edit-lock file from a previous crashed run restores the original
   report JSON on the next run's start; an orphan-PID lock records every spawned PID so a prior
   run that was hard-killed (tool timeout, Ctrl+C) gets its leaked Power BI Desktop instance
   cleaned up by the next run.
10. **Concurrency safety** — a machine-wide named mutex serializes Path A: one capture at a time
    across every session on the machine. A second capture queues up to `-CaptureGateWaitSec`
    (default 300s), then exits with a retryable gate-timeout code — that's not a failure, just
    contention.

### Honest caveats

- The window briefly flashes at its default location for ~1-2s before being moved off-screen —
  unavoidable until Power BI Desktop's WPF init tolerates `WindowStyle Hidden` (currently it
  crashes the app in that state).
- The captured frame includes Power BI Desktop's edit-mode chrome (ribbon, page tabs,
  Visualizations/Data panes) unless cropped to canvas-only.
- Modal dialogs (auth refresh, error popups) aren't auto-detected; if Desktop hangs on one, the
  script exits with a render-timeout code after 5 minutes.
- Concurrent sessions queue rather than parallelize — the machine-wide gate means N sessions
  running Path A take N × capture-time.
- Path A captures **edit mode**, not published view. Drill-down icons on a matrix, bookmark-driven
  state, slicer interaction, drill-through navigation, and tooltip pages are all invisible in edit
  mode — see "Blind spots" below.

## What the layout preview shows

Per visual on the page:

- A rectangle at the visual's actual `position.{x,y,width,height}` (canvas defaults 1280×720, read
  from `page.json`).
- A type chip ("tableEx", "cardVisual", "azureMap", etc.).
- The title text (or the visual's `name` if `visualContainerObjects.title.show=false`).
- Bound field names from `visual.query.queryState.*.projections[].displayName`.
- Type-appropriate filler — a striped grid for `tableEx`/`pivotTable`/`matrix`, a slicer chevron,
  a big-number placeholder for `cardVisual`, a diagonal-striped pattern for maps, a dashed "IMG"
  box for `image`, bar-chart placeholder bars for chart types, and so on. A custom (pbiviz) visual
  renders as an explicit "not rendered in Path B" badge with its visual-type string — it does not
  fall through to a misleading stock-chart mock even when its name contains a substring like
  "scatter" or "slicer".

This is **not** a data-faithful render — it's a wireframe. Treat it like a layout mock, not a
preview of the finished report. The mock chrome uses a fixed neutral palette; it is not yet
brand-aware (rendering the active brand profile's colors in the preview is a possible future
enhancement, not current behavior).

### `visualType` taxonomy

| `visualType` (pattern) | Rendered as |
|---|---|
| `tableEx` / `pivotTable` / `matrix` | Striped grid: header row with column-name cells (from bound fields), placeholder body rows |
| `card` / `cardVisual` | Soft background, big-number placeholder, centered |
| `slicer` / `advancedSlicer` | Bordered box, label from first bound field, a chevron |
| `azureMap` / `shapeMap` / `filledMap` / `map` | Diagonal striped pattern, "MAP" centered |
| `image` | Dashed border, "IMG" centered, white background |
| `shape` | Solid fill with rounded corners |
| `*chart` / `*column` / `*bar` / `*line` / `*area` / `*pie` / `*donut` / `*scatter` / `*combo` / `*funnel` / `*gauge` / `*kpi` / `*treemap` | Axis lines + stepped placeholder bars |
| Custom/organizational visual (a GUID/hash embedded in the `visualType` string) | Explicit "custom visual — not rendered in Path B" badge, detected **before** stock-pattern matching so a custom visual named e.g. `orgVelocityScatter` doesn't get mis-rendered as a stock scatter chart |
| anything else | Soft background, raw `visualType` string shown verbatim |

If a new stock or custom visual type starts showing up frequently and the unknown-type render
isn't useful, add a regex branch to `renderFiller()` in `scripts/preview-layout.mjs`, the matching
CSS to `templates/preview.html.tmpl`, and a row to this table.

## Exec-grade checklist

Path A captures must be inspected against this checklist before surfacing them to the
operator/reviewer. The bar is presentation-ready for executive review on every affected page, not
just the page being actively worked on.

**How to apply:** render Path A on every affected page AND `Read` each PNG. Scan against this
checklist. If any item fails, fix and re-render. Do not declare done until all pass.

### 1. Scroll bars — zero tolerance

- [ ] No vertical scroll bar on any image visual (banner, logo, footer)
- [ ] No vertical scroll bar on any textbox (title, footnote, label)
- [ ] No horizontal scroll bar on tables — all columns visible, no truncated headers
- [ ] No scroll bar on small inline elements

### 2. Truncated text — zero tolerance

- [ ] No ellipsis on card values (`$252...` is a hard fail)
- [ ] No truncated table cell values, especially right-aligned `$` columns
- [ ] No clipped column headers
- [ ] Names and labels fully visible

### 3. Container backgrounds — every textbox/image

- [ ] Logo and title/footnote image and text containers: `visualContainerObjects.background.show
      = false` (they should bleed transparent, not frame in opaque white)
- [ ] `cardVisual` containers: keep `background.show=true` with an explicit color — cards should
      pop against the page background, unlike chrome text/images

### 4. Aspect ratios — image containers must match their asset

Verify every image visual's `position.width / position.height ≈` the actual source asset's
aspect ratio. Tolerance ±5%. An off-ratio container with Fit/Fill scaling produces a stretched
logo or letterboxed whitespace. Maintain the current engagement's actual registered-asset
dimensions as a lookup table in `exec-quality-check.mjs` (see that script's `assetRatios` map) —
it ships empty here since no assets are bundled with this skill; populate it from the active
engagement's `StaticResources/RegisteredResources/`.

### 5. Empty space inside visual containers

- [ ] No empty area below table rows (container height ≈ data height + small padding)
- [ ] No empty space inside a textbox container beyond font-height headroom
- [ ] A visual with N rows × known row height should have a container ≈ that height, not the
      full available body envelope

### 6. Edit-mode artifacts

Edit-mode captures (Path A) can show chrome that won't appear in published view:

- [ ] No formatting toolbar overlay on a textbox (indicates it has focus)
- [ ] No blinking caret next to titles or labels
- [ ] No "..." menu chiclets near the top of visuals

If present: consider replacing a static textbox with a `cardVisual` bound to a string measure, or
accept the artifact only if confirmed to not appear in published view.

### 7. Number formatting — exec readability

- [ ] `$` values display compactly (e.g. `$252M`, never a raw unformatted integer overflowing a
      card)
- [ ] Tables can show full precision — more cell width is available there
- [ ] Sentiment colors (if the active brand profile's `sentiment_policy` is `accent-coded`) match
      that profile's `positive`/`negative` hexes; under `neutral` policy, direction is glyph +
      weight only, never a second color

### 8. Slicers — follow the engagement's on-canvas-slicer convention

- [ ] If the convention is Filter-pane-only (confirm with the operator, don't assume): no slicer
      visuals on the canvas; page-level filters via `page.json`'s `filterConfig.filters[]`
- [ ] If an on-canvas slicer was explicitly requested, it's an accepted, intentional deviation —
      the static scanner will still flag it; that's expected

### 9. Alignment

- [ ] Page title positioned per the page-chrome convention (left rail or top-left header)
- [ ] Row labels aligned adjacent to the data they describe
- [ ] Card titles and values centered within cards
- [ ] Table column headers and cells aligned per column type (`$` right, text left)

### 10. Template-copy hygiene — navigation & dev artifacts

Reports scaffolded by copying another report inherit dev-era navigation and placeholder junk:

- [ ] No `actionButton` on a visible page that page-navigates to a hidden page, unless confirmed
      intentional — the tab strip / page navigator is the standard nav surface a client should see
- [ ] No placeholder literals anywhere: `'test'` button states, `TODO`, `lorem`, `DELETE_*`
      measure bindings
- [ ] Every `pageNavigator` sets `pages.showHiddenPages = false` — otherwise hidden dev pages
      appear in the tab strip during edit-mode review
- [ ] Hidden pages orphaned by removed nav buttons are flagged for deletion, not left indefinitely
      "hidden"

All of the above are enforced statically by `exec-quality-check.mjs` (hidden-page findings
downgrade to warnings there).

### 11. Page-level

- [ ] Page background is not pure white if the active profile specifies a page background color
      — use it for depth
- [ ] No large empty area below visuals before the footer (a gap over ~200px suggests visuals
      should be repositioned or another visual added)
- [ ] Page tabs at the bottom show the correct active page

### What to do if a check fails

1. **Don't ship.** Fix it. Re-render. Re-check.
2. **Add to `pbir-gotchas.md`** if the fix is a non-obvious PBIR convention worth capturing.
3. **Update `exec-quality-check.mjs`** if the defect is detectable statically from JSON.

### Path A as the approval gate, not Path B alone

Path B is bbox-only — it misses image padding, theme colors, container styling, real data fit,
and font rendering. Settling for Path B alone on a styling-sensitive change is not acceptable.

- Visual.json layout/style edits → Path A required before declaring done.
- TMDL / measure / theme-only edits with no visual.json change → Path B sufficient.
- Skill-doc edits only → no screenshot needed.

## Blind spots — what each path cannot see

Knowing which blind spot applies tells you when to escalate.

### Path B (static layout preview)

Path B reads bounding boxes from `visual.json` and draws them. It does not execute Power BI, so
it cannot see:

- Real theme colors — every visual renders with the same fixed mock chrome.
- Real data — no DAX evaluation; values are placeholders.
- Image internal padding — Power BI's default ~12px padding around a rendered image is invisible
  here; a logo that looks "indented" in Desktop looks fine in Path B.
- Chart rendering — bar/line/column charts render as generic placeholder bars.
- Container background color application.
- Conditional formatting / measure-driven colors — cells show a placeholder color, not the
  resolved one.
- Custom (pbiviz) visual TypeScript output — only the bounding rectangle and bound field names.

**Escalate to Path A when** the question is about colors, data fit, image padding, custom-visual
rendering, or whether a styling property actually took effect.

### Path A (live Power BI Desktop screenshot)

Path A captures Desktop in **edit mode**. It does not capture:

- Drill-down icons (`+`/`−`) on matrix visuals — they only appear in published view / app reader.
  Path A always shows a fully-expanded matrix regardless of `expansionStates.isCollapsed`.
- Slicer interaction state or bookmark-driven state.
- Drill-through navigation or tooltip pages.
- Tall / non-standard-height canvases render at Desktop's persisted zoom and scroll position (not
  stored in the PBIR source), so a very tall Fit-to-width page may capture only a slice of the
  canvas. Use Path B for full-page structural review of tall pages; treat tall-page Path A
  captures as spot checks of whatever region happens to be visible.

**Escalate beyond Path A when** the question is about published-only behavior — publish to a
workspace and screenshot, or toggle Desktop's View → Reading View manually.

### Exec-quality scanner (`exec-quality-check.mjs`)

A JSON-level static analyzer. It parses `visual.json`/`page.json` and checks structural
properties — it does not rasterize anything, so it cannot see anything that only emerges at
render time:

- SVG text overflow inside a custom (pbiviz) visual's own rendering.
- Missing layout features in a custom visual compared to an intended mockup.
- Format-string mismatches (a number rendering `20.25%` when the intent was `+20.2%`).
- Cross-visual bleed-through (a lower-z-order textbox showing through gaps between tiles).
- Sentiment-color drift inside a pbiviz's own resolved rendering.
- An auto-bound visual title placeholder Power BI may still emit despite `title.show=false`.
- Header/footer band positioning that overlaps a custom visual in ways the per-visual bbox check
  doesn't catch.

**Mitigation:** Path A's multimodal `Read` is the catch-all. A clean `exec-quality-check` scan is
necessary but not sufficient for declaring done. After it passes and Path A succeeds, scan the
canvas image specifically for: caption text fully visible inside every tile, column headers
present where the mockup has them, no stray fragments in tile gaps, number formats matching the
mockup's precision, sentiment arrows/colors matching the value's sign, and label-tile grouping
matching the mockup's structure. The image-diff tool below (`compare-render.mjs`) is the
pixel-level safety net for what this scanner structurally can't see.

## Render-level regression checking

Once a render is approved, save it as a baseline (e.g. `.preview/approval-<page>_canvas.png`).
Diff future captures against it to catch silent regressions:

```bash
node scripts/compare-render.mjs <candidate.png> <baseline.png> [--max-diff-pct 0.5] [--threshold 0.1]
```

This flags *that* something changed in pixels (clipped text, color drift, a layout shift); the
multimodal `Read` of the diff image tells you *what*.

## Honest limitations

- Path B doesn't render data, theme colors, or chart shapes — it's a wireframe, not a faithful
  render.
- Path B can't render a custom visual's actual TypeScript output — only its bounding rectangle
  and bound fields. For real custom-visual output, use Path A or `npm start` sideload (see
  `custom-visuals.md`).
- Path A captures with Desktop's chrome visible unless cropped to canvas-only.
- Path A briefly flashes the Desktop window on launch before moving it off-screen.
- Path A doesn't auto-detect modal dialogs; a hung modal surfaces as a render-timeout after 5
  minutes.
- Path A can't clean up after a hard kill of the script process itself (tool timeout, Ctrl+C on
  some hosts) — the spawned Desktop instance survives until the next run's orphan-PID recovery.
  Always pass a tool timeout ≥ 360s so this stays rare.
- Concurrent sessions queue rather than parallelize.
- Path A captures edit mode, not published view.

## Resources in this domain

| Path | What it is |
|---|---|
| `scripts/preview-layout.mjs` | Node + Playwright static layout previewer (Path B). |
| `scripts/validate-visual-json.mjs` | ajv-based pre-flight schema validator. |
| `scripts/exec-quality-check.mjs` | JSON-level static defect scanner (see `pbir-gotchas.md` for the mechanisms it enforces). |
| `scripts/check-page-chrome-drift.mjs` | Detects drift in repeated chrome visuals (logo, title, refresh indicator, footer) across pages. |
| `scripts/hide-visual-filters.mjs` | Bulk-sets `isHiddenInViewMode:true` on every visual-level filter already in a `filterConfig`. |
| `scripts/preemptive-hide-fields.mjs` | Pre-creates hidden filter entries for bound fields PBI hasn't persisted yet. |
| `scripts/post-save.mjs` | Umbrella pipeline chaining the above four scripts in order. Run after every Power BI Desktop save session. |
| `scripts/round-positions.mjs` | Rounds fractional position coordinates from a Desktop mouse-resize to integers. |
| `scripts/compare-render.mjs` | Pixel-diff a candidate render against an approved baseline. |
| `scripts/bulk-transparent-bg.mjs` | Sets `background.show=false` on textbox/image visuals by name, in bulk. |
| `scripts/zero-textbox-padding.mjs` | Zeroes textbox internal padding so short containers don't clip/scroll text. |
| `templates/preview.html.tmpl` | HTML scaffold with the mock-chrome CSS used by `preview-layout.mjs`. |
| `references/schemas/visual.schema.json` (ported as `schemas/visual.schema.json`) | Local, intentionally permissive PBIR visual schema for offline validation. |
| `scripts/screenshot-pbi-desktop.ps1` | Path A — live Power BI Desktop screenshot. |
| `scripts/edit-report-for-capture.ps1` | Reversible JSON edits used by Path A (dot-sourced helper). |
