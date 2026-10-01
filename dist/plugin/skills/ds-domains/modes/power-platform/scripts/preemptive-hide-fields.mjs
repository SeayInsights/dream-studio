#!/usr/bin/env node
// Pre-create hidden filter entries for every field/measure bound to a visual's
// data role. PBI Desktop's "Filters on this visual" pane auto-displays a card
// for every bound field — and persists it to filterConfig only after the user
// interacts with the visual. This script writes those entries upfront so the
// "(All)" cards never appear visible in the editor pane.
//
// CRITICAL: filter names must be 20-char lowercase hex strings (PBI Desktop's
// internal format). Using readable strings causes PBI to silently reject the
// filter and render the visual BLANK. Verified by smoke test 2026-05-17.
//
// Idempotent: detects existing coverage by field shape and skips.
//
// Usage:
//   node scripts/preemptive-hide-fields.mjs <Report-folder>
//   node scripts/preemptive-hide-fields.mjs <Report-folder> --dry-run
//
// Exit codes:
//   0  scan complete
//   1  invalid invocation

import { readFileSync, writeFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { randomBytes } from 'node:crypto';

const args = process.argv.slice(2);
if (!args[0] || args[0].startsWith('-')) {
  console.error('usage: node preemptive-hide-fields.mjs <Report-folder> [--dry-run]');
  process.exit(1);
}
const ROOT = args[0];
const dryRun = args.includes('--dry-run');
if (!existsSync(ROOT)) { console.error(`Report folder not found: ${ROOT}`); process.exit(1); }

let scanned = 0, modified = 0, addedTotal = 0;

function walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    let st; try { st = statSync(full); } catch { continue; }
    if (st.isDirectory()) walk(full);
    else if (entry === 'visual.json') processFile(full);
  }
}

function fieldKey(field) {
  if (!field) return null;
  if (field.Column)      return `col:${field.Column.Expression?.SourceRef?.Entity}::${field.Column.Property}`;
  if (field.Measure)     return `meas:${field.Measure.Expression?.SourceRef?.Entity}::${field.Measure.Property}`;
  if (field.Aggregation) {
    const inner = field.Aggregation.Expression;
    return `agg:${field.Aggregation.Function}:${fieldKey(inner) ?? 'unknown'}`;
  }
  return JSON.stringify(field);
}

// PBI Desktop's internal filter-name format. 20-char lowercase hex.
function hexUuid() { return randomBytes(10).toString('hex'); }

function processFile(path) {
  scanned++;
  let json;
  try { json = JSON.parse(readFileSync(path, 'utf8')); } catch { return; }

  const queryState = json.visual?.query?.queryState;
  if (!queryState) return;

  // Every projection across all data roles (Data, Y, Category, Rows, Values, etc.).
  const projectedFields = [];
  for (const role of Object.values(queryState)) {
    if (!role?.projections) continue;
    for (const p of role.projections) {
      if (p.field) projectedFields.push(p.field);
    }
  }
  if (projectedFields.length === 0) return;

  json.filterConfig ??= { filters: [] };
  json.filterConfig.filters ??= [];

  const covered = new Set(json.filterConfig.filters.map(f => fieldKey(f.field)).filter(Boolean));

  let addedHere = 0;
  for (const field of projectedFields) {
    const key = fieldKey(field);
    if (!key || covered.has(key)) continue;
    json.filterConfig.filters.push({
      name: hexUuid(),
      field,
      type: 'Advanced',
      isHiddenInViewMode: true
    });
    covered.add(key);
    addedHere++;
    addedTotal++;
  }

  if (addedHere === 0) return;
  modified++;
  const rel = path.startsWith(ROOT) ? path.slice(ROOT.length + 1) : path;
  console.log(`  ${rel} (${json.name}) — added ${addedHere} hidden filter(s)`);
  if (!dryRun) writeFileSync(path, JSON.stringify(json, null, 2) + '\n', 'utf8');
}

walk(ROOT);
console.log(`\n${dryRun ? 'DRY RUN — ' : ''}Scanned ${scanned}, modified ${modified}, added ${addedTotal} hidden entries.`);
if (dryRun && addedTotal > 0) console.log('Re-run without --dry-run to apply.');
