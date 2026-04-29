# dream-studio — Project Instructions

## Skill Routing

When the user's intent matches a dream-studio skill, invoke it via the Skill tool — never fall back to built-in Claude behavior. Match on the trigger keywords below. Exception: if the user explicitly says "built-in" (e.g. "built-in plan"), use native behavior.

### Exploration & Research
Not every request needs a full skill. Casual lookups get dispatched as lightweight subagents:
- **"go check", "look into", "investigate", "what's going on with"** → Spawn an Explore subagent (Haiku model). Quick codebase/file lookup, report back.
- **"research", "dig into", "explore options"** → If scoped to a codebase question, use Explore. If it needs design thinking or spec work, escalate to `dream-studio:think` with the `research:` trigger.
- **"go find", "where is", "search for"** → Explore subagent or direct Grep/Glob — no skill needed.

<!-- BEGIN AUTO-ROUTING -->
### Build Pipeline (sequential: think → plan → build → review → verify → ship)
| Intent | Skill | Triggers |
|--------|-------|----------|
| Execute a plan with subagent-driven development — fresh agent per task, two-stage review, isolated context, parallel wave execution. | `dream-studio:build` | build:, execute plan: |
| Trace how X works — from entry point through layers to output, at the depth the Director needs | `dream-studio:explain` | explain:, how does, walk me through, what is this doing, why does |
| Session continuity — capture structured state (current task, progress, phase, decisions, active files, next action) to both markdown and JSON. A fresh session resumes from the file alone. | `dream-studio:handoff` | handoff: |
| Break an approved spec into atomic, dependency-ordered tasks with per-task acceptance criteria. | `dream-studio:plan` | plan:, /plan |
| Capture structured build memory — what was built, decisions, risks, stack, remaining work, next step — to `.sessions/YYYY-MM-DD/recap-<topic>.md`. | `dream-studio:recap` | recap:, session recap: |
| Two-stage quality check — spec compliance first (did we build what was asked?), then code quality (is it well-built?) — with severity-tagged findings. | `dream-studio:review` | review:, review code, review PR: |
| Pre-deploy gate — audit (a11y, perf, technical), harden (error/empty/loading states), optimize (bundle/render/animation/images), test (Playwright + regression). Any FAIL blocks deploy. | `dream-studio:ship` | ship:, pre-deploy:, deploy: |
| Clarify an idea, explore 2-3 approaches with trade-offs, write a spec, and get approval before any code. | `dream-studio:think` | think:, spec:, shape ux:, design brief:, research: |
| Evidence-based verification — run the app, test golden path + edges, capture proof (screenshots, logs, Playwright results), check regressions. | `dream-studio:verify` | verify:, prove it: |

### Quality & Learning
| Intent | Skill | Triggers |
|--------|-------|----------|
| Systematic problem solving — reproduce, hypothesize, test one variable at a time, narrow, fix, document. No shotgun debugging. | `dream-studio:debug` | debug:, diagnose: |
| Project hardening audit and fix — checks 20 best-practice items (Makefile, pyproject.toml, UTC enforcement, Pydantic validation, SECURITY.md, CONTRIBUTING.md, test tooling, audit log, pre-commit, etc.) and fills gaps from templates. | `dream-studio:harden` | /harden, /harden audit, /harden fix tier1, /harden fix #N |
| Capture and promote lessons from builds — draft to `meta/draft-lessons/`, Director review, promote to memory / skill / agent updates, archive to `meta/lessons/`. | `dream-studio:learn` | meta/draft-lessons/, meta/lessons/, learn:, capture lesson: |

### Visual & Design
| Intent | Skill | Triggers |
|--------|-------|----------|
| Visual design capability — brand tokens, anti-slop rules, visual hierarchy, generative art (p5.js), theme application to projects, and ad-creative guidance. | `dream-studio:design` | design art:, design poster:, canvas:, generative art:, apply theme:, brand:, ad creative: |
| UI quality decision tree — critique seven dimensions (layout, typography, color, animation, copy, responsive, edge cases), score 1-5, fix by priority, re-score. | `dream-studio:polish` | polish ui:, critique design:, redesign:, make it premium:, build page:, build component: |

### Domain Builders
| Intent | Skill | Triggers |
|--------|-------|----------|
| Tauri + React desktop dashboard patterns — feed contract (hooks write JSON, dashboard reads), multi-panel architecture, additive schema evolution. | `dream-studio:dashboard-dev` | dashboard:, feed contract: |
| 4-phase MCP server development — research, implement (Zod schemas, structured errors, stdio/SSE transport), test (valid/invalid/edge), evaluate. | `dream-studio:mcp-build` | build mcp:, new mcp:, extend mcp: |
| React 19 + React Router 7 + Cloudflare Workers + D1/Kysely stack patterns for SaaS builds — API contract-first, loaders/actions, migrations, CI-only deploys. | `dream-studio:saas-build` | build feature:, build api:, build page:, deploy:, build supabase: |

### Session Management
| Intent | Skill | Triggers |
|--------|-------|----------|
| YAML workflow orchestration — validate, execute DAG nodes through existing skills with gates and parallel spawning, track state via CLI. | `dream-studio:workflow` | workflow: |
<!-- END AUTO-ROUTING -->

### Routing Fallback

If the user's intent does not match any trigger keyword in the tables above, route to `dream-studio:coach` with mode `route-classify`. Coach will classify the intent, map it to the nearest skill, and explain confidence + alternatives. This prevents unmatched intents from falling through to raw Claude default behavior.

## GitHub Workflow
- **Never push directly to `main`** — always create a feature branch first.
- Before starting PR work, check for open PRs on the repo (`gh pr list`) to avoid conflicts or duplicate work.
- Branch naming: `feat/<topic>`, `fix/<topic>`, `chore/<topic>` — keep it short and descriptive.
- Keep PRs under ~120 lines of changes. Split larger work into independent PRs.
- Before creating a PR, check for a pull request template in the repo (`.github/PULL_REQUEST_TEMPLATE.md` or `.github/PULL_REQUEST_TEMPLATE/`).
- Use `gh` CLI for all GitHub operations (PRs, issues, releases), not the MCP GitHub tools.
- Never force-push without explicit user approval.
- Never push to stale/old branches — check branch freshness first.
- **Before pushing to a branch with an existing PR**, run `gh pr view <branch> --json state` to check if it's been merged or closed. If merged/closed, pull latest main, create a new branch, cherry-pick or reapply changes, and open a new PR. Never push commits to a branch whose PR is already merged.

## Commits
- Never add Co-Authored-By attribution to git commits.
- One logical change per commit. Commit messages should explain why, not what.

## Deploys
- Never run `wrangler deploy` or any direct deploy command — push to GitHub and let CI handle it.

## Model Usage
- Use Haiku for searches/exploration subagents; Sonnet for code-change subagents.

## Portable Setup
If using dream-studio as a plugin in another project, add this to your global `~/.claude/CLAUDE.md`:
```markdown
## dream-studio overrides
- When the user's intent matches a dream-studio skill trigger, invoke the skill via the Skill tool — never fall back to built-in Claude behavior. See the Skill Routing table in the dream-studio CLAUDE.md for the full mapping.
- For GitHub workflow, follow the conventions in the dream-studio CLAUDE.md.
```
