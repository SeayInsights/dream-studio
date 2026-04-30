# dream-studio — Project Instructions

## Skill Routing

When the user's intent matches a dream-studio skill, invoke it via the Skill tool — never fall back to built-in Claude behavior. Match on the trigger keywords below. Exception: if the user explicitly says "built-in" (e.g. "built-in plan"), use native behavior.

### Exploration & Research
Not every request needs a full skill. Casual lookups get dispatched as lightweight subagents:
- **"go check", "look into", "investigate", "what's going on with"** → Spawn an Explore subagent (Haiku model). Quick codebase/file lookup, report back.
- **"research", "dig into", "explore options"** → If scoped to a codebase question, use Explore. If it needs design thinking or spec work, escalate to `dream-studio:core` with arg `think`.
- **"go find", "where is", "search for"** → Explore subagent or direct Grep/Glob — no skill needed.

<!-- BEGIN AUTO-ROUTING -->
### Pack-Based Routing

Each pack is one skill with modes. Invoke via `Skill(skill="dream-studio:<pack>", args="<mode>")`. If the user's message matches a keyword, invoke the pack and let the router infer the mode.

| Pack | Skill | Mode keywords |
|------|-------|---------------|
| Build lifecycle | `dream-studio:core` | **think:** spec:, research:, shape ux: · **plan:** plan: · **build:** build:, execute plan: · **review:** review:, review code:, review PR: · **verify:** verify:, prove it: · **ship:** ship:, pre-deploy:, deploy: · **handoff:** handoff: · **recap:** recap:, session recap: · **explain:** explain:, how does, walk me through, what is this doing, why does |
| Code quality | `dream-studio:quality` | **debug:** debug:, diagnose: · **polish:** polish ui:, critique design:, redesign: · **harden:** /harden, harden audit · **secure:** secure:, security review: · **structure-audit:** /structure-audit · **learn:** learn:, capture lesson: · **coach:** /coach, workflow coaching: |
| Career pipeline | `dream-studio:career` | **ops:** career:, job search · **scan:** scan jobs:, find jobs: · **evaluate:** evaluate offer:, evaluate gig: · **apply:** apply:, cover letter:, tailor resume: · **track:** track:, pipeline: · **pdf:** resume:, generate pdf: |
| Security analysis | `dream-studio:security` | **scan:** scan:, scan org:, run security scan: · **dast:** dast:, web scan: · **binary-scan:** binary-scan:, analyze exe: · **mitigate:** mitigate:, fix findings: · **comply:** comply:, SOC 2:, NIST: · **netcompat:** netcompat:, Zscaler: · **dashboard:** security dashboard:, export dataset: |
| Analysis engine | `dream-studio:analyze` | **multi:** analyze:, evaluate idea:, /analyze · **domain-re:** domain-re:, real estate: |
| Domain builders | `dream-studio:domains` | **game-dev:** game:, game build: · **saas-build:** build feature:, build api:, build page: · **mcp-build:** build mcp:, new mcp:, extend mcp: · **dashboard-dev:** dashboard:, feed contract: · **client-work:** intake:, sow:, build powerbi:, optimize dax:, build flow:, build app: · **design:** design art:, design poster:, canvas:, brand: |
| Workflow orchestration | `dream-studio:workflow` | workflow: |
<!-- END AUTO-ROUTING -->

### Routing Fallback

If the user's intent does not match any keyword above, route to `dream-studio:quality` with arg `coach`. Coach will classify the intent, map it to the nearest pack and mode, and explain confidence + alternatives.

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
