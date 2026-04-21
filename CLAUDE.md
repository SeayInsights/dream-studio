# dream-studio — Project Instructions

## Planning
- When the user asks to "plan", "make a plan", or uses `/plan`, invoke the `dream-studio:plan` skill — never use the built-in EnterPlanMode.
- The only exception is if the user explicitly says "built-in plan" or "native plan".
- The dream-studio plan pipeline is: `think` (spec) → `plan` (decompose) → `build` (execute). Follow this sequence.

## GitHub Workflow
- **Never push directly to `main`** — always create a feature branch first.
- Before starting PR work, check for open PRs on the repo (`gh pr list`) to avoid conflicts or duplicate work.
- Branch naming: `feat/<topic>`, `fix/<topic>`, `chore/<topic>` — keep it short and descriptive.
- Keep PRs under ~120 lines of changes. Split larger work into independent PRs.
- Before creating a PR, check for a pull request template in the repo (`.github/PULL_REQUEST_TEMPLATE.md` or `.github/PULL_REQUEST_TEMPLATE/`).
- Use `gh` CLI for all GitHub operations (PRs, issues, releases), not the MCP GitHub tools.
- Never force-push without explicit user approval.
- Never push to stale/old branches — check branch freshness first.

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
- When planning, use the `dream-studio:plan` skill instead of built-in plan mode.
- For GitHub workflow, follow the conventions in the dream-studio CLAUDE.md.
```
