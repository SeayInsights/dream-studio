# Platform Hardening Sequence

Dream Studio's platform-hardening sequence turns local orchestration into a measurable, permissioned, privacy-safe, installable, pilot-ready, and demo-ready product surface.

The sequence is implemented as a single authority-backed read model over current Dream Studio systems. It does not create a competing truth source for Work Orders, validation, security findings, analytics ingestion, adapter usage, or Contract Atlas.

## Milestones

- `skill_evaluation_harness`: versioned skill/workflow evaluations with golden fixtures, expected-output contracts, rubric scores, promotion criteria, rollback criteria, and failure pattern tracking.
- `policy_permission_engine_maturation`: reusable policy decisions for read-only work, repo mutation, live SQLite writes, external project work, cleanup, push/deploy actions, adapter execution, browser automation, career submission, secrets, Docker, and dependency changes.
- `engineering_connector_ingestion_framework`: read-only connectors for GitHub, CI reports, JUnit, SARIF, coverage, package manifests, CSV/JSON imports, AI usage exports, and evidence packets that normalize into current SQLite authority.
- `privacy_redaction_and_secret_boundary_maturation`: visibility modes and redaction profiles for private operation, team/client-safe packets, and public sanitized exports.
- `local_watch_and_scheduled_validation_runtime`: opt-in local watchers for dashboard health, release gate, adapter staleness, Contract Atlas freshness, docs drift, project registry, security/readiness, and backup/restore health.
- `team_pilot_rollup_and_sanitized_reporting`: local-first team rollups that share summaries without raw private state.
- `installer_distribution_hardening`: user-facing install, version, doctor, repair, legacy detection, legacy migration dry run, adapter repair, rollback-check, update-check, backup, restore-check, uninstall-check, and acceptance flows.
- `dream_studio_demo_and_case_study_system`: evidence-backed, sanitized demo scripts, proof packets, screenshots checklists, architecture packets, and case studies.

## Authority

Platform hardening records live in SQLite tables created by migration `046_platform_hardening_authority.sql`:

- `skill_evaluation_runs`
- `policy_decision_records`
- `connector_ingestion_runs`
- `privacy_redaction_export_records`
- `local_watch_schedule_records`
- `team_rollup_records`
- `installer_distribution_checks`
- `demo_case_study_packets`

Dashboard/API output is derived from these tables and repo-owned declarations in `core/shared_intelligence/platform_hardening.py`.

## Boundaries

- Default behavior is read-only or dry-run.
- Connector imports normalize into current SQLite authority; they do not create connector-specific truth.
- Watchers are opt-in and disabled by default.
- Policy decisions must record actor, action, target, scope, risk, approval requirement, evidence requirement, rollback requirement, state, reason, source authority, and dashboard attention impact.
- Public exports must use `public_sanitized` visibility and strip private fields before publication.
- Demos and case studies must be evidence-backed and sanitized before external use.

## Dashboard And CLI

Shared Intelligence exposes:

- `/api/shared-intelligence/platform-hardening`
- `/api/shared-intelligence/platform-hardening/skill-evaluations`
- `/api/shared-intelligence/platform-hardening/policy-decision`
- `/api/shared-intelligence/platform-hardening/connectors`
- `/api/shared-intelligence/platform-hardening/privacy`
- `/api/shared-intelligence/platform-hardening/watchers`
- `/api/shared-intelligence/platform-hardening/team-rollup`
- `/api/shared-intelligence/platform-hardening/installer`
- `/api/shared-intelligence/platform-hardening/demo`

The installed command surface includes:

- `ds version`
- `ds doctor`
- `ds repair`
- `ds policy`
- `ds platform-hardening`
- `ds dashboard --status`
- `ds dashboard --serve`
- `ds dashboard --check`
- `ds install --check-legacy`
- `ds migrate-legacy --dry-run`
- `ds repair-adapters`
- `ds rollback-check`

These commands do not authorize destructive changes. Dashboard serve/check
validation is a local runtime health surface only; it must not bootstrap,
migrate, backfill, clean, or mutate external projects.

## PRD Lifecycle Interaction

Platform hardening treats PRD lifecycle records as control-plane authority for
scope, milestones, Work Orders, change orders, and route reconciliation.
Policy, privacy, connector, watcher, team-rollup, installer, and demo surfaces
may summarize PRD lifecycle status, but they must not overwrite PRDs, create
file sprawl, expose private project history, or authorize execution.

<!-- Last reviewed 2026-05-20 — repo-wide `py -m black .` formatting applied; no behavior or policy change required here. -->

<!-- Last reviewed 2026-05-20 — pipeline optimization landed (migration 057 extends ds_work_order_types with workflow_template, precondition_skill, task_generator, resolution_instructions; CLI gains `ds project state` single-query, auto-advance, gotcha injection, brief mode); doc policy unchanged here. -->

<!-- Last reviewed 2026-05-20 — A1 extraction: 22 CLI handlers refactored into importable functions under core/projects, core/work_orders, core/design_briefs, core/milestones, core/skills, core/health. ds.py wrappers are now thin (call function, print result, return exit code). No policy or contract change in this doc. -->

<!-- Last reviewed 2026-05-20 — A2.1: `_work_order_start` decomposed into `read_work_order_brief`, `write_work_order_context`, `start_work_order` under `core/work_orders/start.py`. Stdin y/N prompt removed from the pure path; CLI wrapper preserves the legacy stderr warning + non-TTY auto-accept for operator terminals. No policy or contract change here. -->

<!-- Last reviewed 2026-05-20 — A2.2: `_work_order_close` decomposed into `run_gate_check`, `check_close_gates`, `close_work_order` under `core/work_orders/close.py`. `_run_gate_check` lifted out of `interfaces/cli/ds.py`; `core/projects/queries.py` now imports the predicate directly. CLI wrapper re-emits `[gate.bypassed] WARNING:` to stderr from the returned `bypassed_gates` list for operator-terminal parity. No policy or contract change here. -->