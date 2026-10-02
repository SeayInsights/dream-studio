#!/usr/bin/env node
// Static layout previewer for PBIR reports.
// Reads visual.json files under <Report>/definition/pages/<pageId>/visuals/*/
// and renders a neutral-themed HTML/PNG mock at the canvas's true x/y/w/h.
//
// Usage:
//   node scripts/preview-layout.mjs "<...>.Report" --page <pageId> [--out <path>]
//   node scripts/preview-layout.mjs "<...>.Report" --all-pages

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Command } from "commander";
import { chromium } from "playwright";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const TEMPLATE_PATH = path.join(__dirname, "templates", "preview.html.tmpl");

const program = new Command()
  .name("preview-layout")
  .description("Render a static layout preview of a PBIR report page.")
  .argument("<reportPath>", "Path to a *.Report folder (PBIR enhanced format)")
  .option("--page <pageId>", "Page folder name (under definition/pages/). Defaults to first page.")
  .option("--all-pages", "Render every page in the report.")
  .option("--out <pngPath>", "Output PNG path. Default: <Report>/.preview/<pageId>.png")
  .parse(process.argv);

const opts = program.opts();
const reportPath = path.resolve(program.args[0]);

await main();

async function main() {
  const reportName = path.basename(reportPath).replace(/\.Report$/, "");
  const pagesDir = path.join(reportPath, "definition", "pages");
  await assertDir(pagesDir, `pages/ folder not found under ${reportPath}`);

  const pageIds = opts.allPages
    ? await listPageFolders(pagesDir)
    : [opts.page ?? (await listPageFolders(pagesDir))[0]];

  const previewDir = path.join(reportPath, ".preview");
  await fs.mkdir(previewDir, { recursive: true });

  const template = await fs.readFile(TEMPLATE_PATH, "utf-8");

  const browser = await chromium.launch();
  try {
    for (const pageId of pageIds) {
      await renderPage({
        pageId,
        pagesDir,
        previewDir,
        template,
        browser,
        reportName,
        outOverride: opts.out,
        explicitPage: !!opts.page || !opts.allPages,
      });
    }
  } finally {
    await browser.close();
  }
}

async function renderPage({ pageId, pagesDir, previewDir, template, browser, reportName, outOverride, explicitPage }) {
  const pageDir = path.join(pagesDir, pageId);
  await assertDir(pageDir, `page folder not found: ${pageDir}`);

  const pageMeta = await readJsonOptional(path.join(pageDir, "page.json"));
  const canvas = readCanvas(pageMeta);

  const visualsDir = path.join(pageDir, "visuals");
  const visualFolders = await listSubdirs(visualsDir);

  const visuals = [];
  for (const vName of visualFolders) {
    const vJsonPath = path.join(visualsDir, vName, "visual.json");
    try {
      const v = await readJson(vJsonPath);
      visuals.push(parseVisual(v, vName));
    } catch (err) {
      visuals.push({
        name: vName,
        type: "ERROR",
        title: vName,
        x: 0, y: 0, width: 200, height: 50,
        z: 0,
        fields: [],
        error: err.message,
        offCanvas: false,
        titleHidden: false,
      });
    }
  }
  visuals.sort((a, b) => a.z - b.z);

  // Resolve relative positions for grouped visuals. Children of a visualGroup
  // have position relative to the group's origin. Walk each visual; if it has
  // parentGroupName, add the group's (x, y) to its own. Handles one level of
  // grouping (sufficient for common report layouts).
  const groupOrigins = new Map();
  for (const v of visuals) {
    if (v.isGroup) groupOrigins.set(v.name, { x: v.x, y: v.y });
  }
  for (const v of visuals) {
    if (v.parentGroupName && groupOrigins.has(v.parentGroupName)) {
      const o = groupOrigins.get(v.parentGroupName);
      v.x += o.x;
      v.y += o.y;
    }
  }

  // Mark off-canvas visuals (now using resolved absolute positions)
  for (const v of visuals) {
    v.offCanvas = (v.x + v.width) > canvas.width || (v.y + v.height) > canvas.height || v.x < 0 || v.y < 0;
  }

  // Group visuals themselves don't render — they're just metadata containers.
  // Their children render in place at resolved absolute positions.
  const renderableVisuals = visuals.filter(v => !v.isGroup);

  const html = renderHtml(template, { reportName, pageId, pageDisplayName: pageMeta?.displayName ?? pageId, canvas, visuals: renderableVisuals });
  const htmlPath = path.join(previewDir, `${pageId}.html`);
  await fs.writeFile(htmlPath, html, "utf-8");

  const pngPath = outOverride && explicitPage
    ? path.resolve(outOverride)
    : path.join(previewDir, `${pageId}.png`);

  const page = await browser.newPage({
    viewport: { width: canvas.width, height: canvas.height + 60 }, // +60 for header strip
    deviceScaleFactor: 1,
  });
  await page.goto(`file://${htmlPath.replace(/\\/g, "/")}`);
  await page.waitForLoadState("networkidle");
  await page.screenshot({ path: pngPath, fullPage: false });
  await page.close();

  // Stdout in a parseable shape
  process.stdout.write(JSON.stringify({
    page: pageId,
    pageDisplayName: pageMeta?.displayName ?? pageId,
    canvas,
    visualCount: renderableVisuals.length,
    groupCount: visuals.length - renderableVisuals.length,
    offCanvasCount: renderableVisuals.filter(v => v.offCanvas).length,
    errorCount: renderableVisuals.filter(v => v.error).length,
    html: htmlPath,
    png: pngPath,
  }) + "\n");
}

