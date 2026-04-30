# Pack Consolidation Plan

## Problem
Claude Code has a character budget (~5-8K chars) for skill descriptions shared across ALL plugins. dream-studio has 37 skills — only 6 load, the rest are silently dropped. Anyone installing dream-studio from GitHub hits this out of the box.

## Solution
Consolidate 37 individual skills into 7 pack-level router skills that dispatch to sub-modes on demand. Total description cost drops from ~10,000 to ~600 chars.

## Architecture

### Before (37 discoverable skills)
```
skills/
  think/SKILL.md          ← discovered as dream-studio:think
  plan/SKILL.md           ← discovered as dream-studio:plan
  build/SKILL.md          ← discovered as dream-studio:build
  ... (37 total)
  core/                   ← shared modules (no SKILL.md, not discovered)
    git.md, format.md, quality.md, orchestration.md, traceability.md, repo-map.md
```

### After (7 discoverable skills)
```
skills/
  core/
    SKILL.md              ← discovered as dream-studio:core (router)
    git.md, format.md ... ← shared modules stay in place
    modes/
      think/SKILL.md      ← NOT discovered (nested too deep)
      plan/SKILL.md
      build/SKILL.md
      review/SKILL.md
      verify/SKILL.md
      ship/SKILL.md
      handoff/SKILL.md
      recap/SKILL.md
      explain/SKILL.md
  quality/
    SKILL.md              ← discovered as dream-studio:quality (router)
    modes/
      debug/SKILL.md
      polish/SKILL.md
      harden/SKILL.md
      secure/SKILL.md
      structure-audit/SKILL.md
      learn/SKILL.md
      coach/SKILL.md
  career/
    SKILL.md              ← discovered as dream-studio:career (router)
    modes/
      ops/SKILL.md
      scan/SKILL.md
      evaluate/SKILL.md
      apply/SKILL.md
      track/SKILL.md
      pdf/SKILL.md
  security/
    SKILL.md              ← discovered as dream-studio:security (router)
    modes/
      scan/SKILL.md
      dast/SKILL.md
      binary-scan/SKILL.md
      mitigate/SKILL.md
      comply/SKILL.md
      netcompat/SKILL.md
      dashboard/SKILL.md
  analyze/
    SKILL.md              ← discovered as dream-studio:analyze (router, replaces existing)
    modes/
      multi/SKILL.md      ← existing analyze content
      domain-re/SKILL.md
    analysts/             ← stays in place
  domains/
    SKILL.md              ← discovered as dream-studio:domains (router, new)
    modes/
      game-dev/SKILL.md
      saas-build/SKILL.md
      mcp-build/SKILL.md
      dashboard-dev/SKILL.md
      client-work/SKILL.md
      design/SKILL.md
    data/, powerbi/ ...   ← existing reference data stays in place
  workflow/
    SKILL.md              ← standalone (already works, unchanged)
```

### Key decisions

1. **`core/` shared modules stay put** — `git.md`, `format.md`, etc. remain at `skills/core/`. Import paths like `core/git.md` in all existing SKILL.md files continue to work with zero changes. The new `core/SKILL.md` router coexists alongside them.

2. **Sub-skill files keep the name SKILL.md** — Claude Code only discovers skills one level deep. `skills/core/modes/think/SKILL.md` is invisible to discovery. Keeping the filename makes it clear these are full skill definitions, just nested.

3. **`workflow` stays standalone** — It's already loaded and working. As the only skill in the `meta` pack, wrapping it in a router adds indirection for no benefit.

4. **`explain` moves to `core` pack** — It's part of understanding the build pipeline. packs.yaml didn't list it; we add it to core.

5. **Career skill mode names drop the `career-` prefix** — `career-ops` → `ops`, `career-scan` → `scan`, etc. The pack name already provides namespace.

6. **`security-dashboard` shortens to `dashboard`** — Same reasoning.

