# Shared Authority And Adapter Projections

Dream Studio is the source of truth for local-first AI orchestration and
operational intelligence. Claude, Codex, Cursor, Copilot, ChatGPT, MCP, local
models, shell tools, and future tools are adapters over Dream Studio authority.

## Canonical Authority

Canonical records live in:

- repo source for product code, schemas, skills, workflows, hooks, docs, and
  tests;
- operator-local SQLite for Work Orders, route decisions, telemetry facts,
  learning events, adapter profiles, model/provider profiles, context packets,
  normalized adapter results, hardening candidates, project authority, PRD
  authority, validation results, and security findings;
- operator-local evidence packets for human-readable exports and audit trails.

Dashboard data is a derived view. It must include `derived_view=true` and
`primary_authority=false` when exposed through API/read-model surfaces.

## Adapter Role

Adapters execute, review, explain, or project context. They do not own source
of truth.

Adapter-specific files such as `CLAUDE.md`, `AGENTS.md`, Cursor rules, Copilot
instructions, MCP command templates, and shell launchers are projections from
Dream Studio authority. They should say what authority they project from and
should be refreshed when SQLite/repo authority changes.

Repo-root `CLAUDE.md` and `AGENTS.md` are the active Claude/Codex project
surfaces when those adapters load the repository. Files under
`adapter-projections/` are generated projection artifacts used for verification,
staleness detection, export, and future sync/install flows. They do not become
active adapter config merely by existing; active-surface refresh requires an
explicit approved projection repair or install boundary.

Adapter scratch folders, app-created worktrees, local session histories, and
runtime caches are not adapter projections. They must stay under user-local
Dream Studio state or a checkout-local excluded path, and they must not pollute
repo status. Unknown adapter files require classification before any ignore,
delete, archive, or cleanup decision. Secret/auth/token paths may be recorded as
path-level metadata only; do not inspect or print their contents.

Private model memory is never authority. If another AI resumes work, Dream
Studio should provide a shared context packet from SQLite/evidence records.

## Convergence Rules

When duplicate legacy state exists:

1. classify the source;
2. migrate real data into current authority where possible;
3. prove current API/read models consume current authority;
4. verify no active reference depends on the old source;
5. purge only the old source rows proven migrated, obsolete, mock, demo, temp,
   or placeholder;
6. keep unknown or sensitive items under manual review.

Rollback backups remain protected until a separate cleanup approval boundary.

## Cross-AI Continuity

Dream Studio records adapter profiles, model/provider profiles, generated
context packets, normalized adapter results, capability routes, learning events,
and hardening candidates in SQLite. A Claude-style packet and a Codex-style
packet generated from the same source should explain the same project state.
Their results should normalize into one shared Dream Studio history.

## Container Boundary

Docker is optional. It can support scanners, workers, adapters, dashboard/API
profiles, and validation sandboxes, but it must not create a second authority
database. Docker-backed modules should receive an explicit SQLite path or a
read-only/rehearsal copy according to their approved profile.
