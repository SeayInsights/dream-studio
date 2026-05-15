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

Installed adapter access should prefer the local Dream Studio router where
possible. The router is exposed through `ds router`, `ds adapters`, and
`/api/shared-intelligence/adapter-router`; it reports adapter health, route
state, context packet generation, evidence capture, telemetry capture, module
profile status, and Contract Atlas availability without making an adapter own
Dream Studio logic. Adapters that cannot call the router should consume exported
context packets and return normalized evidence for Dream Studio to ingest.
Productized installs use `ds install` and selected module profiles to create
the user-local runtime home that these adapter/router surfaces read from.
Unsupported tools remain context-packet-only rather than receiving overclaimed
router support. Repo-owned launchers such as `ds.cmd` and `ds.ps1` may expose
the global command surface, and `ds install-command` can materialize user-local
launchers in a PATH directory. They still delegate back to Dream Studio source
and SQLite authority.

Security lifecycle access follows the same boundary. Adapters may read
`/api/shared-intelligence/security-lifecycle` or a generated context packet to
understand which 47-control checks are applicable, deferred, or blocking, but
they do not become security authority and must normalize results back into
Dream Studio records.

Production readiness access follows the same model. Adapters may read
`/api/shared-intelligence/production-readiness` and
`/api/shared-intelligence/production-readiness/controls` to understand
readiness posture, but persisted readiness authority remains in Dream Studio
SQLite records and evidence refs.

Module contract access is read-only. Adapters and dashboard tools may read
`/api/shared-intelligence/module-contracts` or the Contract Atlas section to
understand which modules own authority, which dependencies are optional, and how
disabled modules should behave. Those contracts do not authorize adapter
execution, repo mutation, Docker execution, or live SQLite writes.

AI usage accounting follows the same projection rule. Adapter-local files and
private model memory do not own billing mode, token visibility, cost visibility,
usage source, cost source, confidence, or operational outcome data. Those
records live in SQLite through `ai_adapter_accounting_profiles`,
`ai_usage_operational_records`, and `token_usage_records`, then project into the
router, Contract Atlas, dashboards, and context packets. Subscription-plan tools
must display cost as `unknown` unless an explicit allocation profile is present.

Contract Atlas lifecycle access is also read-only by default. Adapters may call
`ds contract-atlas-refresh` in dry-run mode or read
`/api/shared-intelligence/contract-atlas/freshness` to understand contract,
maturity, docs, PRD, README, dashboard/API, and sanitized export freshness.
Writing export files requires an explicit output directory and `--execute`; it
does not authorize SQLite mutation or adapter config repair.

Analytics-only ingestion is a current-authority import path, not adapter
authority. Tools may produce normalized JSON for projects, CI/validation,
security findings, token/usage telemetry, components, dependencies, PRDs, and
readiness assessments. `ds analytics-ingest` plans by default and writes only
with `--execute`. It imports into SQLite authority tables and keeps hooks,
agents, workflows, Claude, Codex, Docker, repo mutation, and cleanup optional or
out of scope.

Expert workflow access is read-only by default. Adapters may read
`/api/shared-intelligence/expert-workflows` or a context packet summary to
understand the intentional implementation, code quality, debugging,
performance, frontend design, SEO/content, documentation, data modeling, API
integration, case-study, and career/portfolio workflow contracts. Results must
normalize back into Dream Studio authority records when execution is approved.
The route does not replace existing skills, publish private career data, fill
applications, or authorize browser automation.

External project validation follows the same projection discipline. External
targets are registry entries and dashboard cards until the current operator
decision selects a target and scope. Planning can describe dirty-state capture,
PRD/status detection, stack/dependency discovery, security/readiness
classification, validation profile, Work Orders, and commit policy, but it does
not inspect or mutate the target repo.

Long-run multisession validation is also derived evidence. It aggregates
dashboard/authority, dogfood route, release gate, installed command, docs drift,
security/readiness, adapter/router, and analytics-only cycles with a live SQLite
hash guard. It does not turn adapter output, dashboard output, Docker status, or
external target metadata into source authority.

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
Static Docker profile contracts can be used operationally for planning and
status, but container execution requires separate approval.
