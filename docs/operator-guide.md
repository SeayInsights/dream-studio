# Dream Studio Operator Guide

Dream Studio is a local-first AI orchestration and operational intelligence platform. Its repo code lives under `builds/`, while operator runtime state lives under the user-local `.dream-studio` directory. Repo source, local runtime state, SQLite authority, evidence artifacts, dashboard projections, and operator approvals must stay distinguishable.

## Install And Update

Use the repo checkout as the build authority. First-run and update flows should use canonical path resolution for user-local state and should not hardcode operator-specific paths in source. Before updating an installed local runtime, create a full backup, verify the backup SQLite DB opens, confirm rollback instructions exist, and apply only repo-backed additive migrations.

## Daily Operation

Work should advance through route-first milestones and Work Orders. Handoffs are not normal workflow transitions; they are reserved for real approval, blocker, transfer, or safety boundaries. Local dogfood should prefer bounded source changes, focused tests, file-backed evidence, and clean commits.

## Dashboard Telemetry

The dashboard consumes derived telemetry views. Dashboard data is useful for attention, drilldowns, validation, security, token, workflow, research, decision, and component intelligence, but it is not primary authority. API and dashboard responses should preserve `derived_view: true`, `primary_authority: false`, and route authority boundaries.

## Backup, Restore, And Cutover

Personal installed-state cutover requires explicit approval, a fresh full backup, backup verification, rollback instructions, non-destructive rehydration, runtime validation, and a separate cleanup approval boundary. Cleanup, archive, deletion, compaction, deduplication, and DB retention execution are never implied by cutover.

## Demo Readiness

A good demo should show a real goal moving through milestone selection, Work Order generation, source change, validation, telemetry emission, dashboard visibility, route decision, release evidence, and rollback/approval boundaries. The safest demo uses a temp or rehearsal DB and avoids private raw state, secrets, external project mutation, push, deploy, and cleanup execution.

## Safety Checklist

- Repo status is clean before starting a milestone.
- Approved files are listed before mutation.
- Tests use temp or injected DB paths when writing.
- Live SQLite is not mutated unless the milestone explicitly approves it.
- Dashboard telemetry remains derived, not primary authority.
- External projects remain paused unless a file-backed approval opens a bounded scope.
- Push, tag, deploy, cleanup, and destructive DB work remain separate approval boundaries.

## Publication Checklist

- Public docs describe Dream Studio as a local-first AI orchestration and operational intelligence platform.
- Claude Code, Codex, Cursor, Copilot, ChatGPT, MCP, shell, and local models are described as adapter surfaces.
- `.dream-studio`, SQLite DB files, backups, Work Orders, handoffs, raw telemetry, local audits, cutover evidence, cleanup manifests, and operator decision logs remain private by default.
- License references point to Apache-2.0.
- Git history privacy findings are reviewed before pushing to a public remote.