7. **`analyze` existing content becomes mode `multi`** — The current analyze skill does multi-perspective analysis. Under the pack, it becomes `analyze multi` (or auto-detected from keywords).

### Pack router pattern

Each pack-level SKILL.md follows this template:

```markdown
---
name: <pack>
description: <one line, ~80 chars, no trigger keywords>
argument-hint: "<mode1> | <mode2> | ..."
user_invocable: true
args: mode
---

# <Pack Name>

## Mode dispatch
1. Parse mode from argument (first word after pack name)
2. If no mode given, infer from user message using keyword table below
3. Read `modes/<mode>/SKILL.md` completely
4. Read `modes/<mode>/gotchas.yml` if it exists
5. Follow the mode instructions

| Mode | Keywords |
|---|---|
| think | think:, spec:, research: |
| plan | plan: |
| ... | ... |
```

### Description budget after consolidation

| Skill | Description | ~Chars |
|---|---|---|
| dream-studio:core | Build lifecycle — think, plan, build, review, verify, ship, handoff, recap, explain | 80 |
| dream-studio:quality | Code quality — debug, polish, harden, secure, audit, learn, coach | 70 |
| dream-studio:career | Career pipeline — search, evaluate, apply, track, resume | 60 |
| dream-studio:security | Enterprise security — scan, DAST, binary analysis, mitigate, comply, dashboard | 80 |
| dream-studio:analyze | Multi-perspective analysis and domain-specific evaluation | 55 |
| dream-studio:domains | Stack-specific builders — game, SaaS, MCP, dashboard, client-work, design | 75 |
| dream-studio:workflow | YAML workflow orchestration with DAG execution and state tracking | 65 |
| **Total** | | **~485** |

485 chars vs ~10,000 before. Fits in any budget with room to spare.

### Invocation changes

**Before:**
```
Skill(skill="dream-studio:think")
Skill(skill="dream-studio:debug")
Skill(skill="dream-studio:career-ops")
```

**After:**
```
Skill(skill="dream-studio:core", args="think")
Skill(skill="dream-studio:quality", args="debug")
Skill(skill="dream-studio:career", args="ops")
```

Users typing slash commands:
- Before: `/dream-studio:think`
- After: `/dream-studio:core think`

### CLAUDE.md routing table (after)

The routing table shrinks from 35+ rows to 7:

```markdown
| Intent | Skill | Trigger keywords |
|---|---|---|
| Build lifecycle | dream-studio:core | think:, plan:, build:, review:, verify:, ship:, handoff:, recap:, explain: |
| Code quality | dream-studio:quality | debug:, polish:, harden:, secure:, audit:, learn:, coach: |
| Career tools | dream-studio:career | career:, job search, evaluate offer, apply, track |
| Security analysis | dream-studio:security | scan:, dast:, binary-scan:, mitigate:, comply:, netcompat:, dashboard: |
| Analysis engine | dream-studio:analyze | analyze:, domain-re:, evaluate idea |
| Domain builders | dream-studio:domains | game:, saas:, mcp:, dashboard-dev:, client-work:, design: |
| Workflow orchestration | dream-studio:workflow | workflow: |
```

### What stays unchanged
- All SKILL.md content (instructions, steps, anti-patterns) — moved but not modified
- All `core/` shared modules — untouched, import paths still work
- All per-skill metadata (gotchas.yml, config.yml, metadata.yml) — moved with their skill
- All per-skill subdirectories (analysts/, templates/, examples/) — moved intact
- workflow skill — completely untouched
- Hooks infrastructure — no changes needed
- Agent definitions — no changes needed

### Risks
1. **Import path breakage** — Skills that reference `core/git.md` should still work since core/ stays in place. BUT skills that reference other skills (e.g., ship imports from review) need path updates if those skills moved.
2. **sync-cache.ps1** — Currently syncs flat skills. Needs to handle nested modes/.
3. **Existing sessions/handoffs** — Any in-progress session referencing old skill paths will break. This is a clean-break change.
