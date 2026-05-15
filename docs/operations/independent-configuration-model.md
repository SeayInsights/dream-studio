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

Installed module profiles are declared in `core.module_profiles`. The
`analytics_only` profile is intentionally independent of hooks, agents,
workflows, Claude, Codex, Docker, repo mutation, and cleanup. Optional modules
must report honest empty states instead of silently requiring unavailable
adapters or runtime services.
