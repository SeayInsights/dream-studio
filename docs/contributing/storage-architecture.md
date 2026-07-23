# Storage Architecture

This document defines where every kind of file in Dream Studio belongs. Following this architecture keeps the public repo clean, the operator workspace organized, and Claude Code's outputs predictable across sessions.

## Three storage scopes

Every file Dream Studio touches lives in exactly one of three scopes.

### Scope 1 — Repo content (ships publicly)

Tracked in git. Lives in `<repo>/<path>/` outside of any dotfile or tool-managed directory.

Includes: source code (`core/`, `runtime/`, `integrations/`, `interfaces/`, `projections/`, `emitters/`, `control/`, `spool/`, `hooks/`), canonical content (`canonical/`), tests (`tests/`), documentation (`docs/`), build/install scripts (`install.sh`, `install.ps1`), project meta-files (`README.md`, `LICENSE`, `pyproject.toml`, `requirements.txt`, `.gitignore`, `.pre-commit-config.yaml`), adapter projection files (`CLAUDE.md`, `AGENTS.md` at repo root).

### Scope 2 — Repo-internal working state (docstore, zero-disk)

Lives in the **files.db docstore** (category `planning`), NOT on disk. Local to the
operator's clone, never ships publicly. WO-FILESDB-P3 moved this off loose
`<repo>/.planning/` files: the on-edit enforcement hook now DENIES disk writes to
`.planning/**`. Author via `ds files write "<name>" --category planning` (read
`ds files read`; list `ds files list --category planning`). The subdirectory names
below are now **logical name prefixes** (e.g. name `workstreams/<id>/pr-body.md`),
not disk paths.

Subdirectories (logical name prefixes):

- `phases/` — phase-level docs (active roadmap)
- `phases/archive/` — closed phases moved out of the active doc tree
- `workstreams/<workstream-id>/` — per-workstream working files (PR drafts, inventories, recovery reports)
- `specs/<topic>/` — design specs being drafted before they land in canonical
- `workflows/<topic>/` — workflow YAML drafts
- `work-orders/<id>/` — work-order definition drafts (repo-scoped)
- `audits/` — investigation reports specific to this repo
- `audits/historical/` — superseded audits retained for historical reference
- `audits/graphify-out/` — generated graph artifacts (input to audits)
- `snapshots/` — baseline state captures
- `personal/` — operator notes, unstructured

### Scope 3 — Cross-repo / platform state

Lives in `~/.dream-studio/`. Created by the Dream Studio installer. Operator-local. Spans multiple repos.

Subdirectories:

- `state/` — SQLite DB and installer manifests
- `bin/` — global launcher scripts (`ds` CLI)
- `projects/<project-id>/` — per-project workspace (briefs, milestones, work orders, exports)
- `diagnostics/<YYYY-MM-DD>/<repo-name>/<session-purpose>/` — disposable session output
- `sessions/` — cross-repo session continuity (handoffs between sessions)
- `memory/` — cross-project memory store
- `backups/` — installer backups

## Tool-managed directories at repo root

Tools that need project-local config write to their own dotfile directories. Each is gitignored unless the team explicitly agrees to share that config:

- `.claude/` — Claude Code project config (gitignored; regenerated from `canonical/` by `ds integrate install claude_code`)
- `.git/` — git itself (neither tracked nor ignored)
- `.pytest_cache/` — pytest cache (gitignored, pure tool output, sweepable)
- `.vscode/` — VS Code settings. By default per-developer (gitignored), but Dream Studio commits `.vscode/extensions.json` and `.vscode/tasks.json` as shared infrastructure (recommended extensions and 23-task palette). Other `.vscode/` files (`settings.json`, `launch.json`) remain per-developer.
- `__pycache__/` — Python bytecode cache (gitignored, swept on demand)

## What does NOT belong at repo root

- Disposable test/lint/format output (`pytest-*.txt`, `black-*.txt`, `lint-*.txt`, etc.) → belongs in `~/.dream-studio/diagnostics/`
- PR body drafts → docstore: `ds files write "workstreams/<id>/pr-body.md" --category planning`
- Working notes, inventories, audit reports → docstore: `ds files write "<subcategory>/<name>.md" --category planning`
- Generated graphify output → docstore under name prefix `audits/graphify-out/`
- Build artifacts, debug scripts → belong in `~/.dream-studio/diagnostics/<date>/<repo>/<purpose>/`

If Claude Code writes a file outside its assigned scope, that's a discipline failure. The Output discipline section in the compiler's `_ENFORCEMENT_BLOCK` — regenerated into `.claude/CLAUDE.md` on every install — documents this; the on-edit enforcement hook denying `.planning/**` disk writes is the enforcement mechanism.

## Decision tree for new files

When creating a new file, ask in order:

1. Does it ship publicly to anyone who clones this repo? → **Scope 1**
2. Is it specific to this repo but private to the operator? → **Scope 2** (files.db docstore, `ds files write --category planning` — never `.planning/` on disk)
3. Is it operator-personal across repos OR tool/installer-managed? → **Scope 3** (`~/.dream-studio/`) or appropriate tool dotfile directory
4. Is it disposable session output? → **Scope 3 diagnostics**

If none fit, the file probably shouldn't exist. Stop, ask, route deliberately.

## Migration notes (Phase 0 — 2026-05-25)

This architecture was established during Phase 0 of the architectural realignment. Prior to Phase 0, the repo accumulated several parallel working directories: `.audit/`, `.sessions/`, `graphify-out/`, and various root-level disposable files. Those have been consolidated:

- `.audit/` content migrated to `.planning/audits/historical/` (historical audits), `.planning/specs/` (forward-looking plans), and `.planning/personal/` (working notes); `.audit/` directory removed
- `.sessions/` content migrated to `~/.dream-studio/sessions/`; `.sessions/` directory removed
- `graphify-out/` retained at repo root (operator-managed)
- Root-level disposable files cleaned and `.gitignore` strengthened to prevent reaccumulation

Going forward, the contract is enforced by the `_ENFORCEMENT_BLOCK` Output discipline rule.
