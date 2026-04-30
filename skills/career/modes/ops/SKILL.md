---
name: career-ops
description: "AI job search command center — routes to career sub-skills (evaluate, scan, apply, track, pdf). Trigger on /career-ops or career-related commands."
user_invocable: true
args: mode
argument-hint: "[scan | evaluate | pdf | apply | compare | tracker | pipeline | deep | training | project | gig | proposal | sow | patterns | followup | batch | contact | interview-prep]"
pack: career
chain_suggests: []
---

# Career-Ops — Router & Command Center

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Paths

Read `~/.dream-studio/career-ops/config.yml` to get `career_studio_path`.
Read `{career_studio_path}/config/career-ops-paths.yml` to resolve all paths.
Read `{career_studio_path}/modes/manifest.yml` for routing rules.

## Init Guard (first run)

Before anything else, ensure the dream-studio integration directories exist:
```bash
mkdir -p ~/.dream-studio/career-ops ~/.dream-studio/feeds
```

If `~/.dream-studio/feeds/career-ops.json` doesn't exist, create it with default empty feed:
```json
{"schema_version":1,"last_updated":null,"pipeline_count":0,"total_applications":0,"by_status":{},"last_evaluation":null,"last_scan":null,"overdue_followups":0,"active_interviews":0,"pending_offers":0,"recent_activity":[],"batch_in_progress":null}
```

If `~/.dream-studio/career-ops/checkpoint.json` doesn't exist, create it:
```json
{"schema_version":1,"last_action":null,"timestamp":null,"status":"idle","mode":null,"context":{}}
```

## Onboarding Gate

Before ANY mode execution, verify these files exist (paths from career-ops-paths.yml):
1. `cv.md` — user's CV
2. `config/profile.yml` — user identity and targets
3. `modes/_profile.md` — user archetypes and narrative
4. `portals.yml` — portal config
5. `modes/manifest.yml` — routing manifest (if missing, system cannot route)

If `modes/_profile.md` is missing, copy from `modes/_profile.template.md` silently.
If `modes/manifest.yml` is missing, warn: "Routing manifest missing. Career-ops cannot route commands. Reinstall or restore modes/manifest.yml."
If ANY other file is missing, enter onboarding mode — guide the user step by step per the instructions in `{career_studio_path}/CLAUDE.md` under "First Run — Onboarding".

## Routing

Determine mode from `{{mode}}` using this precedence:

### Language mode resolution
Before loading any mode file, check for a language-specific version:
1. Read `config/profile.yml` for `language.modes_dir` (e.g., `modes/de`, `modes/fr`, `modes/ja`)
2. If set, construct language path: `{language.modes_dir}/{mode}.md`
3. Check if that file exists
4. If yes, use it instead of the default `modes/{mode}.md`
5. If no, fall back to `modes/{mode}.md` and log: "Language mode {language.modes_dir}/{mode}.md not found, using English fallback"
6. If `language.modes_dir` is not set, use `modes/{mode}.md` directly

This applies to all mode file reads below (standalone modes, sub-skill context loading, `_shared.md`, etc.).

### 1. Exact trigger match
Read `modes/manifest.yml`. If input starts with a known trigger for any mode, route directly.

| Input | Skill to invoke |
|-------|-----------------|
| `evaluate`, `oferta`, `eval` | `/career-evaluate` with mode=oferta |
| `compare`, `ofertas`, `rank` | `/career-evaluate` with mode=ofertas |
| `scan`, `search`, `discover` | `/career-scan` |
| `apply`, `application` | `/career-apply` with mode=apply |
| `batch`, `bulk` | `/career-apply` with mode=batch |
| `tracker`, `status`, `applications` | `/career-track` with mode=tracker |
| `pipeline`, `inbox` | `/career-track` with mode=pipeline |
| `patterns`, `rejections` | `/career-track` with mode=patterns |
| `followup`, `follow-up`, `cadence` | `/career-track` with mode=followup |
| `pdf`, `cv`, `resume` | `/career-pdf` |
| `contact`, `contacto`, `linkedin` | `/career-pdf` with mode=contacto |
| `deep`, `research` | Standalone — read `modes/deep.md`, execute inline |
| `training`, `course`, `cert` | Standalone — read `modes/training.md`, execute inline |
| `project`, `portfolio` | Standalone — read `modes/project.md`, execute inline |
| `gig`, `freelance` | `/career-evaluate` with mode=gig |
| `proposal`, `cover-letter` | `/career-evaluate` with mode=proposal |
| `sow`, `statement-of-work` | `/career-evaluate` with mode=sow |
| `interview-prep`, `interview` | Standalone — read `modes/interview-prep.md`, execute inline |

