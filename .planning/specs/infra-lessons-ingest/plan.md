# Plan: Infrastructure, Lesson Harvest, Repo-Ingest Workflow
**Date:** 2026-04-29
**Spec:** Approved inline — Director confirmed priorities in conversation
**Traceability:** ACTIVE

---

## Context

Three problems surfaced during the 2026-04-29 architecture audit:

1. **on-first-run.py fires every session** — `~/.dream-studio/config.json` is missing `director_name`, `claude_memory_path`. Also `skills/learn/config.yml` has `harvest.projects_root` empty. These three config gaps cause the recurring warning and block `learn: harvest`.

2. **26 draft lessons are unprocessed** — All in `~/.dream-studio/meta/draft-lessons/`. Breakdown: 18 are `on-context-threshold` handoff events (individual session noise), 4 are `theme-high-context` (recurring pattern, may warrant a gotcha), 4 are `theme-sonnet` (intentional model choice → REJECT). Need triage.

3. **No formalized repo-ingest workflow** — External repos are ingested ad-hoc. No version tracking, no refresh cadence, no handoff to the right domain YAML. The `repo-integration-analysis-v2.md` plan identified this gap; the domain YAMLs were created but no ongoing intake process was built.

**Confirmed non-issue:** `packs/` vs `skills/` is NOT a duplication. packs/ is live Python hook infrastructure (on-pulse.py, on-meta-review.py, etc.). skills/ is Claude skill guidance loaded by on-skill-load.py. They are different layers of the same system. No migration needed — but the distinction needs to be documented.

---

## Requirements

| TR-ID | Description | Priority | Layer |
|-------|-------------|----------|-------|
| TR-001 | Config gaps fixed: director_name, claude_memory_path (config.json) + harvest.projects_root (learn/config.yml) | must | infra |
| TR-002 | 26 draft lessons triaged: bulk-rejected, 0-1 promoted to gotchas.yml after dedup | must | lessons |
| TR-003 | `workflow: repo-ingest` node built in workflow/SKILL.md | must | ingest |
| TR-004 | `domains/ingest-log.yml` schema created; existing domain YAMLs backfilled | should | ingest |
| TR-005 | packs/ vs skills/ distinction documented in ARCHITECTURE.md | should | infra |
| TR-006 | JIT skill depth policy documented; polish/SKILL.md references its checklists | should | quality |

---

## Technical Context

| Area | SSOT | Notes |
|------|------|-------|
| Global config | `~/.dream-studio/config.json` | director_name + claude_memory_path live here |
| Harvest config | `skills/learn/config.yml` | projects_root + extra_paths |
| Draft lessons | `~/.dream-studio/meta/draft-lessons/` | Source for lesson triage |
| Promoted lessons | `~/.dream-studio/meta/lessons/` | Archive destination |
| Plugin hooks | `packs/*/hooks/*.py` | Live Python — do NOT edit without testing |
| Skill guidance | `skills/*/SKILL.md` | Claude reads these at skill invocation via on-skill-load.py |
| Ingest registry | `skills/domains/ingest-log.yml` | To be created |
| Workflow skill | `skills/workflow/SKILL.md` | Where repo-ingest node lives |

---

## Architecture: repo-ingest node design

The `workflow: repo-ingest` node should:

1. Accept a repo URL or local path as input
2. Determine the domain (BI, security, devops, testing, design, etc.) from content scan
3. Extract patterns into the matching `skills/domains/<domain>/*.yml`
4. Write a log entry to `skills/domains/ingest-log.yml` with:
   - repo name, URL, stars, commit/date analyzed
   - domain mapped to
   - files touched
   - refresh-due date (6 months default)
5. Alert Director if the repo maps to a domain with no existing YAML (new domain detected)

This is intentionally a WORKFLOW node, not a new skill — it orchestrates think + build steps and should live in workflow/SKILL.md as a named workflow node.

---

## Skill depth gap policy (TR-006)

**Decision: JIT enrichment only.** No manual sprint to enrich all 37 skills.

Rules:
1. When a thin skill is about to be used for a real build, run one task first: add 2-3 examples + update gotchas.yml from the build
2. The `learn` skill + `repo-ingest` workflow are the ongoing depth builders
3. Immediate one-time fix only: `polish/SKILL.md` must reference its `checklists/` directory (currently disconnected)
4. Thin skills that need a "this skill enriches on first use" marker: mcp-build, dashboard-dev, saas-build, career suite

---

## Next in pipeline
→ `build` — execute tasks.md