function parseVisual(v, folderName) {
  const pos = v.position ?? {};

  // visualGroup container (no `visual` block, just `visualGroup` metadata).
  // Children point to it via parentGroupName and their positions are relative
  // to the group origin. The group itself is invisible — children render at
  // resolved absolute (group.x + child.x, group.y + child.y).
  if (v.visualGroup && !v.visual) {
    return {
      name: v.name ?? folderName,
      type: "group",
      title: v.visualGroup.displayName ?? v.name ?? folderName,
      x: numOr(pos.x, 0),
      y: numOr(pos.y, 0),
      width: numOr(pos.width, 0),
      height: numOr(pos.height, 0),
      z: numOr(pos.z, 0),
      fields: [],
      titleHidden: false,
      parentGroupName: v.parentGroupName ?? null,
      isGroup: true,
    };
  }

  const visualBlock = v.visual ?? {};
  const type = visualBlock.visualType ?? "unknown";

  // Title — hidden if visualContainerObjects.title[].properties.show.expr.Literal.Value === "false"
  const titleConfigs = visualBlock.visualContainerObjects?.title ?? [];
  let titleHidden = false;
  for (const t of titleConfigs) {
    const showVal = t?.properties?.show?.expr?.Literal?.Value;
    if (showVal === "false") titleHidden = true;
  }

  // Try to extract an explicit title text — uncommon in PBIR but check anyway
  let titleText = null;
  for (const t of titleConfigs) {
    const txt = t?.properties?.text?.expr?.Literal?.Value;
    if (typeof txt === "string") {
      titleText = txt.replace(/^'|'$/g, "");
      break;
    }
  }

  const fields = extractFields(visualBlock);

  return {
    name: v.name ?? folderName,
    type,
    title: titleText ?? v.name ?? folderName,
    x: numOr(pos.x, 0),
    y: numOr(pos.y, 0),
    width: numOr(pos.width, 100),
    height: numOr(pos.height, 50),
    z: numOr(pos.z, 0),
    fields,
    titleHidden,
    parentGroupName: v.parentGroupName ?? null,
    isGroup: false,
  };
}

function extractFields(visualBlock) {
  const queryState = visualBlock?.query?.queryState ?? {};
  const out = [];
  for (const role of Object.keys(queryState)) {
    const projections = queryState[role]?.projections ?? [];
    for (const p of projections) {
      out.push({
        role,
        name: p.displayName ?? p.nativeQueryRef ?? p.queryRef ?? "?",
      });
    }
  }
  return out;
}

function numOr(v, fallback) {
  return typeof v === "number" && Number.isFinite(v) ? v : fallback;
}

function readCanvas(pageMeta) {
  const w = pageMeta?.width ?? pageMeta?.layout?.width ?? 1280;
  const h = pageMeta?.height ?? pageMeta?.layout?.height ?? 720;
  return { width: numOr(w, 1280), height: numOr(h, 720) };
}

async function listPageFolders(pagesDir) {
  const entries = await fs.readdir(pagesDir, { withFileTypes: true });
  const folders = entries.filter(e => e.isDirectory()).map(e => e.name);
  if (folders.length === 0) throw new Error(`No page folders under ${pagesDir}`);
  // Honor pages.json order if present
  try {
    const pagesJson = await readJson(path.join(pagesDir, "pages.json"));
    const ordered = pagesJson?.pageOrder?.filter?.(id => folders.includes(id)) ?? [];
    return ordered.length ? ordered : folders;
  } catch {
    return folders;
  }
}

async function listSubdirs(dir) {
  try {
    const entries = await fs.readdir(dir, { withFileTypes: true });
    return entries.filter(e => e.isDirectory()).map(e => e.name);
  } catch {
    return [];
  }
}

async function readJson(p) {
  const raw = await fs.readFile(p, "utf-8");
  return JSON.parse(raw);
}

async function readJsonOptional(p) {
  try { return await readJson(p); } catch { return null; }
}

async function assertDir(p, msg) {
  try { await fs.access(p); }
  catch { throw new Error(msg); }
}

// === Rendering ===

