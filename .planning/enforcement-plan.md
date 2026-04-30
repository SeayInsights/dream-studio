# Plan: dream-studio enforcement + gap closure
Date: 2026-04-29
Context: Session audit identified 13 critical gaps. This plan closes them in priority order.

## SSOT references
- Source: `C:\Users\Dannis Seay\builds\dream-studio\skills\`
- Cache (active): `C:\Users\Dannis Seay\.claude\plugins\cache\dream-studio\dream-studio\0.2.0\skills\`
- Global CLAUDE.md: `C:\Users\Dannis Seay\.claude\CLAUDE.md`
- Builds CLAUDE.md (full routing): `C:\Users\Dannis Seay\builds\dream-studio\CLAUDE.md`

## Tasks

### Task 1 — Add preload block to all skill SKILL.md files
- Scope: all skills in `builds/skills/` EXCEPT client-work (already done)
- Add at top of each SKILL.md, after frontmatter:
  ```
  ## Before you start
  Read `gotchas.yml` in this directory before every invocation.
  ```
- For skills with project-level work (debug, build, think): also add:
  ```
  If the project has `.planning/GOTCHAS.md` — read it before starting.
  If the project has `.planning/CONSTITUTION.md` — read it before starting.
  ```
- Files: all SKILL.md in analyze, binary-scan, build, career-*, coach, comply, dast, dashboard-dev, debug, design, domain-re, game-dev, handoff, harden, learn, mcp-build, mitigate, netcompat, plan, polish, recap, review, saas-build, scan, secure, security-dashboard, ship, structure-audit, think, verify, workflow
- Acceptance: every SKILL.md starts with a "Before you start" section

### Task 2 — Populate gotchas.yml for high-traffic skills
- Priority order: build, debug, review, verify, secure, think, plan
- Each needs at minimum: 2-3 real avoid entries from known failure patterns
- Source material: this session's audit + the existing DreamySuite GOTCHAS.md patterns
- Acceptance: no `avoid: []` in the 7 priority skills

### Task 3 — Add project-level GOTCHAS.md check to debug and build skills
- `debug/SKILL.md`: add step 0 — "If project has `.planning/GOTCHAS.md`, read it before forming hypotheses"
- `build/SKILL.md`: add step 0 — "If project has `.planning/GOTCHAS.md` and `.planning/CONSTITUTION.md`, read both before executing any task"
- Acceptance: both skills explicitly gate on project-level files

### Task 4 — Add CONSTITUTION.md check to think skill
- `think/SKILL.md`: add to step 1 (Clarify) — "If `.planning/CONSTITUTION.md` exists, read it before writing any spec. Surface any conflicts with existing decisions."
- Acceptance: think doesn't contradict existing architecture

### Task 5 — Add constitution + gotchas scaffolding to harden skill
- `harden/SKILL.md`: add a section — "If `CLAUDE.md`, `.planning/CONSTITUTION.md`, `.planning/GOTCHAS.md` don't exist, create them before any other hardening work. These are the project memory system."
- Acceptance: harden creates the three files as step 1 for any project missing them

### Task 6 — Sync global CLAUDE.md routing from builds/CLAUDE.md
- Read `builds/dream-studio/CLAUDE.md` routing table (full, with security pack, career, analysis, domain-re, etc.)
- Update `~/.claude/CLAUDE.md` routing table to match — it's currently missing ~15 skills
- Acceptance: global CLAUDE.md routes to every skill that exists in the cache

### Task 7 — Audit cache vs builds skill inventory
- List all skill directories in builds/skills/
- List all skill directories in cache/skills/
- Identify which skills are in builds but NOT in cache (these can't be invoked)
- Document the gap; flag skills that need to be manually synced to cache
- Acceptance: complete inventory of what's live vs what's orphaned in builds

### Task 8 — Add builds→cache sync to Makefile
- Add a `make sync-cache` target that copies all skills from `builds/skills/` to the cache path
- Should NOT overwrite engine-ref/ or other cache-only dirs
- Acceptance: `make sync-cache` keeps builds and cache in sync without manual copy

### Task 9 — Update REGISTRY.md
- Add client-work's bi-developer subagent dependency
- Add any other dependency changes made this session
- Acceptance: REGISTRY.md reflects current actual dependencies

### Task 10 — Create domains/bi/ module
- Extract Power BI domain logic from client-work/SKILL.md into `domains/bi/dax-patterns.md`, `domains/bi/m-query-patterns.md`
- client-work SKILL.md references these instead of embedding
- Acceptance: domains/bi/ exists with real content, SKILL.md references it

## Order
Run in sequence: 1 → 3 → 4 → 5 → 6 → 7 → 8 → 2 → 9 → 10
(Preload must be in all skills before populating gotchas.yml pays off)
