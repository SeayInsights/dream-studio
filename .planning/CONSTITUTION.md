# Constitution

## SSOT Map

**Core Skills** (`skills/core/`)
- `SKILL.md` — mode dispatch, routing table
- `modes/<mode>/SKILL.md` — individual mode implementations (think, plan, build, review, verify, ship, handoff, recap, explain)
- Shared modules: `git.md`, `format.md`, `quality.md`, `orchestration.md`, `traceability.md`, `repo-map.md`

**Pack Structure** (`skills/`)
- `core/` — build lifecycle (think → plan → build → review → verify → ship)
- `quality/` — code quality (debug, polish, harden, secure, structure-audit, learn, coach)
- `security/` — security analysis (scan, dast, binary-scan, mitigate, comply, netcompat, dashboard)
- `career/` — job search pipeline (ops, scan, evaluate, apply, track, pdf)
- `analyze/` — multi-perspective analysis (multi, domain-re)
- `domains/` — domain builders (game-dev, saas-build, mcp-build, dashboard-dev, client-work, design)
- `workflow/` — YAML workflow orchestration

**Planning** (`.planning/`)
- `specs/<topic>/` — feature specifications (spec.md, plan.md, tasks.md)
- `templates/` — reusable spec/plan/task templates
- `traceability.yaml` — requirements → tasks → commits mapping

**Skill Catalog** (`skills/dream-studio-catalog.md`)
- Auto-generated from all SKILL.md files
- Shows metrics: success rate, token usage, usage count
- Updated after each build

## Key Decisions

**1. Pack-based architecture (2026-04-27)**
- Skills organized into packs by cohesion (core, quality, security, domains, etc.)
- Each pack is one skill with modes (not separate skills per mode)
- Invocation: `Skill(skill="dream-studio:<pack>", args="<mode>")`
- **Why:** Reduces skill count from 60+ to ~10, clearer cognitive model

**2. dream-studio overrides built-in Claude Code behaviors**
- `EnterPlanMode` → use `dream-studio:core plan`
- Built-in `review` → use `dream-studio:core review`
- Built-in `security-review` → use `dream-studio:quality secure`
- Built-in `init` → use `dream-studio:quality harden`
- **Why:** Python hooks can enforce this (BlockCommand), ensures dream-studio patterns are always used

**3. Spec-first workflow (think → plan → build)**
- No code until spec approved
- No plan until spec exists
- Spec template enforces P1/P2/P3 user story prioritization
- **Why:** Prevents premature implementation, enables incremental delivery

**4. Subagent-driven builds for 4+ tasks**
- Fresh subagent per task (no session history inheritance)
- Two-stage review (spec compliance, then code quality)
- Parallel waves for independent tasks
- **Why:** Preserves controller context, isolated task focus

**5. Traceability for 4+ task features**
- `.planning/traceability.yaml` links requirements → tasks → commits → tests
- TR-IDs in commit messages
- Status lifecycle: planned → in_progress → implemented → verified
- **Why:** Audit trail for compliance, coverage reporting

## Forbidden Patterns

**1. Never commit without Co-Authored-By footer**
- User explicitly does NOT want Claude listed as collaborator
- Remove any `Co-Authored-By: Claude` lines from commits

**2. Never push directly to main**
- Always create feature branch (`feat/`, `fix/`, `chore/`)
- Check for open PRs before starting work (`gh pr list`)
- Never push to stale/closed PR branches

**3. Never run `wrangler deploy` directly**
- CI handles deploys after merge
- Manual deploys bypass quality gates

**4. Never skip CONSTITUTION.md or GOTCHAS.md on 5+ file projects**
- Build mode has a STOP gate for this
- Run `dream-studio:quality harden` to scaffold

**5. Never use EnterPlanMode or built-in skills**
- Hooks will block these
- Always route through dream-studio packs

**6. Never write specs with only one approach**
- Always explore 2-3 alternatives with trade-offs
- Spec without alternatives is a decision disguised as exploration

**7. Never dispatch parallel subagents that write to the same file**
- Race conditions silently lose work
- Check file ownership in dependency analysis

**8. Never continue past major drift without approval**
- Minor drift (variable names) → note and continue
- Major drift (new dependencies, scope change) → STOP and surface
