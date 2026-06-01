# Security-By-Default Development Lifecycle Gate

Dream Studio treats security as a lifecycle control, not a standalone tab. Every
goal, milestone, Work Order, and code change receives a lightweight security
impact classification. Targeted controls run when the change signal is narrow;
full applicable review is required for high-risk lifecycle events.

## Canonical Framework

The canonical framework is the 47 enterprise security controls in
`docs/contracts/security-review-source-47-enterprise-scans.md`. The structured
scan catalog and crosswalk map those controls into Dream Studio's security
skill and review surfaces:

- `docs/contracts/security-review-47-scan-crosswalk.md`
- `docs/contracts/security-review-scan-catalog.yaml`
- `skills/security/SKILL.md`

The security skill may satisfy or orchestrate controls, but the 47-control
framework remains the policy authority.

## Lifecycle Policy

Full applicable 47-control review is required at:

- project intake
- release or merge readiness
- publication
- deployment or live cutover
- dependency, runtime, security, database, or Docker changes
- major architecture changes
- external project onboarding
- scheduled dogfood gates

Lightweight classification remains required for ordinary changes. Controls that
do not apply must record a reason. Unknown or deferred controls route to manual
review or dashboard attention; they do not silently pass.

## Finding Contract

Normalized findings must include:

- project
- file
- line
- severity
- control id
- status
- evidence
- remediation path

Live operator views must not include synthetic or demo findings. Derived
dashboard/API views may summarize findings, but the finding authority remains
SQLite evidence or file-backed review artifacts.

## Readiness Effect

Security status affects project health and release readiness:

- `ready`: security lifecycle clear
- `needs_manual_review`: release held for manual control review
- `unknown_requires_review`: release held for unknown control handling
- `blocked_by_open_findings`: release blocked by current findings

The lifecycle gate is non-executing. It classifies, routes, and records the
required control posture; it does not run scans, inspect secrets, mutate repos,
or write SQLite.

The secure production readiness gate consumes this lifecycle gate rather than
forking the 47-control model. Production readiness can add API, database,
caching, accessibility, observability, performance, dependency, code-quality,
privacy, rollback, and release controls, but enterprise security control
authority remains here.

Module boundary contracts provide the dependency context for lightweight
security classification. A change to `security_only`, `analytics_only`,
`adapter_router`, `external_project`, or `docker_optional` can alter which
controls are applicable, but the module contract route remains read-only and
does not execute scans, mutate repositories, run Docker, or write SQLite.

Contract Atlas lifecycle freshness is a release-gate signal, not a security
scan. The `/api/shared-intelligence/contract-atlas/freshness` route may appear
beside the security lifecycle route in the shared-intelligence router; it does
not inspect secrets, create findings, mutate SQLite, or change 47-control
applicability. Security docs still drift with router changes to confirm the
non-execution boundary.

The expert workflow route is also non-executing. Security reviewers may use
`/api/shared-intelligence/expert-workflows` to see whether implementation,
debugging, design, documentation, API, data modeling, or career/application
workflows require security/readiness evidence, but the route does not run
scans, inspect secrets, fill application forms, submit applications, mutate
SQLite, or change 47-control applicability.

Career Ops, Capability Center, scoped-agent, and GitHub repo intake routes are
also non-executing security-relevant surfaces. Career Ops adds private data and
publication/privacy controls. Scoped agents add context-minimization and
permission-boundary checks. GitHub repo intake adds license, security,
supply-chain, dependency, attribution, and overlap review before third-party
adoption. These routes do not inspect secrets, execute agents, submit
applications, mutate external projects, copy code, or add dependencies.

## Project Portfolio Hydration

All Projects and Project Details consume normalized security findings as a
derived view over current security authority. Findings must remain traceable to
their source rows or evidence refs and include project, file, line, severity,
status, control or rule where available, and remediation path where available.

Project Details now exposes the 47-control applicability list, summary counts,
manual-review count, unknown count, and source framework refs alongside project
health, readiness, stack evidence, validation state, and attention items. This
dashboard route is still non-executing: it does not run scans, inspect secrets,
mutate external projects, draw inferred dependency edges as confirmed, or write
SQLite.

Migrated findings may be assigned to current projects only through
high-confidence mapping, such as an exact project id or the legacy
`project_<project_id_with_underscores>` alias. Findings that cannot be assigned
without ambiguity must be classified as `manual_review_required`,
`unassigned_legacy_finding`, `retention_only`, or `not_applicable` and kept out
of normal operator project cards until reviewed.

The 47 enterprise controls must be visible or honestly unavailable at the
project level. Not-applicable controls require reasons, unknown controls route
to manual review or dashboard attention, and synthetic/demo/test findings must
not appear in live operator views.

Analytics-only ingestion may import normalized security findings from approved
external producers into `security_findings`. This is an authority ingestion
path, not a scanner. It must preserve source/evidence refs, project mapping,
severity, status, rule/control where available, and remediation path where
available. Hooks, agents, workflows, Claude, Codex, and Docker are optional
producers, not required security dependencies.

## AI Usage Accounting Impact

Changes to adapter billing mode, token visibility, cost visibility, provider
usage source handling, telemetry collectors, or dashboard cost display receive
lightweight security impact classification. They normally target privacy,
secrets, logging, telemetry integrity, and release-readiness controls rather
than running the full 47-control review on every edit.

Full applicable review is still required if the accounting change affects
provider credentials, billing APIs, deployment, live cutover, external project
onboarding, database schema, or release/merge readiness. Findings must avoid
printing secrets or provider billing credentials.

## Task Attribution Impact

Task attribution changes receive lightweight security classification because
they link AI/adapter work to files, commands, validation, outcomes, and
security/readiness impact. Applicable checks include telemetry integrity,
evidence refs, logging redaction, source classification, and prevention of fake
model/provider, token, cost, file, command, or outcome precision.

The task attribution routes are non-executing derived views. They do not run
security scans, inspect secrets, mutate SQLite, authorize adapter execution, or
change 47-control applicability by themselves.

## PRD Lifecycle Impact

Project intake, in-flight PRD formalization, Project Change Orders, and route
reconciliation all receive lightweight security/readiness impact
classification. Material changes to security, privacy, data model,
integrations, release targets, or public/private boundaries require targeted or
full applicable review according to the lifecycle policy before authority is
marked current.
## Platform Hardening Refresh

The policy/permission engine is a supporting control-plane surface for the security-by-default lifecycle gate. High-risk actions such as secret access, destructive cleanup, external mutation, push/deploy, Docker execution, package changes, and career submission are denied or deferred by default and must record evidence, approval, rollback, and dashboard attention requirements.

<!-- reviewed: 2026-05-30, migration 084 (project model unification A2). reg_projects deleted; business_projects is the sole project authority. Session hooks now use marker-based UUID resolution. No semantic changes to this document required. -->

<!-- reviewed: 2026-05-30, brownfield vertical slice migration 085. Stack profile + security_scan_runs. No semantic changes required to this document. -->

<!-- 2026-05-31: reg_projects deleted (migration 084); business_projects is canonical. pi_* tables dropped; project_intelligence and prd_authority updated to read detected_stack/stack_json from business_projects. -->

<!-- 2026-06-01: security_scan_runs → scan_runs, security_findings → findings, security_scan_deltas → scan_deltas (migration 089); brownfield intake prompt added; proving-index.md added. -->
