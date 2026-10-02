#!/usr/bin/env node
// Baseline image-diff for Path A / Path B canvas renders.
//
// Compares a candidate PNG against an approved baseline using pixelmatch,
// writes a visual diff PNG, and reports the changed-pixel percentage. This is
// the render-level safety net the JSON-only exec-quality-check.mjs CAN'T be:
// it catches regressions that live in pixels, not in visual.json — clipped
// text inside a custom visual's SVG, sentiment-color drift, a layout shift, a
// logo that moved. It does NOT understand *what* changed; it tells you a
// render diverged from an approved baseline so a human (or Claude, via the
// multimodal Read) looks at the diff.
//
// Workflow: keep an approved render under .preview/approval-<name>_canvas.png.
// After a change, re-run Path A (screenshot-pbi-desktop.ps1) or Path B
// (preview-layout.mjs) to produce a fresh candidate, then diff it against the
// baseline. A non-zero diff is a prompt to LOOK, not an automatic failure —
// tune --max-diff-pct to your tolerance.
//
// Usage:
//   node scripts/compare-render.mjs <candidate.png> <baseline.png> [options]
//
// Options:
//   --out <diff.png>     Where to write the visual diff. Default: <candidate>.diff.png
//   --max-diff-pct <n>   Fail threshold, % of pixels changed (default: 0.5)
//   --threshold <0..1>   Per-pixel color sensitivity for pixelmatch; lower = stricter (default: 0.1)
//   --json               Emit machine-readable JSON only (no human summary)
//
// Exit codes:
//   0  diff% <= max-diff-pct        (pass)
//   1  diff% >  max-diff-pct        (regression — inspect the diff PNG)
//   2  usage / read / dimension-mismatch error

import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { Command } from "commander";
import { PNG } from "pngjs";
import pixelmatch from "pixelmatch";

const program = new Command()
  .name("compare-render")
  .description("Diff a candidate render PNG against an approved baseline.")
  .argument("<candidate>", "Path to the fresh render PNG")
  .argument("<baseline>", "Path to the approved baseline PNG")
  .option("--out <pngPath>", "Output diff PNG path (default: <candidate>.diff.png)")
  .option("--max-diff-pct <n>", "Fail threshold as % of pixels changed", "0.5")
  .option("--threshold <n>", "Per-pixel color sensitivity (0..1, lower = stricter)", "0.1")
  .option("--json", "Emit machine-readable JSON only")
  .parse(process.argv);

const opts = program.opts();
const [candidatePath, baselinePath] = program.args;
const maxDiffPct = Number(opts.maxDiffPct);
const threshold = Number(opts.threshold);

if (!Number.isFinite(maxDiffPct) || maxDiffPct < 0) fail(2, `--max-diff-pct must be a non-negative number (got "${opts.maxDiffPct}")`);
if (!Number.isFinite(threshold) || threshold < 0 || threshold > 1) fail(2, `--threshold must be between 0 and 1 (got "${opts.threshold}")`);

for (const [label, p] of [["candidate", candidatePath], ["baseline", baselinePath]]) {
  if (!existsSync(p)) fail(2, `${label} PNG not found: ${p}`);
}

const candidate = readPng(candidatePath, "candidate");
const baseline = readPng(baselinePath, "baseline");

if (candidate.width !== baseline.width || candidate.height !== baseline.height) {
  fail(
    2,
    `dimension mismatch — candidate ${candidate.width}x${candidate.height} vs baseline ${baseline.width}x${baseline.height}.\n` +
      `  Re-capture both at the same size (same -ResizeWidth/-ResizeHeight, or both with/without -HighRes; same --CanvasOnly).`
  );
}

const { width, height } = candidate;
const diff = new PNG({ width, height });
const diffPixels = pixelmatch(candidate.data, baseline.data, diff.data, width, height, {
  threshold,
  includeAA: false,
});

const totalPixels = width * height;
const diffPct = (diffPixels / totalPixels) * 100;
const pass = diffPct <= maxDiffPct;

const outPath = opts.out ?? `${candidatePath}.diff.png`;
writeFileSync(outPath, PNG.sync.write(diff));

const result = {
  candidate: candidatePath,
  baseline: baselinePath,
  width,
  height,
  diffPixels,
  totalPixels,
  diffPct: Number(diffPct.toFixed(4)),
  maxDiffPct,
  threshold,
  diff: outPath,
  pass,
};

if (opts.json) {
  process.stdout.write(JSON.stringify(result) + "\n");
} else {
  const verdict = pass ? "✓ within tolerance" : "✗ REGRESSION — inspect the diff";
  process.stdout.write(
    `${verdict}\n` +
      `  ${diffPixels.toLocaleString()} / ${totalPixels.toLocaleString()} px changed = ${diffPct.toFixed(3)}% ` +
      `(threshold ${maxDiffPct}%)\n` +
      `  diff image: ${outPath}\n`
  );
}

process.exit(pass ? 0 : 1);

// ---- helpers ----
function readPng(p, label) {
  try {
    return PNG.sync.read(readFileSync(p));
  } catch (err) {
    fail(2, `failed to read ${label} PNG ${p}: ${err.message}`);
  }
}

function fail(code, msg) {
  process.stderr.write(`compare-render: ${msg}\n`);
  process.exit(code);
}
