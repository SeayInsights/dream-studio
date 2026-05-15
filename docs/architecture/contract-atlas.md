# Contract Atlas

Lifecycle status: foundation_active

The Contract Atlas is Dream Studio's private-by-default map of its own system
contracts. It explains what each layer, module, interface, runtime profile, and
adapter projection is allowed to own, what it can only derive, and which docs
must be refreshed when meaningful source changes occur.

## Authority Boundary

The Contract Atlas is a derived view. It does not create routing authority,
database authority, cleanup authority, adapter execution authority, or release
approval.

Current implementation:

- `core/shared_intelligence/contract_atlas.py` builds the atlas read model.
- `core/shared_intelligence/contract_registry.py` defines the contract domains
  and changed-file-to-docs impact mapping.
- `core/shared_intelligence/contract_atlas_lifecycle.py` builds the freshness
  manifest that ties private atlas refresh, sanitized public export refresh,
  maturity ledger validation, docs drift, PRD/README impact detection, and
  leakage checks together.
- `/api/shared-intelligence/contract-atlas` exposes the atlas for local
  dashboard and tooling consumption.
- `/api/shared-intelligence/contract-atlas/freshness` exposes the lifecycle
  freshness manifest without writing exports or SQLite rows.
- If no `project_id` is supplied, the Contract Atlas defaults to the local
  Dream Studio project scope (`dream-studio`) so adapter projection staleness is
  compared against the same generated project-scoped files used by the active
  clean checkout. Callers can still pass an explicit `project_id` for scoped
  inspection.
- `interfaces/cli/contract_docs_drift_gate.py` blocks release closure when
  impacted contracts or docs are stale.
- `interfaces/cli/contract_atlas_lifecycle_gate.py` validates the atlas
  lifecycle, maturity ledger, docs/PRD/README impact detection, and sanitized
  public-export leakage boundary in an isolated temp runtime.

## Registry Foundation

The registry currently tracks these release-blocking domains:

- Contract Atlas
- Shared intelligence and adapter projections
- AI adapter task attribution and outcomes
- SQLite schema and authority
- Installed adapter runtime and global router
- Dashboard runtime and read models
- Workflow and hook runtime
- Security-by-default lifecycle gate
- Secure production readiness gate
- Release gate and publication boundary
- External project validation pipeline
- Docker module runtime boundary
- Long-run multisession operational validation
- Expert skills and workflow system
- Platform hardening sequence

Each domain declares:

- source patterns;
- contract refs;
- documentation refs;
- required docs that must be refreshed with meaningful source changes;
- public/private export boundary;
- freshness policy.

## Maturity Ledger

The atlas includes a current maturity ledger for major Dream Studio areas. Each
area is classified as one of:

- `hardened`
- `runtime_validated`
- `tested_only`
- `designed_not_proven`
- `stale`
- `blocked`
- `not_started`
- `manual_review_required`

Every ledger row must include evidence refs, validation refs, owner/source,
known gaps, next action, whether it can be claimed publicly, and whether it can
be used operationally. This prevents Dream Studio from claiming live Claude,
Codex, Docker, external-project, or release behavior that is only designed or
tested in isolation.

The installed runtime model, module profiles, major module contracts, final
productization closeout, and long-run multisession validation are first-class
atlas sections. They declare the source/state split, global command surface,
adapter-router read model, per-profile dependency expectations, release gate
hash guard, and explicit module boundaries so installed Dream Studio behavior is
visible without making the atlas an installer, mutator, or live-state authority.

Installed platform productization is tracked through the installed adapter
runtime and global router contracts. The atlas treats `ds.cmd`, `ds.ps1`, and
`ds install-command` as installed command-surface contract inputs so plain
`ds` behavior stays visible in drift checks without making the atlas an
installer or runtime mutator.

## AI Usage Accounting

The Contract Atlas now exposes `adapter_usage_accounting` as a derived section
backed by `ai_adapter_accounting_profiles`, `ai_usage_operational_records`, and
`token_usage_records`. This section records adapter billing modes, token
visibility, cost visibility, usage source, confidence, operational value
signals, and task attribution rollups without claiming provider billing
authority.

