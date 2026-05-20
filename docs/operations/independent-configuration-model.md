# Independent Configuration Model

Dream Studio configuration is modular. Each area declares its source, export
targets, owner, lifecycle state, validation needs, storage class, and approval
boundary.

| Area | Canonical Source | Projection Targets | Storage | Approval |
| --- | --- | --- | --- | --- |
| Adapter profiles | `adapter_authority_profiles` | `CLAUDE.md`, `AGENTS.md`, Cursor/Copilot rules | SQLite plus projections | Required |
| Model/provider profiles | `model_provider_profiles` | route model, dashboard, context packets | SQLite | Required |
| Context packets | `shared_context_packets` | Claude/Codex/ChatGPT/MCP packets | SQLite/export | Not for generation |
| Adapter results | `adapter_result_records` | dashboard, learning feedback, audit exports | SQLite | Not for normal recording |
| Skills/workflows/hooks | repo source plus telemetry/hardening records | adapter projections, component analytics | repo plus SQLite | Required for behavior changes |
| Dashboard modules | repo read models plus telemetry tables | API/frontend | repo | Not for derived reads |
| Telemetry modules | migration-backed telemetry tables | dashboard/API/read models | SQLite | Required for schema changes |
| Docker/runtime profiles | docs plus future module registry fields | optional containers | repo docs/config | Required |
| Approval policies | operator decisions, Work Orders, route records | attention queue, release gates | SQLite/evidence | Required |
| Local DB path | `core.config.database` | runtime, tests, dashboard | repo plus local env | Required for default changes |
| Installed adapter router | `core.installed_runtime` | `ds router`, `/api/shared-intelligence/adapter-router` | repo plus local state | Required for router changes |
| Installed platform productization | `core.installed_productization` | `ds install`, `ds acceptance`, backup/restore/update/uninstall checks | repo code plus explicit runtime home | Required for install/update behavior changes |
| Installed dashboard command | `interfaces.cli.ds` plus `projections.api.main` | `ds dashboard --status`, `--serve`, `--open`, `--check` | repo code plus explicit runtime home | Required for dashboard launch behavior changes |
| Module contracts | `core.module_contracts` | Contract Atlas, profile validation, docs drift, release gate tests | repo source | Required for module boundary changes |
| Contract Atlas lifecycle | `core.shared_intelligence.contract_atlas_lifecycle` | `ds contract-atlas-refresh`, `/api/shared-intelligence/contract-atlas/freshness`, release gate | generated exports to explicit caller path | Required for atlas/export freshness changes |
| Security lifecycle gate | `core.security.lifecycle` plus 47-control security contracts | `/api/shared-intelligence/security-lifecycle`, Contract Atlas, release readiness | repo docs/code plus SQLite findings | Required for policy changes |
| Production readiness gate | `core.production_readiness` plus additive SQLite readiness tables | `/api/shared-intelligence/production-readiness`, Project Details, Contract Atlas, release readiness | repo docs/code plus SQLite authority records | Required for readiness policy/schema changes |
| AI usage accounting | `ai_adapter_accounting_profiles`, `ai_usage_operational_records`, `token_usage_records` | `ds router`, `ds adapters`, token/model analytics, Contract Atlas, context packets | SQLite plus derived views | Required for billing-mode or cost-visibility changes |
| Analytics-only ingestion | `core.analytics_ingestion` normalized payload contract | `ds analytics-ingest`, `/api/shared-intelligence/analytics-only`, All Projects, Project Details, metrics/security/readiness APIs | explicit SQLite imports plus derived views | Required for analytics import contract changes |
| Expert workflows | `core.shared_intelligence.expert_workflows` | `/api/shared-intelligence/expert-workflows`, Contract Atlas, Project Details/dashboard attention when executed | repo catalog plus existing SQLite authority targets | Required for skill/workflow overlap or career automation boundary changes |
| GitHub CI/CD profile | `runtime/config/release-gates/dream-studio.json` plus `core.release.github_pr_cicd_gate` | Contract Atlas, release gate packet, GitHub workflows | repo source/config | Required for workflow or merge-policy changes |
| External project validation | `core.projects.external_validation` | All Projects, Project Details, Work Order plans | repo source plus SQLite/evidence refs | Required for target access or policy changes |
| Docker module profiles | `core.telemetry.docker_profiles` | module registry, Contract Atlas, runtime status | repo source/config | Required for Docker execution or profile changes |
| Long-run validation closeout | `core.release.local_dogfood_stability` | release gate packet, Contract Atlas, final closeout | evidence refs plus repo source | Required for release closeout changes |