function renderHtml(template, ctx) {
  const visualsHtml = ctx.visuals.map(v => renderVisual(v)).join("\n");
  const summary = `${ctx.visualCount ?? ctx.visuals.length} visuals — ${ctx.canvas.width}×${ctx.canvas.height}`;
  return template
    .replaceAll("{{REPORT_NAME}}", escapeHtml(ctx.reportName))
    .replaceAll("{{PAGE_ID}}", escapeHtml(ctx.pageId))
    .replaceAll("{{PAGE_DISPLAY_NAME}}", escapeHtml(ctx.pageDisplayName))
    .replaceAll("{{CANVAS_WIDTH}}", String(ctx.canvas.width))
    .replaceAll("{{CANVAS_HEIGHT}}", String(ctx.canvas.height))
    .replaceAll("{{VISUAL_COUNT}}", String(ctx.visuals.length))
    .replaceAll("{{VISUAL_SUMMARY}}", escapeHtml(summary))
    .replaceAll("{{VISUALS_HTML}}", visualsHtml);
}

function renderVisual(v) {
  const cls = ["v", `v-type-${slug(v.type)}`];
  if (v.offCanvas) cls.push("v-off-canvas");
  if (v.error) cls.push("v-error");

  const style = `left:${v.x}px;top:${v.y}px;width:${v.width}px;height:${v.height}px;z-index:${v.z};`;
  const titleLine = v.titleHidden
    ? `<div class="v-title v-title-hidden">${escapeHtml(v.name)} <span class="v-title-tag">title hidden</span></div>`
    : `<div class="v-title">${escapeHtml(v.title)}</div>`;
  const typeChip = `<div class="v-type-chip">${escapeHtml(v.type)}</div>`;
  const filler = renderFiller(v);
  const errBlock = v.error ? `<div class="v-err">${escapeHtml(v.error)}</div>` : "";
  const fieldsList = v.fields.length
    ? `<div class="v-fields">${v.fields.map(f => `<span class="v-field" title="${escapeHtml(f.role)}">${escapeHtml(f.name)}</span>`).join("")}</div>`
    : "";

  return `<div class="${cls.join(" ")}" style="${style}">
    ${typeChip}
    ${titleLine}
    ${filler}
    ${fieldsList}
    ${errBlock}
  </div>`;
}

function renderFiller(v) {
  const t = (v.type || "").toLowerCase();

  // Custom / organizational visuals carry a GUID/hash in their visualType
  // (e.g. orgVelocityScatter_A1B2C3D4E5F6). Detect them FIRST: their
  // names frequently contain stock-chart substrings ("scatter", "slicer",
  // "map", "kpi") that would otherwise hijack them into a misleading stock
  // mock. Path B can't render a custom visual's real TypeScript/SVG output, so
  // draw an explicit "not rendered" placeholder. The bound field chips still
  // render (renderVisual), so layout + data bindings stay checkable.
  if (/[0-9a-f]{8,}/i.test(v.type || "")) {
    return `<div class="filler custom">
      <div class="custom-badge">custom visual</div>
      <div class="custom-type" title="${escapeHtml(v.type)}">${escapeHtml(v.type)}</div>
      <div class="custom-note">real output not rendered in Path B — use Path A or <code>npm start</code> sideload</div>
    </div>`;
  }

  if (/^(tableex|pivottable|matrix)$/.test(t)) {
    const cols = Math.max(1, v.fields.length || 4);
    const colCells = Array.from({ length: cols }, (_, i) =>
      `<div class="grid-cell">${escapeHtml((v.fields[i]?.name ?? `col ${i + 1}`).slice(0, 14))}</div>`
    ).join("");
    return `<div class="filler grid"><div class="grid-header">${colCells}</div>
      <div class="grid-body">${Array.from({ length: 4 }, () => `<div class="grid-row">${Array.from({ length: cols }, () => `<div class="grid-cell">·</div>`).join("")}</div>`).join("")}</div></div>`;
  }
  if (/^(card|cardvisual)$/.test(t)) {
    return `<div class="filler card"><div class="card-num">123</div></div>`;
  }
  if (/^(slicer|advancedslicer)$/.test(t)) {
    return `<div class="filler slicer"><span class="slicer-label">${escapeHtml(v.fields[0]?.name ?? "Slicer")}</span><span class="slicer-chevron">▾</span></div>`;
  }
  if (/^(azuremap|shapemap|filledmap|map)$/.test(t)) {
    return `<div class="filler map">MAP</div>`;
  }
  if (t === "image") {
    return `<div class="filler image">IMG</div>`;
  }
  if (t === "shape") {
    return `<div class="filler shape"></div>`;
  }
  if (/chart|column|bar|line|area|pie|donut|scatter|combo|funnel|gauge|kpi|treemap/.test(t)) {
    return `<div class="filler chart">
      <div class="chart-axis-y"></div>
      <div class="chart-bars">
        ${Array.from({ length: 5 }, (_, i) => `<div class="chart-bar" style="height:${30 + i * 12}%"></div>`).join("")}
      </div>
      <div class="chart-axis-x"></div>
    </div>`;
  }
  return `<div class="filler unknown">${escapeHtml(v.type || "unknown")}</div>`;
}

function slug(s) {
  return String(s).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}
