# Dream Studio Documentation

Dream Studio documentation is split between public product guidance and private local evidence. Public docs should describe the platform, architecture, APIs, workflows, operator practices, examples, and sanitized release notes. Private Work Orders, handoffs, raw telemetry, local audits, cutover records, backups, cleanup manifests, and operator decision logs belong in local runtime state, not Git.

## Public Product Docs

- [Product Requirements](product/dream-studio-prd.md)
- [Architecture](ARCHITECTURE.md)
- [Database](DATABASE.md)
- [Workflows](WORKFLOWS.md)
- [Operator Guide](operator-guide.md)
- [Quick Start](quickstart.md)
- [Publication Boundary](PUBLICATION_BOUNDARY.md)

## Architecture And Contracts

- [AI Orchestration Architecture](architecture/dream-studio-ai-orchestration-architecture.md)
- [Contract Atlas and Maturity Ledger](architecture/contract-atlas.md) - local
  Dream Studio scope by default, with explicit project scoping available for
  future project-specific atlas inspection.
- [Shared Authority And Adapter Projections](architecture/shared-authority-and-adapter-projections.md)
- [Execution Telemetry Spine](architecture/dream-studio-execution-telemetry-spine.md)
- [Dashboard Projection Mapping](architecture/dream-studio-dashboard-projection-mapping.md)
- [Contracts](contracts/)
- [Security-By-Default Lifecycle Gate](contracts/security-by-default-development-lifecycle-gate.md)
- [Secure Production Readiness Gate](contracts/secure-production-readiness-gate.md)

## Analytics-Only Profile

`analytics_only` is a standalone deployment profile for dashboard/API analytics.
It can import normalized project, CI/validation, security, token/usage,
dependency, stack, PRD, and readiness facts into current SQLite authority with
`ds analytics-ingest`. The command is dry-run by default and writes only with
`--execute`.

Analytics-only does not require hooks, agents, workflows, Claude, Codex, Docker,
repo mutation, or full orchestration. Missing data should appear as honest empty
states.

## Module Contracts

Dream Studio module boundaries are declared in `core.module_contracts` and
surfaced through Contract Atlas. Contracts cover `core`, `telemetry`,
`dashboard`, `security_only`, `token_only`, `analytics_only`,
`shared_intelligence`, `adapter_router`, `adapter_projection`,
`external_project`, `docker_optional`, and `full`.

Each contract names owned authority, read/write dependencies, routes, dashboard
surfaces, commands, disabled-module behavior, empty states, profile membership,
security/readiness impact, maturity level, and validation tests. `token_only`
keeps cost unknown unless cost evidence exists, and Docker remains optional
non-authoritative infrastructure.

## AI Usage Accounting

Dream Studio records AI adapter usage as operational telemetry. Tokens are not
treated as billable dollars unless the adapter billing mode and recorded source
metadata make cost reportable. Claude Code subscription, Codex via ChatGPT
plan, Cursor plan, Copilot subscription, MCP, local models, shell tools, and
unknown/custom adapters are represented through SQLite-backed accounting
profiles and surfaced through the adapter router, Contract Atlas, dashboard
read models, and token/model analytics.

## Operations

- [Local Runtime](operations/local-runtime.md)
- [Work Orders](operations/work-orders.md)
- [Independent Configuration Model](operations/independent-configuration-model.md)
- [Adapter Workspace Hygiene](operations/adapter-workspace-hygiene.md)
- [Installed Adapter Runtime](operations/installed-adapter-runtime.md)
- [Installed Platform Productization](operations/installed-platform-productization.md) -
  includes the Windows `ds.cmd` and `ds.ps1` launcher surfaces plus
  `ds install-command` for user-local plain-command setup.
- [Troubleshooting](operations/troubleshooting.md)
- [Verified Legacy Purge Policy](operations/verified-legacy-purge-policy.md)
- [Windows Development Commands](operations/windows-dev-commands.md)
- [Docker Clean Room](operations/docker-clean-room.md)
- [Docker Module Profiles](operations/docker-module-profiles.md)
- [Lint, Format, And Docs Drift Gate Policy](operations/lint-format-baseline-policy.md)

## Publication Rule

When in doubt, keep generated operational history local. Public examples should be synthetic, sanitized, and reproducible without private operator state.