### 2. URL detection
If input contains `https://` or `http://`:
- Domain matches Upwork/Fiverr/Freelancer/Toptal → `/career-evaluate` with mode=gig
- Otherwise → run auto-pipeline (full evaluate + report + PDF + tracker)

### 3. Keyword detection with disambiguation
Read `modes/manifest.yml` for detection rules. Score each mode's `detect.requires_any` keywords against the input.
- If one mode scores above `min_confidence` and no other does → route to it
- If `auto-pipeline` and `gig` both score above threshold → **ask the user**: "This looks like it could be a job posting or a freelance gig. Which should I evaluate it as?"
- If no mode scores above threshold → show discovery menu

### 4. No match — Discovery menu
```
career-ops — Command Center

  /career-ops {JD}         → Full pipeline: evaluate + report + PDF + tracker
  /career-ops evaluate     → Evaluation only A-G
  /career-ops compare      → Compare and rank multiple offers
  /career-ops scan         → Scan portals for new offers
  /career-ops apply        → Live application assistant
  /career-ops pdf          → Generate ATS-optimized CV
  /career-ops tracker      → Application status overview
  /career-ops pipeline     → Process pending URLs from inbox
  /career-ops deep         → Deep company research
  /career-ops contact      → LinkedIn outreach
  /career-ops training     → Evaluate course/cert
  /career-ops project      → Evaluate portfolio project
  /career-ops gig          → Evaluate freelance gig
  /career-ops proposal     → Draft freelance proposal
  /career-ops sow          → Generate statement of work
  /career-ops patterns     → Analyze rejection patterns
  /career-ops followup     → Follow-up cadence tracker
  /career-ops batch        → Batch processing
  /career-ops interview-prep → Company-specific interview prep

Inbox: add URLs to data/pipeline.md → /career-ops pipeline
Or paste a JD directly to run the full pipeline.
```

## Auto-pipeline (JD pasted directly)

When routing to auto-pipeline, invoke `/career-evaluate` with mode=auto-pipeline and pass the full JD text or URL.

## Context Budget

Before invoking a sub-skill, check `modes/manifest.yml` for the mode's `context_budget_tokens`. If the current session is already above 50% context usage, dispatch as a subagent instead of inline execution.

## Feed Update

After ANY mode completes that changes career state (evaluation, scan, apply, tracker update), update the feed file at `~/.dream-studio/feeds/career-ops.json`. Read `data/applications.md` to compute current stats.

**Feed validation (before writing):**
1. `schema_version` must be `1`
2. `last_updated` must be ISO-8601 string or `null`
3. `pipeline_count` must be integer >= 0
4. `recent_activity` must be an array with <= 10 items — truncate to last 10 before writing
5. If any check fails, log a warning and preserve the existing feed file (do not overwrite with invalid data)

## Activity log

After ANY mode completes, append one line to `~/.dream-studio/career-ops/activity.log`:
```
{ISO-8601} | {skill} | {mode} | {summary} | {outcome}
```
Example: `2026-04-18T10:30:00Z | career-evaluate | oferta | Stripe Senior Engineer | score=4.2 | OK`
Outcome is `OK`, `PARTIAL (reason)`, or `ERROR (reason)`.

## Session check

On first invocation per session, run silently:
```bash
node {career_studio_path}/cv-sync-check.mjs
```
If warnings, notify the user.
