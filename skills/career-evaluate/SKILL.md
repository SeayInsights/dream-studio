---
name: career-evaluate
description: "Evaluate job offers, freelance gigs, or compare multiple opportunities. Modes: auto-pipeline, oferta, ofertas, gig, proposal, sow. Trigger via /career-ops routing."
---

# Career-Evaluate — Offer Assessment Engine

## Paths
Read `~/.dream-studio/career-ops/config.yml` to get `career_studio_path`.
Read `{career_studio_path}/config/career-ops-paths.yml` to resolve all paths.

## Mode
Determine execution mode from the routing context:
- `auto-pipeline` — Full pipeline: extract JD → evaluate A-G → save report → generate PDF → draft answers (if score >= 4.5) → update tracker
- `oferta` — Evaluation only: blocks A-G, save report, update tracker. No auto PDF.
- `ofertas` — Compare multiple offers: load reports, rank, produce comparison table
- `gig` — Freelance gig evaluation with financial impact analysis
- `proposal` — Draft a proposal/cover letter for a freelance gig
- `sow` — Generate Statement of Work for a won contract

## Resume check

Before starting a new evaluation, check `~/.dream-studio/career-ops/checkpoint.json`:
- If `status` is `"partial"` and `last_action` is `"evaluate"`:
  1. Read `completed_blocks` from the checkpoint (e.g. `["A", "B", "C"]`)
  2. Read the partial report at `report_path`
  3. Show user: "Found partial evaluation of {company} (blocks {completed_blocks} done). Resume from block {next_block}?"
  4. If user confirms: load the partial report, skip completed blocks, resume from the next incomplete block
  5. If user declines: set checkpoint `status` to `"abandoned"` and proceed with fresh evaluation

## Before evaluation

1. Read `cv.md`, `modes/_profile.md`, `article-digest.md` (if exists)
2. Read `modes/_shared.md` for scoring system, archetypes, global rules
3. Read `modes/{mode}.md` for mode-specific execution steps
4. Language routing: if `config/profile.yml` has `language.modes_dir` set, read from that directory with fallback to `modes/`

## Execution

Follow the loaded mode file exactly. Key rules from `_shared.md`:
- NEVER invent experience or metrics — cite exact lines from CV
- ALWAYS detect archetype and adapt framing per `_profile.md`
- Use WebSearch for comp and company data
- Register every evaluated offer in tracker via TSV (never edit `applications.md` directly for new entries)
- Generate content in the language of the JD

## Report output

Save to `reports/{###}-{company-slug}-{YYYY-MM-DD}.md` where `{###}` is next sequential 3-digit number.

## Tracker update

Write one TSV file per evaluation to `batch/tracker-additions/{num}-{company-slug}.tsv`:
```
{num}\t{date}\t{company}\t{role}\t{status}\t{score}/5\t{pdf_emoji}\t[{num}](reports/{num}-{slug}-{date}.md)\t{note}
```
Then run: `node merge-tracker.mjs`

## Checkpoint

Before starting evaluation, write an initial checkpoint:
```json
{
  "last_action": "evaluate",
  "timestamp": "ISO-8601",
  "status": "in_progress",
  "mode": "oferta",
  "company": "Company Name"
}
```

After completing an evaluation, overwrite with:
```json
{
  "last_action": "evaluate",
  "timestamp": "ISO-8601",
  "status": "idle",
  "mode": "oferta",
  "company": "Company Name",
  "report_path": "reports/042-company-2026-04-18.md",
  "score": 4.2,
  "next_suggested_action": "generate PDF"
}
```

## Atomic writes
Never write directly to checkpoint.json or career-ops.json. Instead:
1. Write to `{filename}.tmp` in the same directory
2. Verify the temp file is valid JSON (parse it back)
3. Rename `{filename}.tmp` → `{filename}` (atomic)

## Feed corruption recovery
If reading the existing feed file fails (corrupted JSON from a previous crash), discard it and start from the default empty feed structure rather than failing.

## Feed update

After evaluation, update `~/.dream-studio/feeds/career-ops.json` with latest stats.

**Feed validation (before writing):**
1. `schema_version` must be `1`
2. `last_updated` must be ISO-8601 string or `null`
3. `pipeline_count` must be integer >= 0
4. `recent_activity` must be an array with <= 10 items — truncate to last 10 before writing
5. If any check fails, log a warning and preserve the existing feed file (do not overwrite with invalid data)

## Activity log

After evaluation completes, append one line to `~/.dream-studio/career-ops/activity.log`:
```
{ISO-8601} | career-evaluate | {mode} | {company} {role} | score={score} | {outcome}
```
Outcome: `OK`, `PARTIAL (blocks A-C done)`, or `ERROR (reason)`.

## Context pressure

If context is growing large mid-evaluation:
- Complete the current block (A-G), don't stop mid-block
- Save the report with whatever blocks are complete, mark incomplete blocks
- Write checkpoint with `"status": "partial"` and `"completed_blocks": ["A", "B", "C"]`
- Handoff can resume from checkpoint
