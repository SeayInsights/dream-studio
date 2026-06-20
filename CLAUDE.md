# dream-studio — Project Instructions

## Adapter Projection Boundary

Dream Studio is a local-first AI orchestration and operational intelligence
platform. Claude Code is one adapter surface, not the product identity and not
the source of truth.

This file is a Claude-facing projection of Dream Studio authority. Canonical
state lives in the repo source, the operator-local SQLite authority database,
and evidence records. Dashboard output is derived, private model memory is not
authority, and adapter-specific instructions must stay thin projections.

Projection source:
- `sqlite:adapter_authority_profiles`
- `sqlite:shared_context_packets`
- `repo:canonical/skills/`, `repo:canonical/workflows/`, `repo:hooks/`
- file-backed evidence under the operator-local Dream Studio meta store

## Skill Routing

When the user's intent matches a dream-studio skill, invoke it via the Skill tool — never fall back to built-in Claude behavior. Match on the trigger keywords below. Exception: if the user explicitly says "built-in" (e.g. "built-in plan"), use native behavior.

### Exploration & Research
Not every request needs a full skill. Casual lookups get dispatched as lightweight subagents:
- **"go check", "look into", "investigate", "what's going on with"** → Spawn an Explore subagent (Haiku model). Quick codebase/file lookup, report back.
- **"research", "dig into", "explore options"** → If scoped to a codebase question, use Explore. If it needs design thinking or spec work, escalate to `ds-core` with arg `think`.
- **"go find", "where is", "search for"** → Explore subagent or direct Grep/Glob — no skill needed.

### Pack-Based Routing

The full pack-based routing table, the work-order types, and the gate definitions
are defined once in the generated universal target:

@AGENTS.md

Do **not** duplicate the routing table here — `AGENTS.md` is generated from
`packs.yaml` + `canonical/skills` + `canonical/workflows` and is the single source
of truth for routing. Regenerate it with
`py -m integrations.compiler.agents_md --write` whenever canonical skills,
workflows, or packs change (the AGENTS.md drift gate enforces this).

### Routing Fallback

If the user's intent does not match any keyword above, route to `ds-quality` with arg `coach`. Coach will classify the intent, map it to the nearest pack and mode, and explain confidence + alternatives.

## Dream Studio CLI — Decision Guide

### Session Start
The resume skill (`ds-project resume`) handles all session start logic.
It calls `ds project state` (one command) and presents a plain-English briefing.

**Do NOT manually call** `project list`, `project next`, or `work-order start` as
part of an orientation flow — the resume skill does this correctly in one step.

### During a Work Order
```
# Mark a task complete (call after each task):
py -m interfaces.cli.ds work-order task-done <work_order_id> <task_id>

# See remaining tasks:
py -m interfaces.cli.ds work-order tasks <work_order_id>

# If stuck on a bug — invoke ds-quality:debug
# If scope change needed — invoke ds-core:think
```

### Closing a Work Order
```
py -m interfaces.cli.ds work-order close <work_order_id>
```
Gates are checked automatically. If a gate fails, the close output tells you
which skill to invoke. Never `--force` close without explicit user approval.

### Gate Failures
- `design_brief_locked` → invoke `ds-website:discover` to fill the brief, then `ds design-brief lock <brief_id>`
- `api_contract_exists` → create the API contract document first
- `all_tests_pass` → fix failing tests

### Getting Project State (one command, everything)
```
py -m interfaces.cli.ds project state
```
Returns: active project, next WO, gate status, brief status, task counts, gotchas, and next action.

### Commands to NEVER call directly
- `ds project list` — resume skill handles this
- `ds project next` — resume skill handles this via `ds project state`
- `ds project set-active` — only needed when switching projects manually
- `ds design-brief update` — the design brief wizard skill handles this

### Milestone and design brief operations (when explicitly needed)
```
py -m interfaces.cli.ds milestone list <project_id>
py -m interfaces.cli.ds milestone close <milestone_id>
py -m interfaces.cli.ds design-brief show <project_id>
py -m interfaces.cli.ds design-brief lock <brief_id>
```

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

## Merge Authorization — Two-Tier Rule (universal, no exceptions)

**Push authorization:** pre-push gate green (format, lint, skill-sync, evals, atlas-leak, docs-drift).

**Merge authorization:** ALL THREE matrix platforms green — `ubuntu-latest`, `macos-latest`, `windows-latest`.

