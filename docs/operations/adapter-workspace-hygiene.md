# Adapter Workspace Hygiene

Dream Studio adapters may create scratch files, nested worktrees, session logs,
temporary prompts, local caches, and runtime artifacts. Those files are not
product source and must not make the Dream Studio repo look dirty.

## Policy

Repo source may contain only:

- product source, tests, public docs, contracts, templates, and examples;
- intentional active adapter projection surfaces such as `AGENTS.md` and
  `CLAUDE.md`;
- generated adapter projection artifacts under `adapter-projections/`.

Adapter scratch/worktree/session files belong in one of two places:

- user-local Dream Studio state such as `~/.dream-studio/adapters/`,
  `~/.dream-studio/worktrees/`, or `~/.dream-studio/sessions/`;
- an explicitly local-excluded repo area for tool-managed checkout-local state.

Machine-specific adapter scratch paths are excluded through
`.git/info/exclude`, not broad repo `.gitignore` rules, when the pattern is
local to one checkout. The setup flow maintains these local-only patterns:

```text
.claude/worktrees/
.codex/sessions/
.codex/tasks/
.codex/tmp/
.adapter-scratch/
.ai-scratch/
```

Repo `.gitignore` should only contain patterns safe for every user and every
checkout. It must not hide product source, tracked `.claude` configuration,
active `AGENTS.md`/`CLAUDE.md` surfaces, or `adapter-projections/` artifacts.

## Classification

Use these classifications before taking action:

| Path family | Classification | Action |
| --- | --- | --- |
| `AGENTS.md`, `CLAUDE.md` | active adapter projection | tracked repo source |
| `adapter-projections/**` | generated adapter projection | tracked generated artifact |
| `.claude/worktrees/**` | local adapter scratch | local `.git/info/exclude` |
| `.codex/sessions/**`, `.codex/tasks/**`, `.codex/tmp/**` | local adapter scratch | local `.git/info/exclude` |
| `~/.dream-studio/adapters/**`, `~/.dream-studio/worktrees/**`, `~/.dream-studio/sessions/**` | user-local adapter state | outside repo source |
| unknown adapter files | manual review | classify before ignore/delete/archive |
| secret/auth/token/credential paths | sensitive manual review | path-only metadata; do not read or print values |

Generated adapter projections remain distinguishable from active adapter config:
files under `adapter-projections/` are verification/export artifacts until an
approved projection repair or install flow copies, links, or refreshes an
active adapter surface.

## Setup Behavior

`interfaces/cli/setup.py --check --json` reports local adapter exclude
readiness without writing files. Normal setup applies checkout-local excludes by
updating `.git/info/exclude`. This is intentionally local-only and is not a
source-controlled `.gitignore` mutation.

If an adapter creates a new scratch path, add the narrowest local-exclude pattern
to `core.release.adapter_workspace_hygiene.LOCAL_ADAPTER_EXCLUDE_PATTERNS` and
cover it with a test. Do not add broad ignores such as `.claude/` or `.codex/`
unless every path hidden by that rule is known non-source for all users.

## Validation

Before closing adapter hygiene work, verify:

- `git status --short --branch --untracked-files=all` is clean;
- `AGENTS.md`, `CLAUDE.md`, and `adapter-projections/**` are still tracked when
  intended;
- adapter worktrees and session scratch paths do not appear in status;
- product source is not accidentally ignored;
- no secret/auth files were read or printed;
- no live SQLite mutation occurred.
