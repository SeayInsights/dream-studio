#!/usr/bin/env node
// Static exec-grade quality check for a PBIR Report folder. Walks every
// visual.json and flags defects that would fail a "presentation-ready for
// C-level executives" bar. Run BEFORE shipping any change. See
// ../../../powerbi/visual-verification.md for the full exec-grade checklist
// this script enforces a static subset of.
//
// Detects:
//   - Image visuals whose container aspect ratio doesn't match the linked
//     asset (causes stretched/squashed logos or letterboxed whitespace)
//   - Title/logo/footer textboxes/images missing
//     `visualContainerObjects.background.show = false` (renders as opaque
//     white box framing on colored page backgrounds)
//   - Slicer visuals (if the engagement convention is Filter-pane-only, no
//     on-canvas slicers)
//   - Fractional pixel container dimensions (suggests user-resize artifact)
//   - $ measure with format string that doesn't compact (will overflow cards)
//   - v_footnote textboxes (shows PBI Desktop edit-mode formatting toolbar
//     in Path A captures)
//   - Body visuals whose bottom overflows the footer band (y + h > 652)
//   - Body visuals whose right edge overflows the right margin (x + w > 1256),
//     except v_refresh which is allowed at x=936 w=296 right=1232
//   - Image visuals missing visualContainerObjects.padding (PBI applies ~12px
//     default internal padding that makes logos look indented)
//   - pivotTable styling objects missing selector:{id:"default"} (PBI Desktop
//     silently falls back to theme defaults without the selector; tableEx
//     does NOT have this requirement)
//   - Visual-level filters lacking isHiddenInViewMode:true (convention:
//     user-facing filters live on page.json/report.json or slicer visuals;
//     visual-level filters are always dev artifacts and must be hidden)
//   - Stray page-navigation buttons: actionButton visualLink of type
//     PageNavigation on a VISIBLE page targeting a HIDDEN page (dead-end nav
//     leftover from template copies); any other page-nav actionButton on a
//     visible page is a warn (tab strip / page navigator is the standard nav
//     surface)
//   - Placeholder text literals ('test', 'TODO', 'TBD', 'lorem…',
//     'placeholder', DELETE_* names) anywhere in a visual's JSON
//   - pageNavigator without pages.showHiddenPages=false (Desktop edit mode
//     then shows hidden junk pages in the tab strip during reviews)
//
// Usage:
//   node scripts/exec-quality-check.mjs <Report-folder>
//
// Exit codes:
//   0  all checks passed
//   1  one or more defects found (lists them on stderr)
//
// NOT detected (requires live render or DAX evaluation):
//   - Scroll bars (only visible at render time — Path A confirms)
//   - Truncated cell values (depends on data + font metrics)
//   - Empty container space (depends on row count at runtime)
//   - PBI Desktop edit-mode caret artifacts (capture-mode quirk)

import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { join, dirname, basename } from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);

const argv = process.argv.slice(2);
// --warnings-ok: exit 0 when only warnings/infos remain (errors still fail).
// Intended for CI against templates with intentional, accepted warnings (e.g.
// deliberately data-fit fractional table sizing). Humans running this pre-ship
// should leave it off and clear warnings too.
const warningsOk = argv.includes('--warnings-ok');
const ROOT = argv.find(a => !a.startsWith('--'));
if (!ROOT) {
  console.error('usage: node exec-quality-check.mjs <Report-folder> [--warnings-ok]');
  process.exit(2);
}

if (!existsSync(ROOT)) {
  console.error(`Report folder not found: ${ROOT}`);
  process.exit(2);
}

// ---------- Asset aspect-ratio reference table ----------
// We can't read PNG dimensions without an image library, so known assets are
// hard-coded here as width/height-derived ratios. This table ships EMPTY —
// populate it with the active engagement's actual registered image assets
// (StaticResources/RegisteredResources/*.png) and their real aspect ratios.
// Get each PNG's pixel dimensions (e.g. via PowerShell's
// System.Drawing.Image or any image-inspection tool) and add an entry here;
// update it whenever an asset changes. See
// ../../../powerbi/visual-verification.md exec-grade checklist item #4.
const assetRatios = new Map([
  // ['your_logo.png', 1.65],
]);

