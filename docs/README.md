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
  future project-specific atlas inspection. The atlas lifecycle manifest also
  validates private refresh, sanitized public export refresh, docs/PRD/README
  impact detection, and public-export leakage checks.
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

## Installed Dashboard Command

The installed `ds dashboard` command is status-only by default so users can run
it from any directory without accidentally starting services. Use
`ds dashboard --serve` to start the local FastAPI dashboard server,
`ds dashboard --open` to start or reuse the server and open a browser, and
`ds dashboard --check` to validate `/dashboard` and `/api/health` on a running
server.

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

## Expert Workflows

Dream Studio expert workflows map existing skills into evaluated reusable
workflow contracts for intentional implementation, code quality, debugging,
performance, frontend design, SEO/content, documentation, data modeling, API
integration, product demos/case studies, and career/portfolio operations. The
catalog lives in `core.shared_intelligence.expert_workflows` and is exposed at
`/api/shared-intelligence/expert-workflows`.

The workflow system strengthens existing owners instead of creating duplicate
skills. Career and application automation remain private by default and retain
the no-account-creation, no-CAPTCHA-bypass, no-misrepresentation, and
operator-approval-before-submit boundaries.

## Career Ops And Capability Center

Career Ops is an opt-in private module backed by local SQLite authority. It can
store career profiles, role targets, resume/cover-letter variants, portfolio
artifacts, case studies, job opportunities, application records, browser
automation evidence, and evidence-backed scorecards. Career data is excluded
from public exports and demo packets by default.

Capability Center exposes derived views for skills, workflows, agents,
controls, evaluations, and hardening candidates. Scoped agents are treated as
workers rather than authority and receive only the context required for their
task. See [Career Ops, Capability Center, And Scoped Agents](operations/career-ops-capability-center.md).

## GitHub Repo Intake

Dream Studio evaluates third-party GitHub repositories before adopting code,
dependencies, prompts, skills, workflows, hooks, adapters, docs, or patterns.
The intake workflow records license, security, maintenance, overlap,
attribution, and integration decisions in SQLite authority and defaults to
pattern learning/original implementation over copying. See
[GitHub Repo Intake And Integration Evaluation](operations/github-repo-intake-evaluation.md).

## AI Usage Accounting

Dream Studio records AI adapter usage as operational telemetry. Tokens are not
treated as billable dollars unless the adapter billing mode and recorded source
metadata make cost reportable. Claude Code subscription, Codex via ChatGPT
plan, Cursor plan, Copilot subscription, MCP, local models, shell tools, and
unknown/custom adapters are represented through SQLite-backed accounting
profiles and surfaced through the adapter router, Contract Atlas, dashboard
read models, and token/model analytics.

Task attribution extends this by showing which AI/adapter did meaningful work,
which skills/workflows were used, what files and commands were recorded, what
validation ran, what outcome occurred, whether rework was needed, and what
security/readiness impact resulted. See
[AI/Adapter Task Attribution And Outcomes](operations/task-attribution-and-outcomes.md).

## PRD Authority Lifecycle

Dream Studio starts and continues project work from SQLite-backed PRD authority:
adaptive intake, explicit assumptions and unknowns, PRD versions, milestones,
Work Order authority, Project Change Orders, and planned-vs-actual route
reconciliation. Project Details and context packets expose the current PRD
version and next safe action so adapters can continue without relying on prior
chat memory. See [PRD Authority Lifecycle](operations/prd-authority-lifecycle.md).

## Platform Hardening

The platform-hardening sequence makes Dream Studio measurable, permissioned,
privacy-safe, integrated, installable, pilot-ready, and demo-ready. It covers
skill/workflow evaluation, policy decisions, engineering connector ingestion,
privacy/redaction, opt-in local watchers, sanitized team rollups,
installer/distribution checks, and demo/case-study packets. See
[Platform Hardening Sequence](operations/platform-hardening-sequence.md).

