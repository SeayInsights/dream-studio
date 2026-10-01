#!/usr/bin/env node
/**
 * zero-textbox-padding.mjs
 *
 * Adds `padding: { top: 0, right: 0, bottom: 0, left: 0 }` to every
 * `textbox` visual on the given pages.
 *
 * Why this exists: PBI's default textbox inserts ~8px of internal padding
 * top/right/bottom/left. For a textbox positioned at y=32 with height=18
 * (a 9pt eyebrow band), the padding eats nearly the entire vertical space
 * and the text content clips with only the bottom of letter glyphs visible.
 * Setting padding=0 lets the text fill the textbox bounds.
 *
 * Idempotent: skips textboxes whose padding is already 0.
 *
 * Usage:
 *   node scripts/zero-textbox-padding.mjs "<Report-folder>"
 *   node scripts/zero-textbox-padding.mjs "<Report-folder>" --pages <id1,id2,...>
 *
 * Without --pages, every page in <Report-folder>/definition/pages is processed.
 */

import { readdirSync, readFileSync, writeFileSync } from "fs";
import { join } from "path";

const args = process.argv.slice(2);
if (args.length < 1) {
    console.error("usage: zero-textbox-padding.mjs <Report-folder> [--pages id1,id2]");
    process.exit(1);
}

const REPORT_DIR = args[0];
let pageFilter = null;
const pagesFlag = args.indexOf("--pages");
if (pagesFlag >= 0 && args[pagesFlag + 1]) {
    pageFilter = new Set(args[pagesFlag + 1].split(","));
}

const PAGES_DIR = join(REPORT_DIR, "definition", "pages");

const PADDING_BLOCK = [
    {
        properties: {
            top:    { expr: { Literal: { Value: "0D" } } },
            right:  { expr: { Literal: { Value: "0D" } } },
            bottom: { expr: { Literal: { Value: "0D" } } },
            left:   { expr: { Literal: { Value: "0D" } } }
        }
    }
];

const touched = [];
let skipped = 0;

let pageIds;
try {
    pageIds = readdirSync(PAGES_DIR).filter(d => {
        if (d === "pages.json") return false;
        if (pageFilter && !pageFilter.has(d)) return false;
        return true;
    });
} catch (e) {
    console.error(`Cannot read pages dir: ${PAGES_DIR}\n${e.message}`);
    process.exit(2);
}

for (const pageId of pageIds) {
    const visualsDir = join(PAGES_DIR, pageId, "visuals");
    let visuals;
    try { visuals = readdirSync(visualsDir); }
    catch { continue; }
    for (const v of visuals) {
        const path = join(visualsDir, v, "visual.json");
        let json;
        try {
            json = JSON.parse(readFileSync(path, "utf8"));
        } catch (e) {
            console.error(`SKIP (parse): ${path}: ${e.message}`);
            continue;
        }
        if (json?.visual?.visualType !== "textbox") {
            skipped++;
            continue;
        }
        json.visual.visualContainerObjects = json.visual.visualContainerObjects ?? {};
        const cur = json.visual.visualContainerObjects.padding;
        const isAlreadyZero = Array.isArray(cur)
            && cur[0]?.properties?.top?.expr?.Literal?.Value === "0D"
            && cur[0]?.properties?.right?.expr?.Literal?.Value === "0D"
            && cur[0]?.properties?.bottom?.expr?.Literal?.Value === "0D"
            && cur[0]?.properties?.left?.expr?.Literal?.Value === "0D";
        if (isAlreadyZero) {
            skipped++;
            continue;
        }
        json.visual.visualContainerObjects.padding = PADDING_BLOCK;
        writeFileSync(path, JSON.stringify(json, null, 2) + "\n");
        touched.push(`${pageId}/${v}`);
    }
}

console.log(JSON.stringify({
    touched_count: touched.length,
    skipped_count: skipped,
    touched
}, null, 2));