**The correct merge sequence for every PR:**
```powershell
gh pr ready <N>
gh pr checks <N> --watch   # wait for all 3 platforms — do NOT skip this
gh pr merge <N> --squash --delete-branch
```

Never chain `gh pr ready && gh pr merge`. That skips the matrix watch and is the documented cause of Phases 18.4.x post-merge hotfixes.

**Why this matters — the runtime/subset gap:** The pre-push gate runs `tests/evals/` only (a subset). The full unit suite takes ~79 minutes on Windows (subprocess.run() spawn overhead — 3–12s per subprocess call, 52 calls across 20 test files) and does NOT OOM (peak ~283MB of 16GB, verified 2026-05-29). Passing the pre-push gate is necessary but not sufficient. Local-green ≠ CI-green — not because of subtle platform quirks alone, but because the local gate runs less. The remote 3-platform `pr-smoke` matrix runs 4 focused gate test files + format/lint (NOT the full suite). The full suite runs ubuntu-only, post-merge in `full-ci.yml`. The matrix watch is the sole merge-authorization gate; it verifies what the PR smoke actually covers (gate tests + format/lint).

**Migration-class escalation:** Changes to `core/event_store/migrations/`, `core/config/sqlite_bootstrap.py`, or `core/event_store/event_store.py` (Python DDL sites) additionally trigger the `migration-risk` pre-push gate, which prints the matrix-watch reminder and blocks push until acknowledged. The matrix-watch rule applies universally; the migration-risk gate is an escalation for the historically highest-risk change class.

See `docs/operations/lightweight-github-ci-strategy.md` for the full rationale.

## Issue → PR Workflow (default for regular work)
1. Create GitHub issue via `gh issue create`
2. Create branch named after issue (e.g., `fix/issue-123-description`)
3. Implement, build, verify
4. Commit referencing issue: `fix: description (fixes #123)`
5. Push branch and create PR with issue reference in body: `Fixes #123`
6. `gh pr checks <N> --watch` — all 3 platforms green
7. Merge

## Debug Workflow
When `ds-quality debug` finds a root cause: register a Dream Studio authority work order first (status `created`, backlog sequence), then create the GitHub issue with the debug log and the WO id in the body, then follow Issue → PR workflow. A GitHub issue alone is NOT sufficient tracking — `get_next_work_order`, `ds project state`, and on-close routing only see the authority. Bugs found during Dream Command builds get tracked even if the fix is trivial.

**Defect WOs require an originating symptom.** When registering a WO for a bug or regression, capture the root-cause SQL check via `set_originating_symptom()` (or `--originating-symptom` on the CLI) immediately after WO creation. Example:
```python
set_originating_symptom(work_order_id=wo_id, symptom="SQL-CHECK: SELECT COUNT(*) FROM token_usage_records", source_root=...)
```
The close command re-runs this SQL at close time. If the check still fails (returns 0 or no rows), the WO is blocked from closing — the fix must land before the WO can be marked done.

## Ship Gate
Use `ds-core ship` (full quality gate) when user says "ship it", before major releases, client demos, or after risky refactors. Regular PRs do NOT need the ship gate — CI auto-deploys after merge.

## Commits
- Never add Co-Authored-By attribution to git commits.
- One logical change per commit. Commit messages should explain why, not what.

## Code History And Impact Guardrail
- Before source edits, inspect relevant git history, module purpose, architecture boundaries, tests, validation expectations, and related routes, read models, SQLite boundaries, telemetry, dashboard surfaces, hooks, skills, workflows, and adapter projections.
- Classify touched files as product source, generated artifact, test fixture, local state, external target, or private evidence before mutating them.
- After code or cleanup changes, validate imports, public API/route contracts, read-model and dashboard response shapes, temp/injected DB behavior, live-state boundaries, external-project boundaries, and release-gate impact.
- Keep mechanical formatting in its own commit. Do not mix formatting with semantic refactors.

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

## Running tests

Pytest output on Windows + PowerShell can be UTF-16-encoded and report misleading exit codes. To run tests reliably:

```powershell
py -m pytest <args> > pytest-output.txt 2>&1
Get-Content pytest-output.txt -Encoding UTF8
```

Ignore the exit code from the first command. The pytest summary line in the file (`=== N passed in X.XXs ===`) is authoritative.

If output is truncated, run via cmd instead:

```powershell
cmd /c "py -m pytest <args>"
```

Windows SIGINT handling is already configured in `spool/ingestor.py` (module-level CTRL_C handler) and `tests/conftest.py` (pytest-level SIGINT handler). No env vars or workarounds needed.
