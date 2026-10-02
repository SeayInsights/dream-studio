#!/usr/bin/env node
// Bulk-set isHiddenInViewMode:true on every visual-level filter across a Report.
//
// Convention: visual-level filters are NEVER user-facing. Users interact
// with filters at the page level (page.json) or report level (report.json), or
// via on-canvas slicer visuals. The "Filters on this visual" section in the
// Filter pane is for developer use only — anything visible there is a defect.
//
// Two sources of visible visual-level filters this script cleans up:
//   1. Auto-bound field filters PBI Desktop emits when fields are placed on a
//      visual's data role (one Categorical entry per column). Pure dev artifact.
//   2. Deliberate dev filters (e.g., Commodity="Cultural Crunch" pinning a card
//      to one slice). Layout choice, not user lever.
//
// Either way, the fix is the same: set isHiddenInViewMode:true on every entry.
//
// Usage:
//   node scripts/hide-visual-filters.mjs <Report-folder>
//   node scripts/hide-visual-filters.mjs <Report-folder> --dry-run
//
// Exit codes:
//   0  scan complete (with or without changes)
//   1  invalid invocation

import { readFileSync, writeFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const args = process.argv.slice(2);
if (!args[0] || args[0].startsWith('-')) {
  console.error('usage: node hide-visual-filters.mjs <Report-folder> [--dry-run]');
  process.exit(1);
}
const ROOT = args[0];
const dryRun = args.includes('--dry-run');
if (!existsSync(ROOT)) { console.error(`Report folder not found: ${ROOT}`); process.exit(1); }

let scanned = 0, modified = 0, hiddenCount = 0;

function walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    let st; try { st = statSync(full); } catch { continue; }
    if (st.isDirectory()) walk(full);
    else if (entry === 'visual.json') processFile(full);
  }
}

function processFile(path) {
  scanned++;
  let json;
  try { json = JSON.parse(readFileSync(path, 'utf8')); }
  catch (e) { console.error(`parse failed: ${path}: ${e.message}`); return; }
  const filters = json.filterConfig?.filters;
  if (!Array.isArray(filters) || filters.length === 0) return;

  let dirty = false;
  for (const f of filters) {
    if (f.isHiddenInViewMode !== true) {
      f.isHiddenInViewMode = true;
      dirty = true;
      hiddenCount++;
    }
  }
  if (!dirty) return;

  modified++;
  const rel = path.startsWith(ROOT) ? path.slice(ROOT.length + 1) : path;
  console.log(`  ${rel} — ${filters.length} filter(s) hidden`);
  if (!dryRun) writeFileSync(path, JSON.stringify(json, null, 2) + '\n', 'utf8');
}

walk(ROOT);

const verb = dryRun ? 'would hide' : 'hid';
console.log(`\n${dryRun ? 'DRY RUN — ' : ''}Scanned ${scanned} files, modified ${modified}, ${verb} ${hiddenCount} filter(s).`);
if (dryRun && hiddenCount > 0) console.log(`Re-run without --dry-run to apply.`);