// ---------- Defect tracking ----------
const defects = [];
// Page ids whose page.json has visibility=HiddenInViewMode; populated by
// walkPages pass 1. Errors on these pages are downgraded to warnings at
// report time — hidden pages are dev space viewers never see (they still
// warrant cleanup, hence warn not silence).
const hiddenPageIds = new Set();

function flag(severity, file, name, message) {
  defects.push({ severity, file, name, message });
}

// ---------- Per-visual checks ----------
// Section Divider pages have intentionally different chrome conventions:
// no v_footer_bar, decorative geometric background, v_logo_white sits in the
// y=660-720 band by design. Skip footer-band overflow checks for those pages.
const SECTION_DIVIDER_DISPLAY_NAME_RE = /section\s*divider/i;

function checkVisual(file, json, pageContext) {
  const v = json.visual;
  if (!v) return;
  const pos = json.position || {};
  const name = json.name || '(unnamed)';
  const isSectionDivider = pageContext?.displayName
    ? SECTION_DIVIDER_DISPLAY_NAME_RE.test(pageContext.displayName)
    : false;

  // ---- Slicer ban ----
  if (v.visualType === 'slicer') {
    flag('error', file, name, 'Slicer visual present — convention is to use the Filter pane, no on-canvas slicers');
  }

  // ---- Fractional pixel positions ----
  for (const k of ['x', 'y', 'width', 'height']) {
    const val = pos[k];
    if (typeof val === 'number' && !Number.isInteger(val)) {
      flag('warn', file, name, `position.${k} = ${val} is fractional (PBI Desktop user-resize artifact; round to integer)`);
    }
  }

  // ---- Image aspect ratio ----
  if (v.visualType === 'image') {
    const itemName = v.objects?.general?.[0]?.properties?.imageUrl?.expr?.ResourcePackageItem?.ItemName;
    if (itemName && assetRatios.has(itemName)) {
      const assetRatio = assetRatios.get(itemName);
      const w = pos.width, h = pos.height;
      if (w > 0 && h > 0) {
        const containerRatio = w / h;
        const deltaPct = Math.abs(containerRatio - assetRatio) / assetRatio * 100;
        if (deltaPct > 5) {
          flag('error', file, name,
            `image container ${w}x${h} = ${containerRatio.toFixed(2)}:1 but asset ${itemName} = ${assetRatio}:1 (${deltaPct.toFixed(1)}% off). Will stretch/letterbox.`);
        }
      }
    } else if (itemName) {
      flag('info', file, name, `image references ${itemName} but no aspect ratio recorded — add to scanner's asset table`);
    }
  }

  // ---- Transparent-or-deliberate-color container check ----
  // Textbox and image visuals must either:
  //   (a) have background.show=false (transparent, page bg shows through), OR
  //   (b) have background.show=true with an EXPLICIT non-default color set
  //       (i.e., a deliberate styling choice like a Frost title card).
  // The combination "show=true + no color set" or "show=true + color=#FFFFFF
  // with no other styling cue" is the failure mode: PBI's default white box
  // frames the content against any colored page background.
  if (v.visualType === 'textbox' || v.visualType === 'image') {
    const bgEntry = v.visualContainerObjects?.background?.[0]?.properties;
    const showVal = bgEntry?.show?.expr?.Literal?.Value;
    const explicitColor = bgEntry?.color?.solid?.color?.expr?.Literal?.Value;
    const isHiddenBg = showVal === 'false';
    const isDeliberateColor = showVal === 'true' && typeof explicitColor === 'string';
    if (!isHiddenBg && !isDeliberateColor) {
      flag('error', file, name,
        `${v.visualType} background is neither hidden (show=false) nor explicitly colored (show=true + color literal) — will render with PBI default opaque white framing`);
    }
  }

  // ---- Textbox content overflow (scroll bar) estimate ----
  // A textbox whose rendered text is taller than its container shows a
  // vertical scroll bar — the #1 zero-tolerance checklist item, previously
  // only catchable at render time. Estimate conservatively:
  //   line height  = fontSize(pt) * 4/3 px * 1.75 (PBI rich-text line box
  //                  measures ~1.7x font px; 1.5x-sized boxes scroll by 1-2px)
  //   line count   = ceil(charCount * 0.52 * fontSize(px) / innerWidth)
  //   padding      = declared visualContainerObjects.padding, else PBI's
  //                  ~8px per side default (16px vertical total)
  // Burn case: every 16/24/30px-tall chrome textbox overflowed at default
  // padding, producing a visible scroll bar. Fix pattern:
  // zero-textbox-padding.mjs + a few px of height slack.
  if (v.visualType === 'textbox' &&
      typeof pos.height === 'number' && typeof pos.width === 'number') {
    const padProps = v.visualContainerObjects?.padding?.[0]?.properties;
    const padVal = side => {
      const raw = padProps?.[side]?.expr?.Literal?.Value;
      if (raw === undefined) return 8; // PBI default ~8px per side
      const n = parseFloat(String(raw).replace(/[DL]$/, ''));
      return Number.isFinite(n) ? n : 8;
    };
    const padV = padVal('top') + padVal('bottom');
    const padH = padVal('left') + padVal('right');
    const innerW = Math.max(1, pos.width - padH);
    // Line factor: tight single/few-paragraph boxes (titles, eyebrows,
    // footers) measure ~1.7x font px in PBI's rich-text renderer — use 1.75.
    // Multi-paragraph bodies flow tighter (~1.5x + small paragraph gaps);
    // 1.75 there false-flags long instructional blocks.
    const paraCount = (v.objects?.general ?? [])
      .reduce((n, g) => n + (g.properties?.paragraphs?.length ?? 0), 0);
    const lineFactor = paraCount >= 4 ? 1.55 : 1.75;
    const paraGap = paraCount >= 4 ? 2 : 0;
    let est = 0;
    for (const gen of v.objects?.general ?? []) {
      for (const para of gen.properties?.paragraphs ?? []) {
        const runs = para.textRuns ?? [];
        const text = runs.map(r => r.value ?? '').join('');
        let pt = 0;
        for (const r of runs) {
          const fsRaw = r.textStyle?.fontSize;
          const n = parseFloat(String(fsRaw ?? '').replace(/pt|D|L/g, ''));
          if (Number.isFinite(n)) pt = Math.max(pt, n);
        }
        if (!pt) pt = 11; // PBI textbox default
        const px = pt * 4 / 3;
        const lines = Math.max(1, Math.ceil((text.length * px * 0.52) / innerW));
        // The lineFactor models inter-line leading, which only exists between
        // WRAPPED lines. A single line's rendered height is ~1.25x font px (cap
        // + descender), not 1.75x — using the wrap factor there false-flagged
        // every single-line header band (eyebrow/title/period) whose container
        // is sized to the glyph. Only apply leading when text actually wraps.
        const effFactor = lines === 1 ? 1.25 : lineFactor;
        est += lines * px * effFactor + paraGap;
      }
    }
    if (est > 0 && est + padV > pos.height + 1) {
      flag('error', file, name,
        `textbox content ~${Math.round(est + padV)}px exceeds container height ${pos.height}px — WILL show a vertical scroll bar. Zero the padding (zero-textbox-padding.mjs) and/or grow the container / shrink the font.`);
    }
  }

  // ---- v_footnote ban (edit-mode toolbar artifact) ----
  if (name === 'v_footnote') {
    flag('error', file, name, 'v_footnote textbox tends to show PBI Desktop edit-mode formatting toolbar in Path A captures; remove or replace with a cardVisual');
  }

  // ---- Bbox: bottom must not overflow the footer band ----
  // Envelope scales with the page canvas (page.json width/height) instead of
  // assuming 1280x720 — 1600-wide / tall Fit-to-width canvases were false-
  // flagged before (Client Scorecard review, 2026-07-12). Footer band is the
  // last 36px of the canvas: on 720 that's the y=690 footer row + 6px breathing
  // room above it (body envelope max y=684, unchanged from before).
  // EXCEPT footer visuals themselves (y inside the band by design), AND
  // Section Divider pages which use the footer band for decorative logos.
  const pageW = pageContext?.width ?? 1280;
  const pageH = pageContext?.height ?? 720;
  const bodyMaxY = pageH - 36;
  if (typeof pos.y === 'number' && typeof pos.height === 'number' && !isSectionDivider) {
    const bottom = pos.y + pos.height;
    // Footer visuals start in the last 60px of the canvas: covers both the
    // template convention (full-bleed v_footer_bar strip at y=660 on 720) and
    // the dashboard convention (footer text row at y=690 on 720). Anything
    // starting above that band must still clear bodyMaxY.
    const isFooterBand = pos.y >= pageH - 60;
    if (!isFooterBand && bottom > bodyMaxY) {
      flag('error', file, name,
        `bbox bottom y+h=${bottom.toFixed(1)} exceeds body envelope max y=${bodyMaxY} (overlaps footer band at y=${pageH - 30}-${pageH})`);
    }
  }

  // ---- Bbox: right edge must not overflow the right margin (x + w <= pageW-24) ----
  // EXCEPT full-bleed visuals (x=0, width>=pageW) and v_refresh (allowed at right=pageW-48).
  if (typeof pos.x === 'number' && typeof pos.width === 'number') {
    const right = pos.x + pos.width;
    const rightMargin = pageW - 24;
    const isFullBleed = pos.x === 0 && pos.width >= pageW;
    if (!isFullBleed && right > rightMargin) {
      flag('error', file, name,
        `bbox right x+w=${right.toFixed(1)} exceeds right margin x=${rightMargin} (24px outer margin convention)`);
    }
  }

  // ---- Image padding=0 requirement ----
  // PBI Desktop applies ~12px default internal padding to image visuals; logos
  // in tight headers and full-bleed footers look indented without explicit zero.
  if (v.visualType === 'image') {
    const padding = v.visualContainerObjects?.padding?.[0]?.properties;
    if (!padding) {
      flag('error', file, name,
        `image visual missing visualContainerObjects.padding block — PBI's default ~12px internal padding will make this look indented. Set top/right/bottom/left all to "0D"`);
    } else {
      for (const side of ['top', 'right', 'bottom', 'left']) {
        const v = padding[side]?.expr?.Literal?.Value;
        if (v !== '0D' && v !== '0') {
          flag('warn', file, name,
            `image visual padding.${side} = ${v ?? 'unset'} (expected "0D" — PBI's default ~12px padding makes logos look indented)`);
        }
      }
    }
  }

  // ---- Visible visual-level filter ban ----
  // Convention: NO visual-level filter is user-facing. Every entry in
  // filterConfig.filters[] needs isHiddenInViewMode:true. User-facing filters
  // belong on page.json / report.json / slicer visuals — never visible at
  // the visual level. Auto-bound field filters and deliberate-dev filters
  // (e.g., a filter pinning a card to one category) BOTH must be hidden.
  const visualFilters = json.filterConfig?.filters;
  if (Array.isArray(visualFilters)) {
    for (let i = 0; i < visualFilters.length; i++) {
      if (visualFilters[i].isHiddenInViewMode !== true) {
        flag('error', file, name,
          `filterConfig.filters[${i}] (type=${visualFilters[i].type}) is not hidden — visual-level filters must always set isHiddenInViewMode:true (convention: user-facing filters go on page/report, not visuals)`);
      }
    }
  }

  // ---- Stray page-navigation button check ----
  // Template copies can carry leftover dev-era actionButtons that
  // page-navigate to hidden dev pages. On a visible page: nav to a HIDDEN
  // page is an error (dead-end for published viewers, junk for reviewers);
  // nav to a visible page is a warn — confirm it's deliberate, the tab strip
  // / pageNavigator is the standard nav surface.
  if (v.visualType === 'actionButton' && pageContext?.visibility !== 'HiddenInViewMode') {
    for (const entry of v.visualContainerObjects?.visualLink ?? []) {
      const p = entry.properties ?? {};
      const linkType = p.type?.expr?.Literal?.Value?.replace(/'/g, '');
      if (linkType !== 'PageNavigation') continue;
      const target = p.navigationSection?.expr?.Literal?.Value?.replace(/'/g, '');
      const targetInfo = pageContext?.allPages?.get(target);
      if (targetInfo?.hidden) {
        // Deliberate bonus-page nav is a sanctioned pattern. The DEFECT is
        // the unfinished leftover: placeholder text ('test' etc.) is flagged
        // as its own error by the placeholder check, so a clean, properly-texted
        // button to a hidden page is a warn (confirm intended), not an error.
        flag('warn', file, name,
          `actionButton on visible page navigates to HIDDEN page '${targetInfo.displayName}' — confirm deliberate (bonus-page pattern); placeholder text on the button would error separately`);
      } else {
        flag('warn', file, name,
          `actionButton page-navigates to '${targetInfo?.displayName ?? target}' — confirm deliberate; tab strip / pageNavigator is the standard nav surface`);
      }
    }
  }

  // ---- Placeholder text literal check ----
  // 'test' in a button state, DELETE_-prefixed measures, lorem ipsum — all
  // shipped-by-accident artifacts. Walk every Literal in the visual JSON.
  {
    const PLACEHOLDER_RE = /^'(test|todo|tbd|xxx+|placeholder|lorem\b.*)'$/i;
    const stack = [json];
    const seen = new Set();
    while (stack.length) {
      const node = stack.pop();
      if (!node || typeof node !== 'object' || seen.has(node)) continue;
      seen.add(node);
      const lit = node.Literal?.Value;
      if (typeof lit === 'string' &&
          (PLACEHOLDER_RE.test(lit) || /^'?DELETE_/.test(lit))) {
        // Hidden pages are dev space pending cleanup — warn, don't fail the gate.
        const sev = pageContext?.visibility === 'HiddenInViewMode' ? 'warn' : 'error';
        flag(sev, file, name,
          `placeholder literal ${lit} — dev artifact; replace or remove before shipping`);
      }
      for (const k of Object.keys(node)) {
        if (typeof node[k] === 'object') stack.push(node[k]);
      }
    }
  }

  // ---- pageNavigator must exclude hidden pages ----
  // Without an explicit pages.showHiddenPages=false, the tab strip lists
  // hidden dev/junk pages in PBI Desktop edit mode — exactly where a reviewer looks.
  if (v.visualType === 'pageNavigator') {
    const pagesProps = v.objects?.pages?.[0]?.properties;
    const showHidden = pagesProps?.showHiddenPages?.expr?.Literal?.Value;
    if (showHidden !== 'false') {
      flag('error', file, name,
        `pageNavigator lacks pages.showHiddenPages=false — hidden dev pages appear in the tab strip during Desktop edit-mode review`);
    }
  }

  // ---- pivotTable selector requirement ----
  // PBI Desktop silently falls back to theme defaults when a pivotTable
  // styling object's FIRST (default) entry lacks selector:{id:"default"}.
  // Subsequent entries in the array are legitimately selector-less when they
  // hold per-property overrides like rowHeaders.showExpandCollapseButtons or
  // conditional formatting entries with metadata-based selectors. Only the
  // [0] (default styling) entry is checked here.
  // Diagnosed 2026-05-13; see feedback_pbir_pivottable_requires_selector.md.
  if (v.visualType === 'pivotTable') {
    const objects = v.objects || {};
    // Only visual-styling objects need selectors. `subTotals` is a behavioral
    // toggle (rowSubtotals/columnSubtotals on/off), styled via `total`.
    const styled = ['grid', 'columnHeaders', 'rowHeaders', 'values', 'total'];
    for (const obj of styled) {
      const entries = objects[obj];
      if (!Array.isArray(entries) || entries.length === 0) continue;
      // Only the first entry — that's the "default styling" target.
      const first = entries[0];
      const sel = first?.selector;
      if (!sel || sel.id !== 'default') {
        flag('error', file, name,
          `pivotTable.${obj}[0] missing selector:{id:"default"} — PBI Desktop will silently fall back to theme defaults for this property block`);
      }
    }
  }
}

// ---------- Walk Report folder ----------
// Walk page-by-page so we can pass pageContext (displayName) into checkVisual.
// pages/<id>/page.json holds displayName; pages/<id>/visuals/<id>/visual.json
// are the visuals on that page.
function walkPages(reportRoot) {
  const pagesDir = join(reportRoot, 'definition', 'pages');
  if (!existsSync(pagesDir)) return;

  // Pass 1: page registry (id -> displayName/hidden/size) so per-visual checks
  // can resolve nav targets and scale envelope rules to the actual canvas.
  const allPages = new Map();
  for (const pageEntry of readdirSync(pagesDir)) {
    const pageJsonPath = join(pagesDir, pageEntry, 'page.json');
    if (!existsSync(pageJsonPath)) continue;
    try {
      const pageJson = JSON.parse(readFileSync(pageJsonPath, 'utf8'));
      allPages.set(pageEntry, {
        displayName: pageJson.displayName || '',
        hidden: pageJson.visibility === 'HiddenInViewMode',
        width: pageJson.width ?? 1280,
        height: pageJson.height ?? 720,
        visibility: pageJson.visibility,
      });
      if (pageJson.visibility === 'HiddenInViewMode') hiddenPageIds.add(pageEntry);
    } catch { /* ignore unparseable page.json */ }
  }

  for (const pageEntry of readdirSync(pagesDir)) {
    const pageDir = join(pagesDir, pageEntry);
    let st;
    try { st = statSync(pageDir); } catch { continue; }
    if (!st.isDirectory()) continue;

    // Load page context.
    const reg = allPages.get(pageEntry);
    const pageContext = reg
      ? { ...reg, id: pageEntry, allPages }
      : null;

    const visualsDir = join(pageDir, 'visuals');
    if (!existsSync(visualsDir)) continue;
    for (const visualEntry of readdirSync(visualsDir)) {
      const visualJsonPath = join(visualsDir, visualEntry, 'visual.json');
      if (!existsSync(visualJsonPath)) continue;
      let json;
      try { json = JSON.parse(readFileSync(visualJsonPath, 'utf8')); }
      catch (e) { flag('error', visualJsonPath, '?', `parse failed: ${e.message}`); continue; }
      checkVisual(visualJsonPath, json, pageContext);
    }
  }
}

walkPages(ROOT);

// Downgrade hidden-page errors to warnings (dev space, viewers never see it).
for (const d of defects) {
  if (d.severity === 'error' &&
      [...hiddenPageIds].some(id => d.file.includes(`${id}`))) {
    d.severity = 'warn';
    d.message += ' [hidden page — warn-only]';
  }
}

// ---------- Report ----------
const errors = defects.filter(d => d.severity === 'error');
const warns  = defects.filter(d => d.severity === 'warn');
const infos  = defects.filter(d => d.severity === 'info');

function fmt(d) {
  const rel = d.file.startsWith(ROOT) ? d.file.slice(ROOT.length + 1) : d.file;
  return `  [${d.severity}] ${rel}\n    visual: ${d.name}\n    ${d.message}`;
}

if (errors.length) {
  console.error(`\n❌ ${errors.length} error(s):`);
  for (const d of errors) console.error(fmt(d));
}
if (warns.length) {
  console.error(`\n⚠️  ${warns.length} warning(s):`);
  for (const d of warns) console.error(fmt(d));
}
if (infos.length) {
  console.error(`\nℹ️  ${infos.length} info note(s):`);
  for (const d of infos) console.error(fmt(d));
}

if (errors.length === 0 && warns.length === 0) {
  console.log(`✓ exec-quality-check: ${defects.length === 0 ? 'clean' : `${infos.length} info note(s) only`}`);
  process.exit(0);
}

if (errors.length === 0 && warningsOk) {
  console.log(`✓ exec-quality-check: 0 errors; ${warns.length} warning(s) tolerated (--warnings-ok)`);
  process.exit(0);
}

console.error(`\nrun fixes before shipping. See ../../../powerbi/visual-verification.md's exec-grade checklist for guidance.`);
process.exit(1);
