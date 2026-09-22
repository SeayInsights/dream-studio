# dream-studio — Contributor Instructions

Instructions for working **on** this codebase.

This file used to also describe how to **operate** an installed Dream Studio —
skill routing, `ds` CLI commands, the SQLite authority, the blocking hooks, the
merge-authorization rule. That content is gone, deliberately. It was never
uniquely useful here and it was actively misleading:

- **Nobody installing Dream Studio ever reads this file.** The product ships from
  `dist/plugin`, which contains neither `CLAUDE.md` nor `AGENTS.md`. An installer
  gets `~/.claude/CLAUDE.md`, written by the installer from a generated
  projection that carries `AUTO-ROUTING` markers so it can be updated in place.
  This file has none of those markers, so it is not a projection at all.
- **With Dream Studio installed**, the operator instructions were a second,
  drifting copy of what `~/.claude/CLAUDE.md` already said.
- **Without it installed**, they directed every session at 13 skills, a SQLite
  authority and a set of blocking hooks that do not exist — which is exactly what
  happened after an uninstall on 2026-09-21. The operator content survived the
  uninstall because it was checked into git, and kept steering work at a runtime
  that had been removed.

Operator instructions belong in the generated projection the installer writes and
the uninstaller removes. Keep this file about the repository.

## Running tests

Pytest output on Windows + PowerShell can be UTF-16-encoded and report misleading
exit codes. To run tests reliably:

```powershell
py -m pytest <args> > pytest-output.txt 2>&1
Get-Content pytest-output.txt -Encoding UTF8
```

Ignore the exit code from the first command. The pytest summary line in the file
(`=== N passed in X.XXs ===`) is authoritative.

If output is truncated, run via cmd instead:

```powershell
cmd /c "py -m pytest <args>"
```

Windows SIGINT handling is already configured in `spool/ingestor.py` (module-level
CTRL_C handler) and `tests/conftest.py` (pytest-level SIGINT handler). No env vars
or workarounds needed.

The full unit suite takes roughly 35 minutes on Windows and does not OOM
(6,044 passed / 25 failed, measured 2026-09-21).

## Gates

The repository's own quality gates are declared in
`canonical/workflows/pre-push.yaml` and run with:

```
py -m core.gates.pre_push
```

They are ordinary Python and need no Dream Studio install. A gate that names a
test file or module which does not exist fails before it checks anything, so
`tests/unit/test_gate_manifests_name_real_files.py` resolves every path and
module both that manifest and `.github/workflows/ci.yml` name.

Writing any output? Use a temp directory. Diagnostic output at the repository
root is not wanted, and nothing here should write into `~/.dream-studio`.

## GitHub workflow

- **Never push directly to `main`** — always create a feature branch first.
- Check for open PRs (`gh pr list`) before starting, to avoid duplicate work.
- Branch naming: `feat/<topic>`, `fix/<topic>`, `chore/<topic>`.
- Keep PRs small. Split larger work into independent PRs.
- Use the `gh` CLI for GitHub operations, not MCP GitHub tools.
- Never force-push without explicit approval.
- Before pushing to a branch that already has a PR, check whether that PR was
  merged or closed (`gh pr view <branch> --json state`). Never push to a branch
  whose PR is already merged — branch from current `main` instead.

## Commits

- Never add Co-Authored-By or "Generated with" attribution. Never use emoji.
- One logical change per commit. Explain **why**, not what.
- Keep mechanical formatting in its own commit — never mixed with a refactor.

## Before and after a source edit

- Read the relevant git history first. A thing that looks missing is often a
  deliberate deletion: `git log --diff-filter=D -- <path>`.
- Check whether a file is **generated** before editing it. Several checked-in
  artifacts are — `canonical/review_lanes.yml`, `canonical/rules.yml`,
  `canonical/normative_baseline.json`, `AGENTS.md`, `dist/plugin/**` and others.
  Edit the generator; an edit to the artifact is discarded by the next render.
- Classify what you are touching: product source, generated artifact, test
  fixture, local state, or external target.
- After the change, validate imports, public API and route contracts, read-model
  shapes, and anything reading a SQLite boundary you moved.

## Deploys

Never run `wrangler deploy` or any direct deploy command. Push and let CI handle
it.

## Subagents

Haiku for search and exploration; Sonnet for code changes.