Plan/subscription adapters such as Claude Code subscription and Codex through a
ChatGPT plan show cost as `unknown` unless an explicit allocation profile is
configured. Token-metered/API-metered adapters can show reportable cost only
when provider metadata, provider export, billing API data, or an explicitly
marked estimate exists.

The atlas also exposes `task_attribution_model`, backed by
`task_attribution_records` and the existing execution, invocation, validation,
adapter-result, usage, security, and readiness tables. This model lets Project
Details, Work Order details, Adapter Usage, and Capability Center show which
AI/adapter did meaningful work, which skills/workflows were used, what files
and commands were recorded, what validation ran, what outcome occurred, whether
rework was needed, and what security/readiness impact was observed. It keeps
unknown model/provider values explicit and never infers fake token or cost
precision.

## Platform Hardening

The atlas exposes `platform_hardening`, backed by migration
`046_platform_hardening_authority.sql` and
`core.shared_intelligence.platform_hardening`. This section summarizes skill
evaluation harness readiness, policy/permission decisions, engineering
connector ingestion, privacy/redaction boundaries, opt-in local watchers,
sanitized team rollups, installer/distribution checks, and demo/case-study
packets.

The confirmed dependency graph maps the platform-hardening module to its SQLite
tables and to analytics-only ingestion. This keeps connector imports normalized
into current authority and prevents policy, demo, or team-rollup outputs from
becoming separate truth sources.
runtime domain. Installer, first-run setup, acceptance, backup, restore-check,
update-check, uninstall-check, module profile selection, and troubleshooting
docs must drift with changes to the installed runtime or global command
surface, including repo-owned launchers such as `ds.cmd` and `ds.ps1`. The atlas can
describe and validate those contracts, but execution still belongs to the `ds`
command surface and explicit operator-approved runtime flows.

The security lifecycle gate is also a first-class atlas section. It maps the
47 enterprise security controls to the security review catalog, security skill,
project health, and release readiness while preserving the non-execution
boundary.

The secure production readiness gate is a first-class atlas section and
maturity input. It maps the security lifecycle gate plus production readiness
control families into project readiness, release readiness, remediation Work
Orders, and dashboard detail without turning the atlas into an execution engine.

Project portfolio maturity is reflected through the dashboard runtime,
security lifecycle, and secure production readiness contracts. All Projects and
Project Details may display current project authority, PRD authority, stack and
dependency evidence, security findings, 47-control status, production readiness
coverage, health, readiness, blockers, remediation, and evidence refs, but they
remain derived views. Legacy, demo, temp, placeholder, and unmapped findings are
classified for retention or manual review instead of being promoted into normal
operator cards.

Project Details now treats architecture and stack evidence as part of the
dashboard runtime/readiness contract. It can show safe read-only repo evidence,
module/runtime profile fit, confirmed dependency graph edges, inferred or
unverified dependency names hidden by default, validations, attention items,
known gaps, and next action. The atlas still treats dashboard output as derived:
no dependency edge is confirmed unless it comes from current authority such as
`pi_dependencies` with source/evidence refs.

External project validation is now tracked as a paused-by-default operational
contract. The atlas records that DreamySuite, Bill Stack, TORII, and future
external targets require explicit current target selection before read-only
intake, scoped approval before mutation, validation and commit policy before
commit, and separate approval before push or deploy. The pipeline can expose
derived dashboard cards and Work Order plans, but it does not inspect or mutate
target repos during planning.

Docker module profiles are tracked as optional runtime-boundary contracts. The
atlas records scanner, sandbox, adapter worker, ingestion worker, and
dashboard/API profile definitions with explicit SQLite path policy, no default
host writes, no competing authority database, approval before container
execution, and native/local fallback when Docker is unavailable.

The atlas also records the analytics-only ingestion contract. That contract
declares the standalone `analytics_only` profile, the dry-run-by-default
`ds analytics-ingest` command, the `/api/shared-intelligence/analytics-only`
status route, and the current SQLite authority tables it can import into when
explicitly executed. Hooks, agents, workflows, Claude, Codex, Docker, repo
mutation, and cleanup are not required for analytics-only operation.

The atlas records the GitHub CI/CD profile as a derived release-authority
section. That profile declares GitHub Actions as a lightweight remote
confidence layer, `pr-smoke` as the required PR check, manual `full-ci` as
remote parity evidence, and manual/tag-triggered release validation as release
evidence. The local Dream Studio release gate remains the heavy validation
layer, and unavailable Actions create a manual-review gap instead of blocking
ordinary local development.