Adapter files are allowed to exist only as projections. Repo-root `CLAUDE.md`
and `AGENTS.md` are active project surfaces for Claude and Codex when those
adapters load the repository. Generated files under `adapter-projections/` are
verification/export artifacts until an approved repair or install flow copies,
links, or otherwise refreshes an active adapter surface. Local user-specific
settings that include secrets or credentials are sensitive manual-review items
and must not be read, printed, copied into public docs, or committed.

Adapter scratch files, app-created worktrees, session transcripts, temporary
prompts, and runtime caches are not configuration authority. They should live
under user-local Dream Studio state or a checkout-local excluded area such as
`.claude/worktrees/` or `.codex/sessions/`. Use `.git/info/exclude` for
machine-specific adapter scratch paths; reserve repo `.gitignore` for patterns
that are safe for every user and do not hide product source, active adapter
surfaces, or generated adapter projections.

Configuration can be enabled independently. Docker, external project scanning,
browser smoke automation, and deployment remain optional profiles and cannot
become core authority without a separate approved Work Order.

External project configuration is paused-by-default. Current target selection
is required before read-only intake, and scoped approval is required before
mutation, commit, push, or deploy. Docker profile configuration is optional and
non-authoritative; profile contracts can be validated without starting
containers.

Installed module profiles are declared in `core.module_profiles`. The
`analytics_only` profile is intentionally independent of hooks, agents,
workflows, Claude, Codex, Docker, repo mutation, and cleanup. `token_only`
keeps token and AI usage telemetry independent from fabricated cost claims.
Optional modules must report honest empty states instead of silently requiring
unavailable adapters or runtime services.

Major module contracts are declared in `core.module_contracts` and surfaced
through Contract Atlas. They are boundary declarations, not runtime execution
authority. A module contract may exist without becoming an installable profile,
and an installable profile may include multiple module contracts.

Contract Atlas lifecycle exports are generated on demand. Public sanitized
exports and freshness manifests can be written only to an explicit output path
with `ds contract-atlas-refresh --execute`; private/internal exports require
`--include-private` and are not repo-safe. The lifecycle gate runs in an
isolated temp runtime and must not touch live installed SQLite.

GitHub CI/CD profile changes are repo-backed release-policy changes. GitHub
Actions provide PR smoke and manual remote evidence only; local Dream Studio
release gates remain the heavy authority. Disabled or unaffordable Actions
create a manual-review release gap rather than a local development blocker.

Analytics-only ingestion is explicit. Hooks, adapters, CI jobs, or manual
exports may produce normalized payloads, but analytics-only does not require
them. `ds analytics-ingest` dry-runs by default and writes only with
`--execute`, targeting current SQLite authority tables instead of creating
legacy file-sprawl or competing dashboard-only stores.

Expert workflow configuration is repo-backed. It maps existing skill/workflow
owners into reusable workflow contracts, overlap decisions, scoring rubrics,
and privacy boundaries. Runtime executions may write structured results through
existing authority tables, but the catalog itself does not create a competing
skill database or authorize browser automation, publication, external mutation,
or live SQLite writes.

Productized first-run setup must always target an explicit Dream Studio home or
an approved installed home resolved from configuration. Rehearsal acceptance
uses temporary homes and must not write to the operator's live
`~/.dream-studio` state. Launcher files such as `ds.cmd` and `ds.ps1` are repo
source that resolve source/state boundaries; user-local launchers generated by
`ds install-command --execute` are installed command projections, not runtime
scratch or adapter authority.

Legacy install migration is a configuration transition, not a source history
merge. The old checkout and old runtime home are detected, backed up, and kept
as rollback/manual-review sources. The fresh active home receives current
runtime config, current migrations, compatible SQLite authority rows, and
current launcher/adapter projections only. Legacy file-sprawl remains in the
backup unless a later additive SQLite migration gives it current authority
semantics.

Adapter billing declarations are configuration, not provider billing
credentials. Subscription-plan adapters keep cost unknown unless an approved
allocation profile is recorded. Token-metered/API-metered adapters may display
reportable cost only when source metadata, usage exports, billing API evidence,
or explicit estimate metadata is present.

Task attribution records are also configuration/runtime authority, not adapter
private memory. They can connect adapter usage to a project, Work Order,
skills/workflows, files, commands, validation, outcome, rework, and
security/readiness impact, but they must keep unknown or unavailable values
explicit and must not infer token or cost precision.

Career Ops configuration is private and disabled until explicitly enabled. It
may store career and application records only in approved local SQLite
authority; it must not leak into public exports, team rollups, sanitized demo
packets, or repo docs as data.

Capability Center and scoped-agent configuration are authority-backed read
models and policies. Agents receive only task-required context, never full
conversation history, secrets, all Work Orders, all memories, raw local
evidence, or unrelated private data by default.

