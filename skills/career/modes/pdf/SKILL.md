---
name: career-pdf
model_tier: sonnet
description: "Generate ATS-optimized CV PDFs and LinkedIn outreach messages. Modes: pdf (CV generation), contacto (LinkedIn outreach). Trigger via /career-ops pdf or /career-ops contact."
pack: career
chain_suggests: []
---

# Career-PDF — Content Generation

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Paths
Read `~/.dream-studio/career-ops/config.yml` to get `career_studio_path`.
Read `{career_studio_path}/config/career-ops-paths.yml` to resolve all paths.

## Modes

### pdf — ATS-optimized CV generation
1. Read `modes/_shared.md` + `modes/pdf.md`
2. Read `cv.md` + `article-digest.md` (if exists) + `modes/_profile.md`
3. Read `templates/cv-template.html` for HTML template
4. If a specific JD was evaluated, tailor the CV to that JD's keywords
5. Generate customized HTML → write to temp file
6. Run: `node generate-pdf.mjs {html_path} {output_path}`
7. Output PDF to `output/` directory

### contacto — LinkedIn outreach
1. Read `modes/_shared.md` + `modes/contacto.md`
2. Use WebSearch to find relevant contacts at target company
3. Draft personalized outreach messages
4. Save to report or display inline

## PDF quality rules (from _shared.md)
- NEVER use cliche phrases ("passionate about", "results-oriented", "proven track record")
- Unicode normalization: generate-pdf.mjs handles em-dashes and smart quotes → ASCII
- Vary sentence structure — don't start every bullet the same way
- Prefer specifics: "Cut p95 latency from 2.1s to 380ms" over "improved performance"
- Case study URLs in Professional Summary section
- Cover letter: if form allows it, always include one. Same visual design as CV. 1 page max.

## Playwright lock
Before PDF generation:
1. Check `~/.dream-studio/career-ops/playwright.lock`
2. If exists and <10 min old → fail: "Playwright is busy (scan or apply running). Wait or delete lock."
3. If absent or stale → create lock with `{"skill": "career-pdf", "started": "ISO-8601"}`
4. Delete lock in finally block after PDF generation completes

## Atomic writes
Never write directly to checkpoint.json or career-ops.json. Instead:
1. Write to `{filename}.tmp` in the same directory
2. Verify the temp file is valid JSON (parse it back)
3. Rename `{filename}.tmp` → `{filename}` (atomic)

## Feed corruption recovery
If reading the existing feed file fails (corrupted JSON from a previous crash), discard it and start from the default empty feed structure rather than failing.

## Output
- PDF files go to `output/` (gitignored)
- Update tracker entry with PDF status (✅)
- Update checkpoint and feed

**Feed validation (before writing):**
1. `schema_version` must be `1`
2. `last_updated` must be ISO-8601 string or `null`
3. `pipeline_count` must be integer >= 0
4. `recent_activity` must be an array with <= 10 items — truncate to last 10 before writing
5. If any check fails, log a warning and preserve the existing feed file (do not overwrite with invalid data)

## Activity log

After PDF generation or outreach completes, append one line to `~/.dream-studio/career-ops/activity.log`:
```
{ISO-8601} | career-pdf | {mode} | {summary} | {outcome}
```
Examples:
- `2026-04-18T10:36:00Z | career-pdf | pdf | Stripe Senior Engineer | output/stripe-cv.pdf | OK`
- `2026-04-18T10:37:00Z | career-pdf | contacto | Stripe 3 contacts | OK`
