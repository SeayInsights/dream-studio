# Database Guide

Dream Studio uses SQLite as the local structured authority for operational intelligence. The public repo contains schema migrations, bootstrap code, read models, tests, and docs. The operator's live database is private runtime state.

## Paths

| Path | Meaning | Git policy |
| --- | --- | --- |
| `core/event_store/migrations/` | Repo-backed schema migrations | Tracked |
| `core/config/sqlite_bootstrap.py` | Bootstrap and migration application | Tracked |
| `core/config/database.py` | Canonical DB path resolver and environment override behavior | Tracked |
| `~/.dream-studio/state/studio.db` | Operator-local live DB | Ignored/private |
| `*.db`, `*.sqlite*`, `*.db-wal`, `*.db-shm` | Runtime DB files | Ignored/private |

## Authority Areas

Dream Studio's SQLite authority covers:

- project, session, milestone, task, and Work Order state;
- route decisions and approval state;
- hook, tool, skill, token, validation, security, workflow, research, decision, and outcome telemetry;
- dashboard attention items and read-model inputs;
- shared intelligence records including adapters, context packets, normalized results, model/provider metadata, learning events, hardening candidates, and evaluation records;
- secure production readiness assessments, control applicability, findings, remediation Work Order links, project health/readiness scorecards, release readiness records, and compliance/legal review flags;
- release/cutover evidence summaries where safe.

Current Career Ops, Capability Center, scoped-agent, and GitHub repo intake
authority lives in migration 044:

- `career_profiles` and related `career_*` tables for opt-in private career
  profiles, fields, role targets, resume/cover-letter variants, portfolio
  artifacts, case studies, job opportunities, applications, application events,
  field mappings, browser automation runs, interview stories, evidence refs,
  and scorecards;
- `capability_center_records` for optional persisted capability metadata, with
  dashboard summaries also reading current invocation and hardening records;
- `agent_registry_records`, `agent_context_scope_policies`,
  `workflow_agent_skill_mappings`, and `agent_result_records` for scoped worker
  declarations and normalized results;
- `github_repo_*` tables for evidence-backed repository evaluations, license,
  security, dependency, integration, pattern, adoption, and attribution records.

Career data is private by default and excluded from public exports unless
explicitly redacted and approved. GitHub repo intake records do not authorize
copying code, adding dependencies, forking, vendoring, or mutating external
projects.

Current AI usage accounting authority lives in:

- `token_usage_records` for token telemetry with billing, token visibility,
  cost visibility, usage source, cost source, and confidence metadata;
- `ai_adapter_accounting_profiles` for operator-declared adapter billing modes
  such as Claude Code subscription, Claude API token-metered, Codex ChatGPT
  plan, Codex token-metered/flexible, local model, and unknown/custom;
- `ai_usage_operational_records` for operational value telemetry such as run
  count, project/milestone/task/Work Order context, files touched, commands
  run, validation outcome, PR/result outcome, rework, duration, and evidence.
- `task_attribution_records` for execution-unit attribution: which adapter,
  model/provider where known, skills/workflows, tools/hooks, files, commands,
  validations, outcome, rework state, commit/PR/result refs, and
  security/readiness impact belong to a meaningful task or Work Order.

Tokens are usage telemetry. They are not dollars unless the adapter billing
mode and source metadata explicitly make cost reportable. Plan/subscription
usage preserves observed tokens where available and shows cost as unknown
unless an explicit allocation profile exists. Reconciled legacy token rows must
carry `source_refs_json` and `evidence_refs_json` so token analytics can use
current authority without restoring legacy `canonical_events` as an active
source.

Task attribution links usage, adapter results, validation, security/readiness,
and Work Order facts without becoming token/cost authority. Unknown
model/provider values remain `unknown`; unavailable file or command data remains
`unavailable`; imported or untracked work must be classified instead of
overclaimed.

## Runtime Rules

- Normal runtime uses the canonical path resolver.
- Tests that write must use temp or injected DB paths.
- Live DB migration requires explicit approval, fresh backup, backup verification, and rollback instructions.
- Destructive migration, DB record deletion, retention cleanup, compaction, and archive execution are separate approval boundaries.
- Public docs may describe schema concepts but must not include private rows, raw logs, operator decisions, local evidence contents, or DB backups.

## Read Models

Telemetry read models aggregate structured state into dashboard-consumable views. They are derived views and must expose or imply:

- `derived_view: true`
- `primary_authority: false`
- `routing_authority: false`
- source tables and freshness metadata
- module availability and empty-state behavior

## Publication Boundary

Never commit live DB files, backups, WAL/SHM files, dumps, raw telemetry, cutover evidence, cleanup manifests, or local audit trails. Use sanitized fixtures and synthetic examples for public tests and demos.