The sanitized public demo packet lives at
[Sanitized Demo Readiness Packet](demo/sanitized/README.md). It contains the
5-minute script, 15-minute technical walkthrough, fallback plan, validation
manifest, and synthetic screenshots for Observe, Assist, and Operate modes.

## Operations

- [Local Runtime](operations/local-runtime.md)
- [Work Orders](operations/work-orders.md)
- [Independent Configuration Model](operations/independent-configuration-model.md)
- [Adapter Workspace Hygiene](operations/adapter-workspace-hygiene.md)
- [Installed Adapter Runtime](operations/installed-adapter-runtime.md)
- [Installed Platform Productization](operations/installed-platform-productization.md) -
  includes the Windows `ds.cmd` and `ds.ps1` launcher surfaces plus
  `ds install-command` for user-local plain-command setup, legacy install
  detection, guarded legacy migration, adapter repair, and rollback checks.
- [External Project Validation Pipeline](operations/external-project-validation-pipeline.md)
- [Lightweight GitHub CI Strategy](operations/lightweight-github-ci-strategy.md)
- [Repo Publication Privacy](operations/repo-publication-privacy.md)
- [Troubleshooting](operations/troubleshooting.md)
- [Verified Legacy Purge Policy](operations/verified-legacy-purge-policy.md)
- [Windows Development Commands](operations/windows-dev-commands.md)
- [Docker Clean Room](operations/docker-clean-room.md)
- [Docker Module Profiles](operations/docker-module-profiles.md)
- [Long-Run Multisession Operational Validation](operations/long-run-multisession-operational-validation.md)
- [Lint, Format, And Docs Drift Gate Policy](operations/lint-format-baseline-policy.md)
- [Expert Workflow Systems](operations/expert-workflow-systems.md)
- [Career Ops, Capability Center, And Scoped Agents](operations/career-ops-capability-center.md)
- [GitHub Repo Intake And Integration Evaluation](operations/github-repo-intake-evaluation.md)
- [AI/Adapter Task Attribution And Outcomes](operations/task-attribution-and-outcomes.md)
- [PRD Authority Lifecycle](operations/prd-authority-lifecycle.md)
- [Platform Hardening Sequence](operations/platform-hardening-sequence.md)
- [Sanitized Demo Readiness Packet](demo/sanitized/README.md)

## Publication Rule

When in doubt, keep generated operational history local. Public examples should be synthetic, sanitized, and reproducible without private operator state.

<!-- Last reviewed 2026-05-20 — atlas sanitizer hardened against POSIX absolute paths and `.dream-studio/` substrings (core/shared_intelligence/contract_atlas.py); contract surface unchanged. -->

<!-- Last reviewed 2026-05-28 — fix/linux-ci-failures-batch2: contract_atlas.py private-content scan exclusion added; 7 new adapter projection files generated and committed (chatgpt, codex, copilot, cursor, local-model, mcp, shell). These are generated projection files from default authority profiles. No documentation structure or policy change required. -->

<!-- Last reviewed 2026-05-29 — O2 (18.4-consolidation-followup-4): contract_registry.py updated to close two docs-drift coverage gaps. Domain count is now 15. No docs structure or policy change. -->

<!-- Last reviewed 2026-05-29 — O1: contract_registry.py narrowed 4 over-broad domains. No docs structure or policy change. -->

<!-- reviewed: 2026-05-30, migration 084 (project model unification A2). reg_projects deleted; business_projects is the sole project authority. Session hooks now use marker-based UUID resolution. No semantic changes to this document required. -->

<!-- reviewed: 2026-05-30, brownfield vertical slice migration 085. Stack profile + security_scan_runs. No semantic changes required to this document. -->

<!-- 2026-06-01: security_scan_runs → scan_runs, security_findings → findings, security_scan_deltas → scan_deltas (migration 089); brownfield intake prompt added; proving-index.md added. -->
