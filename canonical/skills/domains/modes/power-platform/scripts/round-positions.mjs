#!/usr/bin/env node
// Round fractional position coordinates in PBIR visual.json files.
//
// PBI Desktop's mouse-drag resize writes coordinates at sub-pixel precision
// (e.g., x=24.497607655502392, height=329.18660287081343). These hit no actual
// pixel boundary, accumulate diffs in version control, and snake through to
// child visuals that snap-aligned to them. This script rounds them to integers
// (or to a snap grid like nearest-4) so the saved layout matches an intentional
// grid.
//
// Usage:
//   node scripts/round-positions.mjs <Report-folder> [--snap N] [--dry-run]
//   node scripts/round-positions.mjs <Report-folder> --visual <visualName> ...
//   node scripts/round-positions.mjs <Report-folder> --skip <visualName> ...
//
// Flags:
//   --snap N        Round to nearest N (default 1 = integer)
//   --dry-run       Print intended changes, don't write
//   --visual <name> Only process these named visuals (repeatable). Default: all.
//   --skip <name>   Skip these named visuals (repeatable). Useful when the user
//                   has manually sized a visual to fit data — pass
//                   `--skip v_table_main --skip v_table_side` to preserve.
//
// Exit codes:
//   0  one or more files updated (or dry-run preview emitted), or nothing to do
//   1  invalid invocation

import { readFileSync, writeFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const args = process.argv.slice(2);
if (args.length === 0 || args[0].startsWith('-')) {
  console.error('usage: node round-positions.mjs <Report-folder> [--snap N] [--dry-run] [--visual <name>]... [--skip <name>]...');
  process.exit(1);
}

const ROOT = args.shift();
let snap = 1;
let dryRun = false;
const onlyVisuals = new Set();
const skipVisuals = new Set();

while (args.length) {
  const a = args.shift();
  if (a === '--snap') snap = Math.max(1, parseInt(args.shift(), 10) || 1);
  else if (a === '--dry-run') dryRun = true;
  else if (a === '--visual') onlyVisuals.add(args.shift());
  else if (a === '--skip') skipVisuals.add(args.shift());
  else { console.error(`unknown flag: ${a}`); process.exit(1); }
}

if (!existsSync(ROOT)) {
  console.error(`Report folder not found: ${ROOT}`);
  process.exit(1);
}

const pagesDir = join(ROOT, 'definition', 'pages');
if (!existsSync(pagesDir)) {
  console.error(`pages/ folder not found at ${pagesDir}`);
  process.exit(1);
}

let filesScanned = 0;
let filesUpdated = 0;
const changes = [];

for (const pageEntry of readdirSync(pagesDir)) {
  const pageDir = join(pagesDir, pageEntry);
  let st; try { st = statSync(pageDir); } catch { continue; }
  if (!st.isDirectory()) continue;
  const visualsDir = join(pageDir, 'visuals');
  if (!existsSync(visualsDir)) continue;
  for (const visualEntry of readdirSync(visualsDir)) {
    const visualJsonPath = join(visualsDir, visualEntry, 'visual.json');
    if (!existsSync(visualJsonPath)) continue;
    filesScanned++;
    processVisual(visualJsonPath);
  }
}

function processVisual(path) {
  const raw = readFileSync(path, 'utf8');
  let json;
  try { json = JSON.parse(raw); }
  catch (e) {
    console.error(`parse failed: ${path}: ${e.message}`);
    return;
  }
  const name = json.name || '(unnamed)';
  if (onlyVisuals.size > 0 && !onlyVisuals.has(name)) return;
  if (skipVisuals.has(name)) return;

  const pos = json.position;
  if (!pos) return;

  const before = { x: pos.x, y: pos.y, width: pos.width, height: pos.height };
  const after = {
    x: roundToSnap(pos.x),
    y: roundToSnap(pos.y),
    width: roundToSnap(pos.width),
    height: roundToSnap(pos.height),
  };

  const fields = ['x', 'y', 'width', 'height'].filter(k => before[k] !== after[k]);
  if (fields.length === 0) return;

  pos.x = after.x;
  pos.y = after.y;
  pos.width = after.width;
  pos.height = after.height;

  changes.push({ path, name, fields: fields.map(k => `${k}: ${before[k]} -> ${after[k]}`) });

  if (!dryRun) {
    writeFileSync(path, JSON.stringify(json, null, 2) + '\n', 'utf8');
    filesUpdated++;
  }
}

function roundToSnap(val) {
  if (typeof val !== 'number') return val;
  return Math.round(val / snap) * snap;
}

if (changes.length === 0) {
  console.log(`round-positions: scanned ${filesScanned} visual.json file(s), nothing to round (already integer at snap=${snap}).`);
  process.exit(0);
}

console.log(`round-positions: ${dryRun ? 'DRY RUN — ' : ''}${filesUpdated || changes.length} file(s) ${dryRun ? 'would be' : ''} updated (snap=${snap}):\n`);
for (const c of changes) {
  const rel = c.path.startsWith(ROOT) ? c.path.slice(ROOT.length + 1) : c.path;
  console.log(`  ${rel}`);
  console.log(`    ${c.name}`);
  for (const f of c.fields) console.log(`      ${f}`);
}
if (dryRun) console.log(`\n(dry run — no files written. Re-run without --dry-run to apply.)`);