GitHub repo intake configuration is an evaluation workflow, not an adoption
approval. It may record evidence-backed decisions, but it does not fetch,
copy, fork, vendor, add dependencies, mutate external repositories, or waive
license/security/legal review boundaries.

PRD lifecycle configuration is not adapter-local memory. Intake mode,
assumptions, current PRD version, milestone sequence, Work Order authority,
change orders, and route reconciliation are stored in SQLite authority and may
be projected into context packets. Adapter configs must not maintain a
competing PRD copy.
## Platform Hardening Refresh

The independent configuration model now includes platform-hardening configuration surfaces for policy decisions, connector definitions, opt-in local watchers, installer checks, sanitized rollups, and demo packets. Defaults are dry-run or disabled unless an operator-approved profile enables writes, scheduling, or export generation.

<!-- Last reviewed 2026-05-20 — repo-wide `py -m black .` formatting applied; no behavior or policy change required here. -->

<!-- Last reviewed 2026-05-20 — pipeline optimization landed (migration 057 extends ds_work_order_types with workflow_template, precondition_skill, task_generator, resolution_instructions; CLI gains `ds project state` single-query, auto-advance, gotcha injection, brief mode); doc policy unchanged here. -->

<!-- Last reviewed 2026-05-20 — A1 extraction: 22 CLI handlers refactored into importable functions under core/projects, core/work_orders, core/design_briefs, core/milestones, core/skills, core/health. ds.py wrappers are now thin (call function, print result, return exit code). No policy or contract change in this doc. -->

<!-- Last reviewed 2026-05-20 — A2.1: `_work_order_start` decomposed into `read_work_order_brief`, `write_work_order_context`, `start_work_order` under `core/work_orders/start.py`. Stdin y/N prompt removed from the pure path; CLI wrapper preserves the legacy stderr warning + non-TTY auto-accept for operator terminals. No policy or contract change here. -->

<!-- Last reviewed 2026-05-20 — A2.2: `_work_order_close` decomposed into `run_gate_check`, `check_close_gates`, `close_work_order` under `core/work_orders/close.py`. `_run_gate_check` lifted out of `interfaces/cli/ds.py`; `core/projects/queries.py` now imports the predicate directly. CLI wrapper re-emits `[gate.bypassed] WARNING:` to stderr from the returned `bypassed_gates` list for operator-terminal parity. No policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — A2.3: `_project_start` decomposed into the `start_project` composer under `core/projects/start.py`, which orchestrates `set_active_project` (mutations) + `get_next_work_order` (queries) + `start_work_order` (work_orders/start). CLI wrapper converts the compound result dict into the legacy operator-facing summary; no policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — A2.4: `_skill_invoke` (heaviest CLI handler) decomposed into `load_skill_content` + `record_skill_invocation` + `seed_gate_artifact_files` under `core/skills/invocation.py`. Duplicate `_load_packs` / `_SKILL_SPECIFIER_RE` / `_SKILL_FM_RE` removed from `interfaces/cli/ds.py`; the canonical `_load_packs` lives in `core/skills/queries.py`. Phase A3 workflow runner can now compose these three functions directly. No policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — A2.5: `_design_brief_create` lifted to `create_design_brief` in `core/design_briefs/mutations.py` (returns dict with brief_id, project_id, status, next_step). CLI wrapper preserves the legacy `Draft brief created:` stdout line. A2.4's lazy `from interfaces.cli.ds import _design_brief_create` in `core/skills/invocation.py` is now a direct `core.design_briefs.mutations` import. No policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — A2.6: `_design_brief_lock` lifted to `lock_design_brief` in `core/design_briefs/mutations.py` (returns dict with brief_id, status='locked', locked_at; ok=False/error for missing brief). CLI wrapper preserves the legacy `Brief <id> locked.` stdout line and exit-1 JSON path. No policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — A2.7: `_milestone_close` lifted to `close_milestone` in `core/milestones/close.py`. Pure function returns one canonical result dict across every path (missing milestone / open WOs / gate failures / forced bypass / success); CLI wrapper preserves the legacy mixed-format operator output (JSON for failures, plain-text on success, `[gate.bypassed] WARNING:` stderr on force). No policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — A2.8: `_update_command` no longer self-shells via `subprocess.run(['ds','integrate','install','claude_code','--execute'])`; instead it calls `ClaudeCodeInstaller.install('execute')` directly in-process, mirroring the `ds integrate install` code path. Skips interpreter respawn, keeps tracebacks intact, and lets callers patch the installer with `unittest.mock`. Final A2 handler. No policy or contract change here. -->