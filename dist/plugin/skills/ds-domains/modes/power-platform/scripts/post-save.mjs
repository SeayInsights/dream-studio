#!/usr/bin/env node
// Umbrella cleanup pipeline to run after every PBI Desktop save session.
// Chains the four standard sanitizers in order; halts on hard error, continues
// on warnings. Idempotent — safe to re-run at any time.
//
// Pipeline:
//   1. hide-visual-filters.mjs       — flip every existing filterConfig entry to hidden
//   2. preemptive-hide-fields.mjs    — pre-create hidden entries for any bound projection PBI hasn't persisted yet
//   3. check-page-chrome-drift.mjs   — flag schema/position/filter drift across pages (non-fatal)
//   4. exec-quality-check.mjs        — preflight all the rules the exec-grade review enforces (non-fatal)
//
// Usage:
//   node scripts/post-save.mjs <Report-folder>
//   node scripts/post-save.mjs <Report-folder> --skip drift,exec    # skip listed steps
//
// Exit codes:
//   0  all cleanup steps succeeded (exec-quality warnings are non-fatal)
//   1  one or more critical steps failed (parse error, missing folder)
//   2  drift or exec-quality reported errors — fix and re-run

import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
if (!args[0] || args[0].startsWith('-')) {
  console.error('usage: node post-save.mjs <Report-folder> [--skip step1,step2]');
  console.error('       steps: hide, preemptive, drift, exec');
  process.exit(1);
}
const ROOT = args[0];
const skipFlag = args.find(a => a.startsWith('--skip='))?.slice(7)
              ?? (args.indexOf('--skip') >= 0 ? args[args.indexOf('--skip') + 1] : '');
const skip = new Set(skipFlag ? skipFlag.split(',').map(s => s.trim()) : []);

if (!existsSync(ROOT)) { console.error(`Report folder not found: ${ROOT}`); process.exit(1); }

const steps = [
  { id: 'hide',       script: 'hide-visual-filters.mjs',    label: 'Hide existing visual-level filters' },
  { id: 'preemptive', script: 'preemptive-hide-fields.mjs', label: 'Pre-create hidden filters for bound fields' },
  { id: 'drift',      script: 'check-page-chrome-drift.mjs', label: 'Check page-chrome drift across pages', diagnostic: true },
  { id: 'exec',       script: 'exec-quality-check.mjs',     label: 'Exec-grade quality scan',             diagnostic: true },
];

let hadDiagnosticFailure = false;

for (const step of steps) {
  if (skip.has(step.id)) {
    console.log(`\n--- ${step.label} (SKIPPED) ---`);
    continue;
  }
  console.log(`\n--- ${step.label} ---`);
  const scriptPath = join(__dirname, step.script);
  if (!existsSync(scriptPath)) {
    console.error(`  ! script not found: ${scriptPath}`);
    process.exit(1);
  }
  const r = spawnSync(process.execPath, [scriptPath, ROOT], { stdio: 'inherit' });
  if (r.status !== 0) {
    if (step.diagnostic) {
      console.error(`  ! ${step.id} reported issues (exit ${r.status}). Fix and re-run.`);
      hadDiagnosticFailure = true;
    } else {
      console.error(`  ! ${step.id} failed (exit ${r.status}); aborting pipeline.`);
      process.exit(1);
    }
  }
}

console.log('\n--- post-save complete ---');
if (hadDiagnosticFailure) {
  console.log('One or more diagnostic checks found issues. Cleanup steps ran; fix the flagged items before shipping.');
  process.exit(2);
}
console.log('All checks clean. Report is ready.');
process.exit(0);