`core.module_contracts` is the source-level registry for major module
boundaries: `core`, `telemetry`, `dashboard`, `security_only`, `token_only`,
`analytics_only`, `shared_intelligence`, `adapter_router`,
`adapter_projection`, `external_project`, `docker_optional`, and `full`. The
atlas exposes those contracts separately from lower-level telemetry dashboard
module declarations so product/runtime boundaries are not confused with
individual dashboard cards. `token_only` preserves unknown or plan-based costs
as unknown, `dashboard_only` shows unavailable optional data honestly,
`shared_intelligence` and `adapter_router` work without live Claude/Codex
execution, and Docker remains optional non-authoritative infrastructure.
The same contract payload is available directly at
`/api/shared-intelligence/module-contracts` for dashboard/API consumers that do
not need the full atlas.

The atlas also exposes `expert_workflow_system`, a derived section backed by
`core.shared_intelligence.expert_workflows`. It summarizes the expert workflow
catalog, overlap decisions, no-duplicate-skill policy, career/application
automation boundaries, and authority write targets. Confirmed dependency graph
edges map each expert workflow back to existing skill/workflow owners rather
than inventing a parallel skill system. The full catalog is available at
`/api/shared-intelligence/expert-workflows`.

The atlas now also exposes:

- `career_ops_module`, an opt-in private module summary that reports schema
  readiness and automation boundaries while excluding career data from public
  exports;
- `capability_center`, a derived skills/workflows/agents/controls/evaluations
  surface backed by authority tables and repo contracts;
- `scoped_agent_execution`, which declares agents as scoped workers and records
  forbidden context defaults;
- `github_repo_intake`, which records evidence-backed external repo evaluation
  outcomes and blocks unapproved code copy, dependency adoption, fork/vendor,
  or attribution-sensitive reuse.

## Drift Gate

The drift gate checks changed files against the registry. If source changes
impact a domain, the required contract or docs refs for that domain must be in
the same change set. This keeps Dream Studio from closing work that changed
code, schema, dashboard routes, workflows, hooks, adapters, or release behavior
while leaving the matching public docs stale.

The gate distinguishes:

- docs update required;
- docs reviewed and no change needed;
- PRD update required;
- README update required;
- Contract Atlas update required;
- publication boundary review required;
- private artifact risk detected.

The gate is intentionally scoped. It does not rewrite every doc blindly and it
does not require PRD updates for implementation details that do not change
product authority.

## Lifecycle And Export Refresh

Contract Atlas lifecycle management is generated from Dream Studio authority,
not maintained by hand. `ds contract-atlas-refresh` plans or writes explicit
exports to a caller-supplied directory. The command is dry-run by default,
does not mutate SQLite, and writes only when `--execute` is supplied.

The lifecycle manifest includes:

- private/internal Contract Atlas refresh status;
- public sanitized export refresh status;
- maturity ledger validation;
- docs, PRD, README, and publication-boundary impact detection;
- public-export private-data leakage checks;
- release-gate status for stale contracts, docs, and exports;
- dashboard/API freshness status.

Public exports must use `contract-atlas.public_sanitized.json` and may be
shared only after the leakage check passes. Private/internal exports are for
operator-local runtime or review directories only and are not repo-safe
artifacts.

Repo publication readiness is a release/publication gate input. Contract Atlas
tracks the publication/privacy maturity area and the release-publication domain
so changes to publication checks, history privacy classification, sanitized
exports, README/PRD alignment, or Apache-2.0 references require same-change-set
docs refresh and publication evidence review.

## Export Boundary

The private atlas may include local repo paths and local surface status. Public
exports must be sanitized and must not include private runtime state, local
evidence paths, secrets, raw telemetry, backups, or operator-local config
contents.

Career Ops rows and private application/career evidence are excluded from
public Contract Atlas exports by default. Public exports may retain only the
policy statement that Career Ops is private and opt-in. GitHub repo intake
evidence remains private until a sanitized adoption note is explicitly approved.

## Visual Layer

The current milestone establishes the foundation and release gate. A later
visual Contract Atlas dashboard can render the same registry, graph, scorecard,
and boundary report without inventing new dependency data.
