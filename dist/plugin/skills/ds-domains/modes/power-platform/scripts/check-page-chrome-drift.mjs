#!/usr/bin/env node
// Detect drift in repeated page-chrome visuals across a PBIR Report.
//
// A multi-page exec report commonly repeats `v_logo`, `v_title`,
// `v_refresh`, and `v_footer_bar` on every body page (KPI Overview, Detail
// Table, Trend Analysis, Header/Footer Master, etc.). If those visuals
// diverge across pages (different position, schema version, color, filter
// config), the report looks inconsistent and the divergence is invisible
// until you flip between pages.
//
// Most common cause: PBI Desktop bumps $schema and rewrites visual.json
// on save, but only for pages the user touches. Pages last touched
// programmatically stay on the old schema. This script flags that.
//
// Usage:
//   node scripts/check-page-chrome-drift.mjs <Report-folder>
//
// Exit codes:
//   0  no drift detected
//   1  drift detected (details on stderr)
//   2  invalid invocation

import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { join, basename } from 'node:path';

const ROOT = process.argv[2];
if (!ROOT) {
  console.error('usage: node check-page-chrome-drift.mjs <Report-folder>');
  process.exit(2);
}
if (!existsSync(ROOT)) {
  console.error(`Report folder not found: ${ROOT}`);
  process.exit(2);
}

// Repeated chrome visual names we expect to match across pages.
const CHROME_NAMES = ['v_logo', 'v_title', 'v_refresh', 'v_footer_bar'];

// Page-level visuals that legitimately differ per page (cover-style hero
// logo on the KPI Overview vs. small logo on detail pages). Ignored.
const VARIANT_NAMES = ['v_logo_hero', 'v_logo_white', 'v_page_title', 'v_section_title'];

// Properties on each chrome visual we compare across pages. Anything outside
// this list is allowed to differ (e.g., tabOrder is per-page).
const COMPARED = {
  position: ['x', 'y', 'z', 'width', 'height'],
  schema: true,
  visualType: true,
  // For v_refresh specifically: it should have a filterConfig that suppresses
  // the visual when the Refresh Display measure is blank. We compare the
  // presence of filterConfig.filters[0] but not the exact filter name (which
  // is a UUID).
  hasFilterConfig: true,
  // For image visuals: padding=0 block must be present.
  hasZeroPadding: true,
};

// ---------- Walk ----------
const pagesDir = join(ROOT, 'definition', 'pages');
if (!existsSync(pagesDir)) {
  console.error(`pages/ folder not found at ${pagesDir}`);
  process.exit(2);
}

// Each chrome name -> array of { page, shape } observations across pages.
const observations = Object.fromEntries(CHROME_NAMES.map(n => [n, []]));

for (const pageEntry of readdirSync(pagesDir)) {
  const pagePath = join(pagesDir, pageEntry);
  let st;
  try { st = statSync(pagePath); } catch { continue; }
  if (!st.isDirectory()) continue;

  const visualsDir = join(pagePath, 'visuals');
  if (!existsSync(visualsDir)) continue;

  for (const visualEntry of readdirSync(visualsDir)) {
    const visualPath = join(visualsDir, visualEntry);
    if (!CHROME_NAMES.includes(visualEntry)) continue;

    const visualJsonPath = join(visualPath, 'visual.json');
    if (!existsSync(visualJsonPath)) continue;

    let json;
    try { json = JSON.parse(readFileSync(visualJsonPath, 'utf8')); }
    catch (e) {
      console.error(`parse failed: ${visualJsonPath}: ${e.message}`);
      process.exit(1);
    }

    const shape = extractShape(json);
    observations[visualEntry].push({ page: pageEntry, shape, path: visualJsonPath });
  }
}

// ---------- Compare ----------
const driftFindings = [];

for (const name of CHROME_NAMES) {
  const obs = observations[name];
  if (obs.length === 0) continue;
  if (obs.length === 1) continue; // only one page has this chrome — nothing to compare

  const reference = obs[0];
  for (let i = 1; i < obs.length; i++) {
    const cmp = obs[i];
    const diffs = diffShape(reference.shape, cmp.shape);
    if (diffs.length > 0) {
      driftFindings.push({
        name,
        referencePage: reference.page,
        comparedPage: cmp.page,
        diffs,
        comparedPath: cmp.path,
      });
    }
  }
}

// ---------- Report ----------
if (driftFindings.length === 0) {
  console.log(`✓ page-chrome-drift: ${CHROME_NAMES.join(', ')} consistent across ${pageCount()} page(s)`);
  process.exit(0);
}

console.error(`\n❌ ${driftFindings.length} page-chrome drift finding(s):\n`);
for (const f of driftFindings) {
  console.error(`  ${f.name}: ${f.referencePage} ≠ ${f.comparedPage}`);
  for (const d of f.diffs) {
    console.error(`    ${d}`);
  }
  console.error(`    file: ${f.comparedPath.replace(ROOT, '<Report>')}\n`);
}
console.error(`Fix by copying the reference page's visual.json shape to the divergent page(s).`);
console.error(`Most common root cause: PBI Desktop bumped $schema on one page during a save without touching the others.`);
process.exit(1);

// ---------- Helpers ----------

function extractShape(json) {
  const pos = json.position || {};
  return {
    schema: json.$schema || null,
    visualType: json.visual?.visualType || null,
    position: {
      x: pos.x ?? null,
      y: pos.y ?? null,
      z: pos.z ?? null,
      width: pos.width ?? null,
      height: pos.height ?? null,
    },
    hasFilterConfig: Array.isArray(json.filterConfig?.filters) && json.filterConfig.filters.length > 0,
    hasZeroPadding: detectZeroPadding(json),
  };
}

function detectZeroPadding(json) {
  const padding = json.visual?.visualContainerObjects?.padding?.[0]?.properties;
  if (!padding) return false;
  for (const side of ['top', 'right', 'bottom', 'left']) {
    const v = padding[side]?.expr?.Literal?.Value;
    if (v !== '0D' && v !== '0') return false;
  }
  return true;
}

function diffShape(a, b) {
  const out = [];
  if (a.schema !== b.schema) out.push(`$schema: "${a.schema}" vs "${b.schema}"`);
  if (a.visualType !== b.visualType) out.push(`visualType: "${a.visualType}" vs "${b.visualType}"`);
  for (const k of ['x', 'y', 'z', 'width', 'height']) {
    if (a.position[k] !== b.position[k]) {
      out.push(`position.${k}: ${a.position[k]} vs ${b.position[k]}`);
    }
  }
  if (a.hasFilterConfig !== b.hasFilterConfig) {
    out.push(`filterConfig presence: ${a.hasFilterConfig} vs ${b.hasFilterConfig}`);
  }
  if (a.hasZeroPadding !== b.hasZeroPadding) {
    out.push(`padding=0 presence: ${a.hasZeroPadding} vs ${b.hasZeroPadding}`);
  }
  return out;
}

function pageCount() {
  return readdirSync(pagesDir).filter(p => {
    try { return statSync(join(pagesDir, p)).isDirectory(); } catch { return false; }
  }).length;
}
