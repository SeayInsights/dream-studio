#!/usr/bin/env node
// Pre-flight validator for PBIR visual.json files.
// Catches schema breaks before the previewer wastes time rendering.
//
// Usage:
//   node scripts/validate-visual-json.mjs "<...>.Report"
//   node scripts/validate-visual-json.mjs "<...>.Report" --page <pageId>
//
// Exit codes:
//   0  all visual.json files valid
//   1  one or more validation errors
//   2  invocation error (bad args, missing folder)

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import Ajv from "ajv";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const SCHEMA_PATH = path.join(__dirname, "schemas", "visual.schema.json");

const args = process.argv.slice(2);
if (args.length === 0) {
  console.error("Usage: validate-visual-json.mjs <Report-folder> [--page <pageId>]");
  process.exit(2);
}
const reportPath = path.resolve(args[0]);
const pageIdx = args.indexOf("--page");
const onlyPage = pageIdx >= 0 ? args[pageIdx + 1] : null;

const pagesDir = path.join(reportPath, "definition", "pages");
try { await fs.access(pagesDir); }
catch {
  console.error(`Not a valid PBIR Report folder (no definition/pages/): ${reportPath}`);
  process.exit(2);
}

const schema = JSON.parse(await fs.readFile(SCHEMA_PATH, "utf-8"));
const ajv = new Ajv({ allErrors: true, strict: false });
const validate = ajv.compile(schema);

const pageFolders = onlyPage ? [onlyPage] : (await fs.readdir(pagesDir, { withFileTypes: true }))
  .filter(e => e.isDirectory()).map(e => e.name);

let errors = 0;
let checked = 0;

for (const pageId of pageFolders) {
  const visualsDir = path.join(pagesDir, pageId, "visuals");
  let visualFolders = [];
  try {
    visualFolders = (await fs.readdir(visualsDir, { withFileTypes: true }))
      .filter(e => e.isDirectory()).map(e => e.name);
  } catch {
    continue;
  }

  // Try to read canvas size for off-canvas warnings
  let canvas = { width: 1280, height: 720 };
  try {
    const pageMeta = JSON.parse(await fs.readFile(path.join(pagesDir, pageId, "page.json"), "utf-8"));
    canvas = {
      width: numOr(pageMeta?.width ?? pageMeta?.layout?.width, 1280),
      height: numOr(pageMeta?.height ?? pageMeta?.layout?.height, 720),
    };
  } catch { /* default */ }

  for (const vName of visualFolders) {
    const vPath = path.join(visualsDir, vName, "visual.json");
    let raw;
    try { raw = await fs.readFile(vPath, "utf-8"); }
    catch (err) {
      report("error", pageId, vName, `cannot read visual.json: ${err.message}`);
      errors++;
      continue;
    }

    let data;
    try { data = JSON.parse(raw); }
    catch (err) {
      report("error", pageId, vName, `invalid JSON: ${err.message}`);
      errors++;
      continue;
    }

    checked++;

    // visualGroup containers carry a `visualGroup` block instead of `visual`.
    // They're valid PBIR, but visual.schema.json requires `visual`, so ajv
    // would false-flag them. Skip schema validation for groups (same special
    // case preview-layout.mjs and exec-quality-check.mjs already make).
    if (data.visualGroup && !data.visual) {
      if (data.name && data.name !== vName) {
        report("error", pageId, vName, `name field "${data.name}" does not match folder name`);
        errors++;
      }
      continue;
    }

    const ok = validate(data);
    if (!ok) {
      for (const e of validate.errors) {
        report("error", pageId, vName, `${e.instancePath || "/"} ${e.message}`);
        errors++;
      }
      continue;
    }

    if (data.name && data.name !== vName) {
      report("error", pageId, vName, `name field "${data.name}" does not match folder name`);
      errors++;
    }

    const p = data.position;
    if (p) {
      if (p.x + p.width > canvas.width || p.y + p.height > canvas.height) {
        report("warn", pageId, vName, `off-canvas: visual extends past ${canvas.width}x${canvas.height}`);
      }
      if (p.x < 0 || p.y < 0) {
        report("warn", pageId, vName, `off-canvas: x=${p.x} y=${p.y} (negative)`);
      }
    }
  }
}

const summary = `Checked ${checked} visual.json file(s). ${errors} error(s).`;
console.log(summary);
process.exit(errors > 0 ? 1 : 0);

function report(level, pageId, vName, msg) {
  const tag = level === "error" ? "ERROR" : "WARN ";
  console.log(`[${tag}] ${pageId}/${vName}: ${msg}`);
}

function numOr(v, fb) {
  return typeof v === "number" && Number.isFinite(v) ? v : fb;
}
