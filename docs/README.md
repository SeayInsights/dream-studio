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

## Operations

- [Local Runtime](operations/local-runtime.md)
- [Work Orders](operations/work-orders.md)
- [Independent Configuration Model](operations/independent-configuration-model.md)
- [Adapter Workspace Hygiene](operations/adapter-workspace-hygiene.md)
- [Installed Adapter Runtime](operations/installed-adapter-runtime.md)
- [Installed Platform Productization](operations/installed-platform-productization.md) -
  includes the Windows `ds.ps1` launcher surface.
- [Troubleshooting](operations/troubleshooting.md)
- [Verified Legacy Purge Policy](operations/verified-legacy-purge-policy.md)
- [Windows Development Commands](operations/windows-dev-commands.md)
- [Docker Clean Room](operations/docker-clean-room.md)
- [Docker Module Profiles](operations/docker-module-profiles.md)
- [Lint, Format, And Docs Drift Gate Policy](operations/lint-format-baseline-policy.md)

## Publication Rule

When in doubt, keep generated operational history local. Public examples should be synthetic, sanitized, and reproducible without private operator state.
