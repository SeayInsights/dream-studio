#!/usr/bin/env node
// One-shot helper: walk a PBIP report tree and add an explicit
// `visualContainerObjects.background[].show = false` to specific visuals so
// they render with a transparent container instead of PBI Desktop's default
// opaque white. Safe to run multiple times (skips if already set).
//
// Targets (by visual name): v_logo, v_title, v_page_title, v_logo_hero,
// v_logo_white, v_refresh.
//
// Why: PBIR schema is permissive; if visualContainerObjects has no
// `background` entry, PBI Desktop fills the visual container with white.
// On a colored page background this looks like an empty white card framing
// what should be just transparent content (a logo, a title text).

import { readFileSync, writeFileSync, readdirSync, existsSync, statSync } from 'node:fs';
import { join } from 'node:path';

const ROOT = process.argv[2];
if (!ROOT) {
  console.error('usage: node bulk-transparent-bg.mjs <Report-folder>');
  process.exit(1);
}

// Target rule: any visual whose visualType is textbox or image. Textboxes
// (titles, labels, body text, footnotes) and images (logos, banners, backgrounds)
// should never have opaque white container framing on a colored page.
//
// cardVisual, tableEx, pivotTable, charts: keep their explicit backgrounds
// (the white card body IS the intended look on a frost page).
const TARGET_VISUAL_TYPES = new Set(['textbox', 'image']);

const TRANSPARENT_BACKGROUND = {
  properties: {
    show: { expr: { Literal: { Value: 'false' } } }
  }
};

function walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      walk(full);
    } else if (entry === 'visual.json') {
      patch(full);
    }
  }
}

function patch(path) {
  let src;
  try { src = readFileSync(path, 'utf8'); }
  catch { return; }
  let json;
  try { json = JSON.parse(src); }
  catch (e) { console.error(`! parse failed: ${path}`); return; }

  const v = json.visual;
  if (!v) return;
  if (!TARGET_VISUAL_TYPES.has(v.visualType)) return;
  v.visualContainerObjects = v.visualContainerObjects || {};
  const bg = v.visualContainerObjects.background;

  if (Array.isArray(bg) && bg.length > 0) {
    // Already has a background entry — force show=false.
    const props = bg[0].properties = bg[0].properties || {};
    props.show = { expr: { Literal: { Value: 'false' } } };
  } else {
    v.visualContainerObjects.background = [TRANSPARENT_BACKGROUND];
  }

  const out = JSON.stringify(json, null, 2) + '\n';
  if (out !== src) {
    writeFileSync(path, out, 'utf8');
    console.log(`patched ${json.name}: ${path}`);
  }
}

walk(ROOT);
